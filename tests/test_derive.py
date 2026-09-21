"""Tests for lineage.derive: build_graph on the captured feed plus the curated data files."""

import datetime as dt
import json

import pytest

from lineage.derive import (
    CONTRACT_DRAFT_RIGHTS,
    HOLDER_VOID,
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
from lineage.corrections import Corrections, DropRow
from lineage.events import CuratedEvents, PickIn
from lineage.parse import FeedParseError
from lineage.snapshot import Snapshot, UnresolvedPlayerError
from lineage.timeline import Segment, build_timelines

BASELINE_ID = "OPENING-2025-26"


@pytest.fixture
def graph(feed_payload, resolvable_inputs):
    snapshot, curated, corrections = resolvable_inputs
    return build_graph(feed_payload, snapshot, curated, corrections)


def test_build_graph_fails_loudly_on_an_unresolvable_snapshot_player(
    feed_payload, curated_inputs
):
    snapshot, curated, corrections = curated_inputs
    snapshot = snapshot.model_copy(deep=True)
    # Jaylen Wells never appears by name or slug in the captured fixture, so nulling his
    # person_id here (regardless of what data/opening_snapshot_2025_26.json currently has)
    # reliably exercises the unresolvable-player path.
    wells = next(player for player in snapshot.players if player.name == "Jaylen Wells")
    wells.person_id = None

    with pytest.raises(UnresolvedPlayerError, match="Jaylen Wells"):
        build_graph(feed_payload, snapshot, curated, corrections)


def test_baseline_node_holds_the_whole_opening_inventory(graph):
    baseline = next(t for t in graph.transactions if t.id == BASELINE_ID)
    movements = [m for m in graph.movements if m.transaction_id == BASELINE_ID]

    assert baseline.kind == "baseline"
    assert baseline.occurred_on == dt.date(2025, 10, 22)
    assert baseline.description == "Opening-night roster and owned pick inventory"
    assert baseline.group_key is None
    assert baseline.source_key == "snapshot"
    assert sum(1 for m in movements if m.asset_type == "player") == 18
    assert sum(1 for m in movements if m.asset_type == "pick") == 16
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


def test_basseys_ten_day_expires_ten_days_later_since_nothing_else_moves_him(graph):
    timelines = build_timelines(graph.movements)

    assert timelines[("player", "1629646")] == [
        Segment(
            from_node="Signing-1139430",
            to_node="Expire-1139430",
            holder="MEM",
            contract_type="ten_day",
        ),
        Segment(from_node="Expire-1139430", to_node=None, holder="FA", contract_type=None),
    ]
    expiry = next(t for t in graph.transactions if t.id == "Expire-1139430")
    assert expiry.kind == "expiry"
    assert expiry.occurred_on == dt.date(2025, 11, 6)
    assert expiry.description == "10-day contract expired"
    assert expiry.group_key is None
    assert expiry.counterparties == []
    assert expiry.source_key == "feed"
    expiry_movement = next(m for m in graph.movements if m.transaction_id == "Expire-1139430")
    assert (expiry_movement.from_holder, expiry_movement.to_holder) == ("MEM", "FA")
    assert expiry_movement.contract_type is None


def test_kolokos_two_ten_days_eleven_days_apart_each_get_their_own_expiry(graph):
    timelines = build_timelines(graph.movements)

    assert timelines[("player", "1631132")] == [
        Segment(
            from_node="Signing-1142557",
            to_node="Expire-1142557",
            holder="MEM",
            contract_type="ten_day",
        ),
        Segment(from_node="Expire-1142557", to_node="Signing-1143016", holder="FA", contract_type=None),
        Segment(
            from_node="Signing-1143016",
            to_node="Expire-1143016",
            holder="MEM",
            contract_type="ten_day",
        ),
        Segment(from_node="Expire-1143016", to_node=None, holder="FA", contract_type=None),
    ]
    first_expiry = next(t for t in graph.transactions if t.id == "Expire-1142557")
    second_expiry = next(t for t in graph.transactions if t.id == "Expire-1143016")
    assert first_expiry.occurred_on == dt.date(2026, 1, 1)  # 11 days > 10: expires first
    assert second_expiry.occurred_on == dt.date(2026, 1, 12)


def test_tyler_burtons_two_ten_days_eleven_days_apart_also_both_expire(graph):
    expiry_ids = {t.id for t in graph.transactions if t.id in ("Expire-1146960", "Expire-1147490")}
    assert expiry_ids == {"Expire-1146960", "Expire-1147490"}
    first_expiry = next(t for t in graph.transactions if t.id == "Expire-1146960")
    second_expiry = next(t for t in graph.transactions if t.id == "Expire-1147490")
    assert first_expiry.occurred_on == dt.date(2026, 3, 22)
    assert second_expiry.occurred_on == dt.date(2026, 4, 2)


def test_adama_bals_ten_days_exactly_ten_days_apart_supersede_instead_of_expiring(graph):
    """03-28 -> 04-07 is exactly 10 days: the second signing supersedes the first (a
    movement dated == the expiry date wins the tie), so only the second signing expires."""
    expiry_ids = {t.id for t in graph.transactions if t.id in ("Expire-1147703", "Expire-1148392")}
    assert expiry_ids == {"Expire-1148392"}

    timelines = build_timelines(graph.movements)
    assert timelines[("player", "1642380")] == [
        Segment(
            from_node="Signing-1147703",
            to_node="Signing-1148392",
            holder="MEM",
            contract_type="ten_day",
        ),
        Segment(
            from_node="Signing-1148392",
            to_node="Expire-1148392",
            holder="MEM",
            contract_type="ten_day",
        ),
        Segment(from_node="Expire-1148392", to_node=None, holder="FA", contract_type=None),
    ]


def test_expiries_add_twelve_transactions_to_the_fixture(graph):
    """The fixture's 16 MEM ten-day signings minus the 4 that are superseded by a same-
    or next-day movement (Rupert's two-way, Jarreau's and Adama Bal's and Williamson's
    second 10-day, each exactly 10 days out) leaves 12 synthetic expiry transactions."""
    expiries = [t for t in graph.transactions if t.kind == "expiry"]
    assert len(expiries) == 12
    # 46 feed-derived transactions (baseline + parsed groups + 12 expiries), plus the 3
    # curated draft-selection nodes and the 1 curated contract_void event.
    assert len(graph.transactions) == 46 + 3 + 1 == 50


def test_movements_add_up_across_baseline_curated_trades_draft_and_void(graph):
    """Baseline (18 players + 16 picks) plus the 6 curated pick-in movements (LAL 2027 R1,
    PHX 2031 R1, DAL 2029 R2, WAS 2029 R2, GSW 2030 R1, WAS 2033 R2) plus the 3 draft
    selections (a pick-used and a player-drafted movement each) plus the 1 contract_void,
    on top of the feed's own non-baseline movements."""
    baseline_movements = [m for m in graph.movements if m.transaction_id == BASELINE_ID]
    assert len(baseline_movements) == 34

    curated_pick_ins = {
        (m.transaction_id, m.asset_id)
        for m in graph.movements
        if m.asset_type == "pick" and m.from_holder != "MEM" and m.to_holder == "MEM"
    }
    assert curated_pick_ins >= {
        ("Trade-2025022", "2027-R1-LAL"),
        ("Trade-2025022", "2031-R1-PHX"),
        ("Trade-2026006", "2029-R2-DAL"),
        ("Trade-2026006", "2029-R2-WAS"),
        ("Trade-2026006", "2030-R1-GSW"),
        ("Trade-2026006", "2033-R2-WAS"),
    }

    draft_movements = [m for m in graph.movements if m.transaction_id.startswith("Draft-")]
    assert len(draft_movements) == 6  # 3 selections x (pick used + player drafted)

    void_movements = [m for m in graph.movements if m.transaction_id.startswith("Void-")]
    assert len(void_movements) == 1

    assert len(graph.movements) == 107


def test_trade_2025022_has_four_players_and_two_picks_in_each_direction(graph):
    movements = [m for m in graph.movements if m.transaction_id == "Trade-2025022"]

    players_in = [m for m in movements if m.asset_type == "player" and m.to_holder == "MEM"]
    players_out = [m for m in movements if m.asset_type == "player" and m.from_holder == "MEM"]
    picks_in = [m for m in movements if m.asset_type == "pick" and m.to_holder == "MEM"]

    assert len(players_in) == 4
    assert len(players_out) == 4
    assert len(picks_in) == 2
    assert len(movements) == 10


def test_trade_2026006_has_four_curated_pick_movements(graph):
    pick_movements = [
        m for m in graph.movements if m.transaction_id == "Trade-2026006" and m.asset_type == "pick"
    ]

    assert {m.asset_id for m in pick_movements} == {
        "2029-R2-DAL",
        "2029-R2-WAS",
        "2030-R1-GSW",
        "2033-R2-WAS",
    }
    assert all((m.from_holder, m.to_holder) == (m.from_holder, "MEM") for m in pick_movements)


def test_a_trade_with_no_curated_picks_and_no_footnotes_keeps_the_uncurated_note(
    feed_payload, resolvable_inputs
):
    from lineage.events import UNCURATED_NOTE

    snapshot, curated, corrections = resolvable_inputs
    trade = next(t for t in curated.trades if t.group_key == "Trade 2025037")
    trade.footnotes = []

    graph = build_graph(feed_payload, snapshot, curated, corrections)
    transaction = next(t for t in graph.transactions if t.id == "Trade-2025037")

    assert transaction.note == UNCURATED_NOTE
    assert f"Trade-2025037: {UNCURATED_NOTE}" in graph.notes


def test_a_trade_with_footnotes_but_no_curated_picks_gets_a_footnotes_only_note(graph):
    transaction = next(t for t in graph.transactions if t.id == "Trade-2025037")

    assert transaction.note.startswith("draft consideration: footnotes only: ")
    assert "Justinian Jessup" in transaction.note


def test_a_trade_with_curated_picks_folds_footnotes_after_the_marker_text(graph):
    transaction = next(t for t in graph.transactions if t.id == "Trade-2025022")

    assert transaction.note.startswith("draft consideration: MEM<-UTA")
    assert "footnotes:" in transaction.note
    assert "most favorable of UTA/CLE/MIN" in transaction.note


def test_a_trade_with_no_feed_markers_gets_a_plain_footnotes_note_and_no_w1(graph):
    """Trade 2025063 (Morant-to-Portland) moved no picks and has no feed draft-consideration
    leg at all, so it is not "uncurated": its note carries the footnote without the
    `draft consideration:` prefix that would make it look like an unresolved marker."""
    transaction = next(t for t in graph.transactions if t.id == "Trade-2025063")

    assert transaction.note == (
        "footnotes: No draft picks changed hands (Morant for Grant + Murray + $1M cash to POR)."
    )
    assert not transaction.note.startswith("draft consideration:")


def test_curated_draft_selection_becomes_a_node_with_two_movements(graph):
    node = next(t for t in graph.transactions if t.id == "Draft-2026-06-23-2026-R1-MEM")
    movements = {
        (m.asset_type, m.asset_id): (m.from_holder, m.to_holder, m.contract_type)
        for m in graph.movements
        if m.transaction_id == node.id
    }

    assert node.kind == "draft_selection"
    assert node.source_key == "events"
    assert node.description.startswith("Drafted Cameron Boozer #3 with 2026-R1-MEM.")
    assert movements[("pick", "2026-R1-MEM")] == ("MEM", "USED", None)
    assert movements[("player", "1643409")] == ("DRAFT", "MEM", CONTRACT_DRAFT_RIGHTS)


def test_saunders_gets_a_deterministic_synthetic_player_id_and_a_note(graph):
    node = next(t for t in graph.transactions if t.id == "Draft-2026-06-24-2026-R2-MEM")
    movement = next(
        m
        for m in graph.movements
        if m.transaction_id == node.id and m.asset_type == "player"
    )

    assert movement.asset_id == "-202632"
    assert movement.contract_type == CONTRACT_DRAFT_RIGHTS
    assert any("-202632" in note for note in graph.notes)
    assert any(p.full_name == "Richie Saunders" for p in graph.players if p.id == -202632)


def test_boozer_and_lopez_re_sign_from_draft_rights_to_standard_at_mem(graph):
    timelines = build_timelines(graph.movements)

    boozer = timelines[("player", "1643409")]
    assert boozer[0].holder == "MEM" and boozer[0].contract_type == CONTRACT_DRAFT_RIGHTS
    assert boozer[1].holder == "MEM" and boozer[1].contract_type == "standard"
    assert boozer[1].from_node == "Signing-1153118"

    lopez = timelines[("player", "1643510")]
    assert lopez[0].holder == "MEM" and lopez[0].contract_type == CONTRACT_DRAFT_RIGHTS
    assert lopez[1].holder == "MEM" and lopez[1].contract_type == "standard"


def test_clarke_void_resolves_from_the_baseline_mem_holder(graph):
    timelines = build_timelines(graph.movements)

    assert timelines[("player", "1629634")] == [
        Segment(
            from_node=BASELINE_ID, to_node="Void-2026-07-03-1629634", holder="MEM",
            contract_type="standard",
        ),
        Segment(
            from_node="Void-2026-07-03-1629634", to_node=None, holder=HOLDER_VOID,
            contract_type=None,
        ),
    ]
    node = next(t for t in graph.transactions if t.id == "Void-2026-07-03-1629634")
    assert node.kind == "contract_void"
    assert node.source_key == "events"
    assert "Brandon Clarke" in node.description


def test_a_referenced_pick_outside_the_snapshot_is_created_from_its_id(
    feed_payload, resolvable_inputs
):
    snapshot, curated, corrections = resolvable_inputs
    trade = next(t for t in curated.trades if t.group_key == "Trade 2025022")
    trade.picks_in = trade.picks_in + [
        PickIn(pick_id="2031-R2-UTA", from_holder="UTA", protections="top-3")
    ]

    graph = build_graph(feed_payload, snapshot, curated, corrections)
    created = next(p for p in graph.picks if p.id == "2031-R2-UTA")
    movement = next(m for m in graph.movements if m.asset_id == "2031-R2-UTA")

    assert (created.draft_year, created.round, created.original_team) == (2031, 2, "UTA")
    assert created.protections == "top-3"
    assert (movement.from_holder, movement.to_holder) == ("UTA", "MEM")
    assert movement.transaction_id == "Trade-2025022"


def test_curated_events_naming_an_unknown_group_key_raises(feed_payload, resolvable_inputs):
    snapshot, curated, corrections = resolvable_inputs
    curated.trades[0].group_key = "Trade 9999999"

    with pytest.raises(ValueError, match="Trade 9999999"):
        build_graph(feed_payload, snapshot, curated, corrections)


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
    snapshot, curated, corrections = resolvable_inputs

    first = graph_to_json(build_graph(feed_payload, snapshot, curated, corrections))
    second = graph_to_json(build_graph(feed_payload, snapshot, curated, corrections))

    assert first == second
    assert json.loads(first)["movements"][0]["transaction_id"] == BASELINE_ID


def test_every_movement_is_unique_per_transaction_and_asset(graph):
    keys = [(m.transaction_id, m.asset_type, m.asset_id) for m in graph.movements]

    assert len(set(keys)) == len(keys)


def test_corrections_can_drop_a_feed_row(feed_payload, resolvable_inputs):
    snapshot, curated, corrections = resolvable_inputs
    corrections.drop_rows = [DropRow(group_key="Waive 1140530", player_id=1641790)]

    graph = build_graph(feed_payload, snapshot, curated, corrections)

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
        conn, graph, {"snapshot": 1, "feed": 2, "events": 3, "corrections": 4}
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

    # The fake connection exercised a real graph carrying every new kind and contract type
    # this task adds, so this doubles as the "load includes the new kinds/contract types"
    # check: nothing about truncate/insert ordering needed to change for them.
    transaction_rows = conn.calls[3][2]
    kinds = {row[2] for row in transaction_rows}
    assert {"draft_selection", "contract_void"} <= kinds
    movement_rows = conn.calls[4][2]
    contract_types = {row[5] for row in movement_rows}
    assert "draft_rights" in contract_types


def test_load_graph_stamps_each_transaction_with_its_source_record(graph):
    conn = FakeConnection()

    load_graph(
        conn, graph, {"snapshot": 11, "feed": 22, "events": 33, "corrections": 44}
    )
    transaction_rows = conn.calls[3][2]
    source_ids = {row[0]: row[5] for row in transaction_rows}

    assert source_ids[BASELINE_ID] == 11
    assert source_ids["Signing-1139430"] == 22
    assert source_ids["Draft-2026-06-23-2026-R1-MEM"] == 33
    assert source_ids["Void-2026-07-03-1629634"] == 33


def test_load_graph_inserts_each_transaction_note(feed_payload, resolvable_inputs):
    snapshot, curated, corrections = resolvable_inputs
    graph = build_graph(feed_payload, snapshot, curated, corrections)
    conn = FakeConnection()

    load_graph(
        conn, graph, {"snapshot": 11, "feed": 22, "events": 33, "corrections": 44}
    )
    transaction_rows = conn.calls[3][2]
    notes = {row[0]: row[7] for row in transaction_rows}

    assert notes[BASELINE_ID] is None
    assert notes["Trade-2025022"].startswith("draft consideration: MEM<-UTA")
    assert notes["Trade-2026014"].startswith("draft consideration: footnotes only: ")


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


def test_build_graph_ignores_a_malformed_row_from_another_team(
    feed_payload, feed_payload_with_malformed_row, resolvable_inputs
):
    """Regression: CI died on `derive failed: no position word in description: 'Denver
    Nuggets signed  Bryce Hopkins to a Two-Way Contract.'` while scanning the full feed."""
    snapshot, curated, corrections = resolvable_inputs

    with_bad_row = build_graph(
        feed_payload_with_malformed_row, snapshot, curated, corrections
    )
    clean = build_graph(feed_payload, snapshot, curated, corrections)

    # The Denver row is not a Memphis group, so it changes nothing about the graph.
    assert graph_to_json(with_bad_row) == graph_to_json(clean)
    assert 1641801 not in {player.id for player in with_bad_row.players}


def test_a_malformed_memphis_row_still_fails_loudly(feed_payload, resolvable_inputs):
    """Tolerance is for the identity index only; Memphis movements stay strict."""
    snapshot, curated, corrections = resolvable_inputs
    rows = feed_payload["NBA_Player_Movement"]["rows"]
    bad = dict(next(r for r in rows if r["GroupSort"] == "Waive 1140530"))
    bad["TRANSACTION_DESCRIPTION"] = "Memphis Grizzlies did something inscrutable."
    rows[rows.index(next(r for r in rows if r["GroupSort"] == "Waive 1140530"))] = bad

    with pytest.raises(FeedParseError, match="inscrutable"):
        build_graph(feed_payload, snapshot, curated, corrections)


def _synthetic_row(group_key, transaction_type, description, player_id, player_slug):
    return {
        "GroupSort": group_key,
        "TEAM_ID": 1610612763.0,  # MEM
        "Additional_Sort": 0.0,
        "PLAYER_ID": float(player_id),
        "PLAYER_SLUG": player_slug,
        "TEAM_SLUG": "grizzlies",
        "TRANSACTION_DATE": "2026-01-02T00:00:00",
        "Transaction_Type": transaction_type,
        "TRANSACTION_DESCRIPTION": description,
    }


def test_contract_converted_and_award_on_waivers_produce_the_expected_movements():
    """Derive-level regression for the two real feed shapes B4 review flagged: a
    ContractConverted row (MEM->MEM, standard) and an AwardOnWaivers row (FA->MEM,
    standard) - both drawn from real observed phrasings, not synthesized text."""
    snapshot = Snapshot(team="MEM", season="2025-26", as_of=dt.date(2026, 1, 1), players=[], picks=[])
    curated = CuratedEvents(trades=[], draft_selections=[], events=[])
    corrections = Corrections()
    feed_payload = {
        "NBA_Player_Movement": {
            "rows": [
                _synthetic_row(
                    "ContractConverted 9001",
                    "ContractConverted",
                    "Memphis Grizzlies converted the contract of guard A.J. Lawson to an "
                    "NBA Contract.",
                    9001,
                    "aj-lawson",
                ),
                _synthetic_row(
                    "AwardOnWaivers 9002",
                    "AwardOnWaivers",
                    "Memphis Grizzlies claimed guard Tony Wroten off waivers.",
                    9002,
                    "tony-wroten",
                ),
            ]
        }
    }

    graph = build_graph(feed_payload, snapshot, curated, corrections)
    movements = {movement.asset_id: movement for movement in graph.movements}

    converted = movements["9001"]
    assert (converted.from_holder, converted.to_holder, converted.contract_type) == (
        "MEM",
        "MEM",
        "standard",
    )
    claimed = movements["9002"]
    assert (claimed.from_holder, claimed.to_holder, claimed.contract_type) == (
        "FA",
        "MEM",
        "standard",
    )
