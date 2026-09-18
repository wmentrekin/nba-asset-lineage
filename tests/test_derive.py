"""Tests for lineage.derive: build_graph on the captured feed plus the curated data files."""

import datetime as dt
import json

import pytest

from lineage.derive import (
    INSERT_MOVEMENT_SQL,
    INSERT_PICK_SQL,
    INSERT_PLAYER_SQL,
    INSERT_TRANSACTION_SQL,
    TRUNCATE_SQL,
    DeriveError,
    build_graph,
    graph_to_dict,
    graph_to_json,
    load_graph,
    select_feed_payload,
)
from lineage.corrections import DropRow
from lineage.picks import UNCURATED_NOTE, PickMove
from lineage.snapshot import UnresolvedPlayerError
from lineage.timeline import Segment, build_timelines

BASELINE_ID = "OPENING-2025-26"


@pytest.fixture
def graph(feed_payload, resolvable_inputs):
    snapshot, pick_events, corrections = resolvable_inputs
    return build_graph(feed_payload, snapshot, pick_events, corrections)


def test_build_graph_fails_loudly_on_an_unresolvable_snapshot_player(
    feed_payload, curated_inputs
):
    snapshot, pick_events, corrections = curated_inputs

    with pytest.raises(UnresolvedPlayerError, match="Jaylen Wells"):
        build_graph(feed_payload, snapshot, pick_events, corrections)


def test_baseline_node_holds_the_whole_opening_inventory(graph):
    baseline = next(t for t in graph.transactions if t.id == BASELINE_ID)
    movements = [m for m in graph.movements if m.transaction_id == BASELINE_ID]

    assert baseline.kind == "baseline"
    assert baseline.occurred_on == dt.date(2025, 10, 22)
    assert baseline.description == "Opening-night roster and owned pick inventory"
    assert baseline.group_key is None
    assert baseline.source_key == "snapshot"
    assert sum(1 for m in movements if m.asset_type == "player") == 18
    assert sum(1 for m in movements if m.asset_type == "pick") == 15
    assert all(m.from_holder is None and m.to_holder == "MEM" for m in movements)


def test_baseline_is_first_and_the_first_feed_transaction_is_basseys_ten_day(graph):
    assert graph.transactions[0].id == BASELINE_ID

    first_feed = graph.transactions[1]

    assert first_feed.id == "Signing-1139430"
    assert first_feed.occurred_on == dt.date(2025, 10, 27)
    assert first_feed.kind == "ten_day"
    assert first_feed.source_key == "feed"


def test_pre_window_feed_rows_are_excluded(graph):
    transaction_ids = {t.id for t in graph.transactions}

    # June/July 2025 moves: the Bane trade, the Huff trade and the summer signings.
    for excluded in ("Trade-2024042", "Trade-2025003", "Signing-1135871", "Waive-1135841"):
        assert excluded not in transaction_ids
    assert min(t.occurred_on for t in graph.transactions) == dt.date(2025, 10, 22)


def test_landale_moves_from_the_baseline_to_utah(graph):
    timelines = build_timelines(graph.movements)

    assert timelines[("player", "1629111")] == [
        Segment(
            from_node=BASELINE_ID,
            to_node="Trade-2025022",
            holder="MEM",
            contract_type="standard",
        ),
        Segment(
            from_node="Trade-2025022", to_node=None, holder="UTA", contract_type=None
        ),
    ]


def test_pj_hall_goes_from_a_two_way_baseline_to_free_agency(graph):
    timelines = build_timelines(graph.movements)

    assert timelines[("player", "1641790")] == [
        Segment(
            from_node=BASELINE_ID,
            to_node="Waive-1140530",
            holder="MEM",
            contract_type="two_way",
        ),
        Segment(
            from_node="Waive-1140530", to_node=None, holder="FA", contract_type=None
        ),
    ]


