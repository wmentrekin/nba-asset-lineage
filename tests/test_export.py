"""Tests for lineage.export: the graph.json contract."""

import datetime as dt
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

snapshot, pick_events, corrections = load_inputs(pathlib.Path("data"))
feed = json.load(open("tests/fixtures/nba_player_movement_mem_2025_26.json"))
graph = build_graph(feed, snapshot, pick_events, corrections)
export = build_export(graph, snapshot.as_of)
import sys
sys.stdout.write(json.dumps(export, sort_keys=True))
"""


@pytest.fixture
def graph(feed_payload, resolvable_inputs):
    snapshot, pick_events, corrections = resolvable_inputs
    return build_graph(feed_payload, snapshot, pick_events, corrections)


@pytest.fixture
def export(graph):
    return build_export(graph, dt.date(2025, 10, 22))


def test_window_spans_as_of_to_the_last_transaction(export):
    assert export["window"] == {"start": "2025-10-22", "end": "2026-09-08"}


def test_nodes_are_ordered_by_date_then_id_and_carry_the_contract_fields(export):
    nodes = export["nodes"]
    order = [(n["date"], n["id"]) for n in nodes]
    assert order == sorted(order)

    baseline = nodes[0]
    assert baseline["id"] == "OPENING-2025-26"
    assert set(baseline) == {"id", "date", "kind", "description", "counterparties", "note"}

    trade = next(n for n in nodes if n["id"] == "Trade-2025022")
    assert trade["note"] == "draft consideration: picks not yet curated"


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
    from lineage.picks import PickMove

    snapshot, pick_events, corrections = resolvable_inputs
    trade = next(t for t in pick_events.trades if t.group_key == "Trade 2025022")
    trade.picks = [PickMove(pick_id="2031-R2-UTA", from_holder="UTA", to_holder="MEM")]

    graph = build_graph(feed_payload, snapshot, pick_events, corrections)
    export = build_export(graph, snapshot.as_of)

    asset = next(a for a in export["assets"] if a["id"] == "2031-R2-UTA")
    assert asset == {"id": "2031-R2-UTA", "type": "pick", "label": "2031 R2 (UTA)"}


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
