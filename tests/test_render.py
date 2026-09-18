"""Tests for lineage.render: hand-written SVG from a graph.json export.

The render is "slot lanes + node hubs": lanes are roster slots that get reused, and every
transaction that starts or ends a Memphis tenure is a hub with a curve per asset flowing in
and out. These tests derive the expected hubs and lane reuse straight from graph.json, so
they check the layout contract rather than restating the renderer's arithmetic.
"""

import os
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from lineage.derive import build_graph
from lineage.export import build_export
from lineage.render import render_svg

SVG_NS = "{http://www.w3.org/2000/svg}"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

TRADE = "Trade-2025022"
LANDALE = "1629111"
KYLE_ANDERSON = "203937"
FLAT_KINDS = {"baseline", "expiry"}
CONNECTOR_OFFSET = 24.0

# Builds the fixture-derived graph.json's SVG and prints it to stdout, so it can be run as a
# separate process per PYTHONHASHSEED value.
_RENDER_SCRIPT = """
import json, pathlib
from lineage.derive import build_graph, load_inputs
from lineage.export import build_export
from lineage.render import render_svg

snapshot, pick_events, corrections = load_inputs(pathlib.Path("data"))
feed = json.load(open("tests/fixtures/nba_player_movement_mem_2025_26.json"))
graph = build_graph(feed, snapshot, pick_events, corrections)
export = build_export(graph, snapshot.as_of)
import sys
sys.stdout.write(render_svg(export))
"""


@pytest.fixture
def export(feed_payload, resolvable_inputs):
    snapshot, pick_events, corrections = resolvable_inputs
    graph = build_graph(feed_payload, snapshot, pick_events, corrections)
    return build_export(graph, snapshot.as_of)


@pytest.fixture
def svg(export):
    return render_svg(export)


@pytest.fixture
def root(svg):
    return ET.fromstring(svg)


def _tenures(export):
    """(asset_id, start_node, end_node) per unbroken stretch of MEM ownership.

    Independent of render.py: read straight off the strands, merging consecutive MEM segments
    (a conversion or a re-signing is one tenure, not an exit and a re-entry).
    """
    found = []
    for strand in export["strands"]:
        segments = strand["segments"]
        index = 0
        while index < len(segments):
            if segments[index]["holder"] != "MEM":
                index += 1
                continue
            last = index
            while last + 1 < len(segments) and segments[last + 1]["holder"] == "MEM":
                last += 1
            found.append(
                (strand["asset_id"], segments[index]["from_node"], segments[last]["to_node"])
            )
            index = last + 1
    return found


def _hub_nodes(export):
    """{node_id: (out count, in count)} for every node the renderer must draw as a hub."""
    tenures = _tenures(export)
    hubs = {}
    for node in export["nodes"]:
        if node["kind"] in FLAT_KINDS:
            continue
        outs = sum(1 for _, _, end in tenures if end == node["id"])
        ins = sum(1 for _, start, _ in tenures if start == node["id"])
        if outs or ins:
            hubs[node["id"]] = (outs, ins)
    return hubs


def _hub(root, node_id):
    return next(
        group
        for group in root.findall(f'.//{SVG_NS}g[@class="hub"]')
        if group.get("data-node-id") == node_id
    )


def _hub_x(root, node_id):
    return float(_hub(root, node_id).find(f'{SVG_NS}circle[@class="hub-marker"]').get("cx"))


def _strand(root, asset_id, from_node):
    """The strand group for one tenure, identified by the node its first segment starts at."""
    return next(
        group
        for group in root.findall(f'.//{SVG_NS}g[@class="strand"]')
        if group.get("data-asset-id") == asset_id
        and group.find(f"{SVG_NS}rect").get("data-from-node") == from_node
    )


def _bar_extent(strand_group):
    bars = strand_group.findall(f'{SVG_NS}rect[@class="segment"]')
    left = min(float(bar.get("x")) for bar in bars)
    right = max(float(bar.get("x")) + float(bar.get("width")) for bar in bars)
    return left, right


def test_svg_parses_as_xml(root):
    assert root.tag == f"{SVG_NS}svg"


def test_lanes_are_reused_slots_not_one_per_asset(root, export):
    lanes = root.findall(f'.//{SVG_NS}g[@class="lane"]')

    assert 0 < len(lanes) < len(export["assets"])