def test_uncurated_draft_considerations_become_notes(graph):
    uncurated = {t.id for t in graph.transactions if t.note == UNCURATED_NOTE}

    assert uncurated == {
        "Trade-2025022",
        "Trade-2025037",
        "Trade-2026006",
        "Trade-2026014",
    }
    assert not [m for m in graph.movements if m.asset_type == "pick" and m.transaction_id
                in uncurated]
    assert all(f"{t}: {UNCURATED_NOTE}" in graph.notes for t in uncurated)


def test_todo_draft_selections_are_skipped_with_a_note(graph):
    assert not [t for t in graph.transactions if t.kind == "draft_selection"]
    assert any("Cameron Boozer" in note and "TODO" in note for note in graph.notes)
    assert any("Karim Lopez" in note and "TODO" in note for note in graph.notes)


def test_curated_draft_selection_becomes_a_node_with_two_movements(
    feed_payload, resolvable_inputs
):
    snapshot, pick_events, corrections = resolvable_inputs
    pick_events.draft_selections[0].pick_id = "2026-R1-MEM"

    graph = build_graph(feed_payload, snapshot, pick_events, corrections)
    node = next(t for t in graph.transactions if t.kind == "draft_selection")
    movements = {
        (m.asset_type, m.asset_id): (m.from_holder, m.to_holder, m.contract_type)
        for m in graph.movements
        if m.transaction_id == node.id
    }

    assert node.id == "Draft-2026-06-24-1643409"
    assert node.source_key == "pick_events"
    assert movements[("pick", "2026-R1-MEM")] == ("MEM", "USED", None)
    assert movements[("player", "1643409")] == ("DRAFT", "MEM", None)


def test_a_referenced_pick_outside_the_snapshot_is_created_from_its_id(
    feed_payload, resolvable_inputs
):
    snapshot, pick_events, corrections = resolvable_inputs
    trade = next(t for t in pick_events.trades if t.group_key == "Trade 2025022")
    trade.picks = [
        PickMove(
            pick_id="2031-R2-UTA",
            from_holder="UTA",
            to_holder="MEM",
            protections="top-3",
        )
    ]

    graph = build_graph(feed_payload, snapshot, pick_events, corrections)
    created = next(p for p in graph.picks if p.id == "2031-R2-UTA")
    movement = next(m for m in graph.movements if m.asset_id == "2031-R2-UTA")

    assert (created.draft_year, created.round, created.original_team) == (2031, 2, "UTA")
    assert created.protections == "top-3"
    assert (movement.from_holder, movement.to_holder) == ("UTA", "MEM")
    assert movement.transaction_id == "Trade-2025022"


def test_pick_events_naming_an_unknown_group_key_raises(feed_payload, resolvable_inputs):
    snapshot, pick_events, corrections = resolvable_inputs
    pick_events.trades[0].group_key = "Trade 9999999"

    with pytest.raises(ValueError, match="Trade 9999999"):
        build_graph(feed_payload, snapshot, pick_events, corrections)


def test_rows_are_ordered_deterministically(graph):
    transaction_order = [(t.occurred_on, t.id) for t in graph.transactions]
    movement_order = [
        (m.occurred_on, m.transaction_id, m.asset_type, m.asset_id) for m in graph.movements
    ]

    assert transaction_order == sorted(transaction_order)
    assert movement_order == sorted(movement_order)
    assert [m.sequence for m in graph.movements] == list(range(1, len(graph.movements) + 1))
    assert [p.id for p in graph.players] == sorted(p.id for p in graph.players)
    assert [p.id for p in graph.picks] == sorted(p.id for p in graph.picks)


def test_build_graph_twice_yields_identical_serialized_output(
    feed_payload, resolvable_inputs
):
    snapshot, pick_events, corrections = resolvable_inputs

    first = graph_to_json(build_graph(feed_payload, snapshot, pick_events, corrections))
    second = graph_to_json(build_graph(feed_payload, snapshot, pick_events, corrections))

    assert first == second
    assert json.loads(first)["movements"][0]["transaction_id"] == BASELINE_ID


