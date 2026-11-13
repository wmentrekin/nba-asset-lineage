"""Tests for lineage.export: the graph.json contract."""

import os
import pathlib
import subprocess
import sys

import pytest

from lineage.derive import build_graph
from lineage.export import build_export, pick_label

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

_EXPORT_SCRIPT = """
import json, pathlib
from lineage.derive import build_graph, load_inputs
from lineage.export import build_export

snapshot, curated, corrections = load_inputs(pathlib.Path("data"))
feed = json.load(open("tests/fixtures/nba_player_movement_mem_2025_26.json"))
graph = build_graph(feed, snapshot, curated, corrections)
export = build_export(graph, snapshot)
import sys
sys.stdout.write(json.dumps(export, sort_keys=True))
"""


@pytest.fixture
def snapshot(resolvable_inputs):
    snapshot, _, _ = resolvable_inputs
    return snapshot


@pytest.fixture
def graph(feed_payload, resolvable_inputs):
    snapshot, curated, corrections = resolvable_inputs
    return build_graph(feed_payload, snapshot, curated, corrections)


@pytest.fixture
def export(graph, snapshot):
    return build_export(graph, snapshot)


def test_window_spans_as_of_to_the_last_transaction(export):
    assert export["window"] == {"start": "2025-10-22", "end": "2026-09-08"}


def test_nodes_are_ordered_by_date_then_id_and_carry_the_contract_fields(export):
    nodes = export["nodes"]
    order = [(n["date"], n["id"]) for n in nodes]
    assert order == sorted(order)

    baseline = nodes[0]
    assert baseline["id"] == "OPENING-2025-26"
    assert set(baseline) == {
        "id", "date", "kind", "description", "counterparties", "note", "hidden",
    }

    trade = next(n for n in nodes if n["id"] == "Trade-2025022")
    assert trade["note"].startswith("draft consideration: MEM<-UTA")

    uncurated = next(n for n in nodes if n["id"] == "Trade-2025037")
    assert uncurated["note"].startswith("draft consideration: footnotes only: ")

    draft = next(n for n in nodes if n["id"] == "Draft-2026-06-23-2026-R1-MEM")
    assert draft["kind"] == "draft_selection"

    void = next(n for n in nodes if n["id"] == "Void-2026-07-03-1629634")
    assert void["kind"] == "contract_void"


def test_assets_are_players_then_picks_ordered_by_label(export):
    assets = export["assets"]
    types = [a["type"] for a in assets]
    split = types.index("pick") if "pick" in types else len(types)

    assert types[:split] == ["player"] * split
    assert types[split:] == ["pick"] * (len(types) - split)
    assert [a["label"] for a in assets[:split]] == sorted(a["label"] for a in assets[:split])
    assert [a["label"] for a in assets[split:]] == sorted(a["label"] for a in assets[split:])


def test_pick_label_format():
    from lineage.derive import Pick

    pick = Pick(id="2030-R1-ORL", draft_year=2030, round=1, original_team="ORL", protections=None)
    assert pick_label(pick) == "2030 R1 (ORL)"


def test_strands_are_in_asset_order_and_match_the_timeline(export):
    assets = export["assets"]
    strands = export["strands"]

    assert [(s["asset_id"], s["asset_type"]) for s in strands] == [
        (a["id"], a["type"]) for a in assets
    ]

    landale = next(s for s in strands if s["asset_id"] == "1629111")
    assert landale["segments"] == [
        {
            "from_node": "OPENING-2025-26",
            "to_node": "Trade-2025022",
            "holder": "MEM",
            "contract_type": "standard",
        },
        {"from_node": "Trade-2025022", "to_node": None, "holder": "UTA", "contract_type": None},
    ]


def test_a_referenced_pick_becomes_a_labelled_asset(feed_payload, resolvable_inputs):
    from lineage.events import PickIn

    snapshot, curated, corrections = resolvable_inputs
    trade = next(t for t in curated.trades if t.group_key == "Trade 2025022")
    trade.picks_in = trade.picks_in + [PickIn(pick_id="2031-R2-UTA", from_holder="UTA")]

    graph = build_graph(feed_payload, snapshot, curated, corrections)
    export = build_export(graph, snapshot)

    asset = next(a for a in export["assets"] if a["id"] == "2031-R2-UTA")
    assert asset == {
        "id": "2031-R2-UTA",
        "type": "pick",
        "label": "2031 R2 (UTA)",
        "sort_key": [2031, 2, 1, "UTA"],
    }


def test_draft_rights_contract_type_flows_through_export(export):
    strands = export["strands"]
    boozer = next(s for s in strands if s["asset_id"] == "1643409")

    assert boozer["segments"][0]["contract_type"] == "draft_rights"
    assert boozer["segments"][1]["contract_type"] == "standard"


def test_every_player_asset_carries_a_tenure_start(export):
    players = [a for a in export["assets"] if a["type"] == "player"]
    assert players
    for player in players:
        assert isinstance(player["tenure_start"], str) and player["tenure_start"]


