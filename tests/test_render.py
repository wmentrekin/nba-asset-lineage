"""Tests for lineage.render: hand-written SVG from a graph.json export."""

import datetime as dt
import xml.etree.ElementTree as ET

import pytest

from lineage.derive import build_graph
from lineage.export import build_export
from lineage.render import render_svg

SVG_NS = "{http://www.w3.org/2000/svg}"


@pytest.fixture
def export(feed_payload, resolvable_inputs):
    snapshot, pick_events, corrections = resolvable_inputs
    graph = build_graph(feed_payload, snapshot, pick_events, corrections)
    return build_export(graph, snapshot.as_of)


@pytest.fixture
def svg(export):
    return render_svg(export)


def test_svg_parses_as_xml(svg):
    root = ET.fromstring(svg)
    assert root.tag == f"{SVG_NS}svg"


def test_one_lane_group_per_asset(svg, export):
    root = ET.fromstring(svg)
    lanes = root.findall(f'.//{SVG_NS}g[@class="lane"]')
    assert len(lanes) == len(export["assets"])


def test_one_node_group_per_transaction(svg, export):
    root = ET.fromstring(svg)
    node_groups = root.findall(f'.//{SVG_NS}g[@class="node"]')
    assert len(node_groups) == len(export["nodes"])


def test_landale_segment_ends_at_the_trade_nodes_x(svg):
    root = ET.fromstring(svg)
    rects = root.findall(f'.//{SVG_NS}rect[@class="segment"]')
    landale_open_segment = next(
        r
        for r in rects
        if r.get("data-asset-id") == "1629111" and r.get("data-to-node") == "Trade-2025022"
    )
    trade_node = next(
        g
        for g in root.findall(f'.//{SVG_NS}g[@class="node"]')
        if g.get("data-node-id") == "Trade-2025022"
    )
    trade_x = float(trade_node.find(f"{SVG_NS}line").get("x1"))
    segment_end_x = float(landale_open_segment.get("x")) + float(landale_open_segment.get("width"))

    assert segment_end_x == pytest.approx(trade_x, abs=0.01)


def test_render_is_byte_identical_across_two_runs(export):
    assert render_svg(export) == render_svg(export)


def test_all_text_is_escaped(export):
    export = dict(export)
    export["nodes"] = list(export["nodes"])
    export["nodes"][0] = {**export["nodes"][0], "description": "A & B <weird> \"quote\""}

    svg = render_svg(export)

    ET.fromstring(svg)  # must still parse
    assert "A & B <weird>" not in svg