def test_every_movement_is_unique_per_transaction_and_asset(graph):
    keys = [(m.transaction_id, m.asset_type, m.asset_id) for m in graph.movements]

    assert len(set(keys)) == len(keys)


def test_corrections_can_drop_a_feed_row(feed_payload, resolvable_inputs):
    snapshot, pick_events, corrections = resolvable_inputs
    corrections.drop_rows = [DropRow(group_key="Waive 1140530", player_id=1641790)]

    graph = build_graph(feed_payload, snapshot, pick_events, corrections)

    assert "Waive-1140530" not in {t.id for t in graph.transactions}
    assert build_timelines(graph.movements)[("player", "1641790")][-1].holder == "MEM"


def test_players_are_named_from_the_feed(graph):
    names = {player.id: (player.full_name, player.slug) for player in graph.players}

    assert names[1629111] == ("Jock Landale", "jock-landale")
    assert names[1626156] == ("D'Angelo Russell", "dangelo-russell")
    assert names[203484] == ("Kentavious Caldwell-Pope", "kentavious-caldwell-pope")


def test_graph_to_dict_is_json_serializable(graph):
    json.dumps(graph_to_dict(graph))


class FakeCursor:
    def __init__(self, calls, rows):
        self._calls = calls
        self._rows = rows
        self._last = None

    def execute(self, sql, params=None):
        self._calls.append(("execute", sql, params))
        self._last = self._rows.pop(0) if self._rows else None

    def executemany(self, sql, params_seq):
        params = list(params_seq)
        self._calls.append(("executemany", sql, params))

    def fetchone(self):
        return self._last

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConnection:
    def __init__(self, rows=None):
        self.calls = []
        self.committed = False
        self._rows = list(rows or [])

    def cursor(self):
        return FakeCursor(self.calls, self._rows)

    def commit(self):
        self.committed = True


def test_load_graph_truncates_then_inserts_in_dependency_order(graph):
    conn = FakeConnection()

    load_graph(
        conn, graph, {"snapshot": 1, "feed": 2, "pick_events": 3, "corrections": 4}
    )

    assert [(kind, sql) for kind, sql, _ in conn.calls] == [
        ("execute", TRUNCATE_SQL),
        ("executemany", INSERT_PLAYER_SQL),
        ("executemany", INSERT_PICK_SQL),
        ("executemany", INSERT_TRANSACTION_SQL),
        ("executemany", INSERT_MOVEMENT_SQL),
    ]
    row_counts = [len(params) for _, _, params in conn.calls[1:]]
    assert row_counts == [
        len(graph.players),
        len(graph.picks),
        len(graph.transactions),
        len(graph.movements),
    ]
    assert conn.committed is True


def test_load_graph_stamps_each_transaction_with_its_source_record(graph):
    conn = FakeConnection()

    load_graph(
        conn, graph, {"snapshot": 11, "feed": 22, "pick_events": 33, "corrections": 44}
    )
    transaction_rows = conn.calls[3][2]
    source_ids = {row[0]: row[5] for row in transaction_rows}

    assert source_ids[BASELINE_ID] == 11
    assert source_ids["Signing-1139430"] == 22


def test_load_graph_refuses_a_missing_source_record_id(graph):
    with pytest.raises(DeriveError, match="source key"):
        load_graph(FakeConnection(), graph, {"feed": 1})


def test_select_feed_payload_reads_the_newest_record():
    payload = {"NBA_Player_Movement": {"rows": []}}
    conn = FakeConnection(rows=[(7, json.dumps(payload))])

    assert select_feed_payload(conn) == (7, payload)
    assert "order by fetched_at desc" in conn.calls[0][1]


def test_select_feed_payload_raises_when_nothing_is_stored():
    with pytest.raises(DeriveError, match="lineage fetch"):
        select_feed_payload(FakeConnection(rows=[]))