def test_every_strand_sits_on_a_drawn_lane(root):
    lanes = {
        (group.get("data-band"), group.get("data-lane"))
        for group in root.findall(f'.//{SVG_NS}g[@class="lane"]')
    }
    strands = root.findall(f'.//{SVG_NS}g[@class="strand"]')

    assert strands
    for strand in strands:
        assert (strand.get("data-band"), strand.get("data-lane")) in lanes


def test_one_hub_per_node_that_starts_or_ends_a_memphis_tenure(root, export):
    drawn = {
        group.get("data-node-id") for group in root.findall(f'.//{SVG_NS}g[@class="hub"]')
    }

    assert drawn == set(_hub_nodes(export))


def test_connector_counts_match_each_hubs_in_and_out_assets(root, export):
    for node_id, (outs, ins) in _hub_nodes(export).items():
        hub = _hub(root, node_id)
        assert len(hub.findall(f'{SVG_NS}path[@class="out"]')) == outs, node_id
        assert len(hub.findall(f'{SVG_NS}path[@class="in"]')) == ins, node_id


@pytest.mark.parametrize(
    ("node_id", "expected"),
    [("Trade-2025022", (4, 4)), ("Trade-2026006", (1, 3))],
)
def test_the_known_trades_converge_and_diverge(root, export, node_id, expected):
    assert _hub_nodes(export)[node_id] == expected

    hub = _hub(root, node_id)
    outs = len(hub.findall(f'{SVG_NS}path[@class="out"]'))
    ins = len(hub.findall(f'{SVG_NS}path[@class="in"]'))

    assert (outs, ins) == expected


def test_a_departing_bar_stops_short_of_the_hub_and_gets_an_exit_cap(root):
    landale = _strand(root, LANDALE, "OPENING-2025-26")
    _, right = _bar_extent(landale)

    assert right == pytest.approx(_hub_x(root, TRADE) - CONNECTOR_OFFSET, abs=0.01)

    cap = next(
        group
        for group in root.findall(f'.//{SVG_NS}g[@class="exit"]')
        if group.get("data-asset-id") == LANDALE
    )
    assert cap.get("data-destination") == "UTA"
    assert cap.find(f'{SVG_NS}text[@class="exit-label"]').text == "UTA"


def test_an_arriving_bar_starts_past_the_hub_in_a_lane_the_trade_freed(root, export):
    anderson = _strand(root, KYLE_ANDERSON, TRADE)
    left, _ = _bar_extent(anderson)

    assert left == pytest.approx(_hub_x(root, TRADE) + CONNECTOR_OFFSET, abs=0.01)

    departing = [
        _strand(root, asset_id, start)
        for asset_id, start, end in _tenures(export)
        if end == TRADE
    ]
    freed = {(group.get("data-band"), group.get("data-lane")) for group in departing}

    assert len(freed) == 4
    assert (anderson.get("data-band"), anderson.get("data-lane")) in freed


def test_only_memphis_segments_are_drawn_as_bars(root, export):
    bars = root.findall(f'.//{SVG_NS}rect[@class="segment"]')
    memphis_segments = sum(
        1
        for strand in export["strands"]
        for segment in strand["segments"]
        if segment["holder"] == "MEM"
    )

    assert bars
    assert len(bars) == memphis_segments
    assert {bar.get("data-holder") for bar in bars} == {"MEM"}


def test_the_image_is_short_enough_to_read_at_full_width(root):
    assert int(root.get("width")) == 1600
    assert int(root.get("height")) <= 900


def test_render_is_byte_identical_across_two_runs(export):
    assert render_svg(export) == render_svg(export)


def _run_render_script(hash_seed: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", _RENDER_SCRIPT],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_render_is_byte_identical_across_processes_regardless_of_hash_seed():
    first = _run_render_script("1")
    second = _run_render_script("2")

    assert first == second


def test_all_text_is_escaped(export):
    export = dict(export)
    export["nodes"] = [
        {**node, "description": 'A & B <weird> "quote"'} if node["id"] == TRADE else node
        for node in export["nodes"]
    ]

    svg = render_svg(export)

    ET.fromstring(svg)  # must still parse
    assert "A & B <weird>" not in svg
    assert "A &amp; B &lt;weird&gt;" in svg