def test_tenure_start_for_snapshot_baseline_players(export):
    players = {a["id"]: a for a in export["assets"] if a["type"] == "player"}

    assert players["1628991"]["tenure_start"] == "2018-07-01"  # Jaren Jackson Jr.
    # Conversion restarts tenure: mem_since is already the conversion date.
    assert players["1629723"]["tenure_start"] == "2020-11-22"  # John Konchar


def test_tenure_start_for_players_acquired_during_the_season(export):
    players = {a["id"]: a for a in export["assets"] if a["type"] == "player"}

    assert players["203937"]["tenure_start"] == "2026-02-03"  # Kyle Anderson, traded in
    assert players["1643409"]["tenure_start"] == "2026-06-23"  # Cameron Boozer, draft day
    assert players["1629646"]["tenure_start"] == "2025-10-27"  # Charles Bassey, 10-day signing
    assert players["1643563"]["tenure_start"] == "2026-06-24"  # Richie Saunders, draft day


def test_prosper_tier_change_at_conversion(export):
    players = {a["id"]: a for a in export["assets"] if a["type"] == "player"}
    prosper = players["1641765"]

    assert prosper["tenure_tier_changes"] == [
        {
            "node": "Signing-1146537",
            "date": "2026-03-04",
            "to_contract_type": "standard",
        }
    ]


def test_boozer_tier_change_at_rookie_signing(export):
    players = {a["id"]: a for a in export["assets"] if a["type"] == "player"}
    boozer = players["1643409"]

    assert boozer["tenure_tier_changes"] == [
        {
            "node": "Signing-1153118",
            "date": "2026-07-13",
            "to_contract_type": "standard",
        }
    ]


def test_pick_sort_key(export):
    picks = {a["id"]: a for a in export["assets"] if a["type"] == "pick"}
    assert picks["2030-R1-ORL"]["sort_key"] == [2030, 1, 1, "ORL"]
    assert picks["2027-R1-MEM"]["sort_key"] == [2027, 1, 0, "MEM"]


def test_2027_picks_sort_mem_r1_then_lal_r1_then_mem_r2(export):
    keys = {
        a["id"]: a["sort_key"]
        for a in export["assets"]
        if a["type"] == "pick" and a["sort_key"][0] == 2027
    }
    assert sorted(keys, key=keys.get) == ["2027-R1-MEM", "2027-R1-LAL", "2027-R2-MEM"]


HIDDEN_PLAYERS = {
    "Charles Bassey", "Kobe Bufkin", "Christian Koloko", "Lawson Lovering", "Tyler Burton",
    "DeJon Jarreau", "Adama Bal", "Lucas Williamson", "Dariq Whitehead", "Toby Okani",
}


def test_hidden_players_are_the_ten_day_only_signings(export):
    players = [a for a in export["assets"] if a["type"] == "player"]
    assert all(isinstance(a["hidden"], bool) for a in players)
    assert {a["label"] for a in players if a["hidden"]} == HIDDEN_PLAYERS


@pytest.mark.parametrize(
    "name",
    ["Rayan Rupert", "Georges Niang", "Eric Gordon", "Kyle Anderson", "Taj Gibson"],
)
def test_visible_players_with_other_arrivals_or_contracts(export, name):
    asset = next(a for a in export["assets"] if a["label"] == name)
    assert asset["hidden"] is False


def test_nodes_are_hidden_only_when_every_movement_touches_hidden_players(export, graph):
    hidden_ids = {a["id"] for a in export["assets"] if a["type"] == "player" and a["hidden"]}
    nodes = {n["id"]: n for n in export["nodes"]}
    assert nodes["Signing-" + "1153251"]["hidden"] is False
    for node_id, node in nodes.items():
        moves = [m for m in graph.movements if m.transaction_id == node_id]
        expected = all(m.asset_type == "player" and m.asset_id in hidden_ids for m in moves)
        assert node["hidden"] is expected
    assert any(n["hidden"] for n in nodes.values())
    assert nodes["Trade-2026014"]["hidden"] is False


def test_horizon_node_and_strands(export):
    node = next(n for n in export["nodes"] if n["id"] == "Horizon-2033")
    assert (node["date"], node["kind"], node["hidden"]) == (
        "2026-06-25", "pick_horizon", False,
    )
    assert node["description"] == "2033 picks become tradeable"
    strands = {s["asset_id"]: s["segments"] for s in export["strands"]}
    for pick_id in ("2033-R1-MEM", "2033-R2-MEM"):
        assert strands[pick_id] == [
            {"from_node": "Horizon-2033", "to_node": None, "holder": "MEM", "contract_type": None}
        ]


def test_snapshot_player_without_mem_since_fails_loudly(feed_payload, resolvable_inputs):
    snapshot, curated, corrections = resolvable_inputs
    snapshot = snapshot.model_copy(deep=True)
    jjj = next(player for player in snapshot.players if player.name == "Jaren Jackson Jr.")
    jjj.mem_since = None

    graph = build_graph(feed_payload, snapshot, curated, corrections)

    with pytest.raises(ValueError, match="Jaren Jackson Jr."):
        build_export(graph, snapshot)


def test_export_is_byte_identical_across_processes_regardless_of_hash_seed():
    def run(hash_seed: str) -> str:
        result = subprocess.run(
            [sys.executable, "-c", _EXPORT_SCRIPT],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    assert run("1") == run("2")
