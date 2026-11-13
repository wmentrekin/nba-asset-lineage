"""Tests for lineage.render: hand-written SVG from a graph.json export.

The render is the "compacting stack": a row is a rank, not a slot, so the assertions here are
about *order* and *movement* — who sits above whom at a given x, and how a strand's y steps
when the stack compacts or when it crosses from one band into another. Expected orders are
derived from graph.json (tenure_start, sort_key) rather than restated, so the tests check the
layout contract rather than the renderer's arithmetic.
"""

import copy
import datetime as dt
import os
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from lineage.derive import build_graph
from lineage.export import build_export
from lineage.render import PLOT_X0, PLOT_X1, SHIFT_GAP, TRANSITION, Scale, render_svg

SVG_NS = "{http://www.w3.org/2000/svg}"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

BASELINE = "OPENING-2025-26"
TRADE = "Trade-2025022"  # Feb 3: JJJ, Konchar, Williams and Landale out
WAIVER = "Waive-1140530"  # Nov 16: PJ Hall's two-way waived...
MASHACK_SIGNING = "Signing-1140528"  # ...and Jahmai Mashack's two-way signed the same day
CONVERSION = "Signing-1146537"  # Mar 4: Prosper's two-way becomes a real contract
FIRST_DRAFT = "Draft-2026-06-23-2026-R1-MEM"
LAST_DRAFT = "Draft-2026-06-24-2026-R2-MEM"
HIDDEN_PLAYER = "1629646"  # Charles Bassey: one 10-day contract, nothing else
HIDDEN_NODE = "Signing-1139430"  # his 10-day signing
JJJ = "1628991"
MORANT = "1629630"
PROSPER = "1641765"
BOOZER = "1643409"

# Builds the fixture-derived graph.json's SVG and prints it to stdout, so it can be run as a
# separate process per PYTHONHASHSEED value.
_RENDER_SCRIPT = """
import json, pathlib, sys
from lineage.derive import build_graph, load_inputs
from lineage.export import build_export
from lineage.render import render_svg

snapshot, pick_events, corrections = load_inputs(pathlib.Path("data"))
feed = json.load(open("tests/fixtures/nba_player_movement_mem_2025_26.json"))
graph = build_graph(feed, snapshot, pick_events, corrections)
sys.stdout.write(render_svg(build_export(graph, snapshot)))
"""

POINT = re.compile(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")


@pytest.fixture
def export(feed_payload, resolvable_inputs):
    snapshot, pick_events, corrections = resolvable_inputs
    graph = build_graph(feed_payload, snapshot, pick_events, corrections)
    return build_export(graph, snapshot)


@pytest.fixture
def svg(export):
    return render_svg(export)


@pytest.fixture
def root(svg):
    return ET.fromstring(svg)


@pytest.fixture
def bands(root):
    """{band: (top, rows, row height)} straight off the drawn band groups."""
    return {
        group.get("data-band"): (
            float(group.get("data-top")),
            float(group.get("data-rows")),
            float(group.get("data-row-height")),
        )
        for group in root.findall(f'.//{SVG_NS}g[@class="band"]')
    }


def _points(element):
    return [(float(x), float(y)) for x, y in POINT.findall(element.get("d"))]


def _strand(root, asset_id):
    return next(
        group
        for group in root.findall(f'.//{SVG_NS}g[@class="strand"]')
        if group.get("data-asset-id") == asset_id
    )


def _strand_points(root, asset_id):
    points = []
    for path in _strand(root, asset_id).findall(f'{SVG_NS}path[@class="segment"]'):
        points.extend(_points(path))
    return points


def _y_at(points, x):
    """The row y a strand sits on at `x`: its last vertex at or before that x."""
    found = None
    for px, py in points:
        if px <= x + 0.01:
            found = py
    return found if found is not None else points[0][1]


def _shift_start(points):
    """The x where a strand's first y change begins: the `L` vertex before its first curve.

    A curve is `L x1,y1 C mid,y1 mid,y2 x2,y2`, so the first point at a new y is the second
    control point, two points after the curve's start.
    """
    first_y = points[0][1]
    index = next(i for i, (_, y) in enumerate(points) if abs(y - first_y) > 0.01)
    return points[index - 2][0]


def _x_range(points):
    xs = [px for px, _ in points]
    return min(xs), max(xs)


def _band_at(bands, y):
    for band, (top, rows, row_height) in bands.items():
        if top - 1 <= y <= top + rows * row_height + 1:
            return band
    return None


def _rank(bands, band, y):
    top, _, row_height = bands[band]
    return round((y - top - row_height / 2) / row_height, 2)


def _hub(root, node_id):
    return next(
        group
        for group in root.findall(f'.//{SVG_NS}g[@class="hub"]')
        if group.get("data-node-id") == node_id
    )


def _hub_x(root, node_id):
    return float(_hub(root, node_id).find(f'{SVG_NS}circle[@class="hub-marker"]').get("cx"))


def _hub_fill(root, node_id):
    return _hub(root, node_id).find(f'{SVG_NS}circle[@class="hub-marker"]').get("fill")


def _stack_at(root, bands, x, band):
    """[asset id] top to bottom of the strands sitting in `band` at `x`."""
    rows = []
    for group in root.findall(f'.//{SVG_NS}g[@class="strand"]'):
        points = _strand_points(root, group.get("data-asset-id"))
        low, high = _x_range(points)
        if not low - 0.01 <= x <= high + 0.01:
            continue
        y = _y_at(points, x)
        if _band_at(bands, y) == band:
            rows.append((y, group.get("data-asset-id")))
    return [asset_id for _, asset_id in sorted(rows)]


def _labels(export):
    return {asset["id"]: asset["label"] for asset in export["assets"]}


def _baseline_holdings(export, band):
    """Asset ids MEM held at the baseline in `band`, in the order the layout should stack them."""
    assets = {asset["id"]: asset for asset in export["assets"]}
    held = []
    for strand in export["strands"]:
        first = strand["segments"][0] if strand["segments"] else None
        if not first or first["from_node"] != BASELINE or first["holder"] != "MEM":
            continue
        asset = assets[strand["asset_id"]]
        if asset["type"] == "pick":
            found = "pick"
        else:
            found = "two_way" if first["contract_type"] == "two_way" else "roster"
        if found != band:
            continue
        if band == "pick":
            key = (*asset["sort_key"], asset["id"])
        else:
            key = (asset["tenure_start"], asset["label"], asset["id"])
        held.append((key, asset["id"]))
    return [asset_id for _, asset_id in sorted(held)]


def _node_x(root, node_id):
    return _hub_x(root, node_id)


def test_svg_parses_as_xml(root):
    assert root.tag == f"{SVG_NS}svg"


def test_the_image_is_2400_wide(root):
    assert int(root.get("width")) == 2400


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


def test_no_exit_cap_carries_visible_destination_text(root):
    caps = root.findall(f'.//{SVG_NS}g[@class="exit"]')

    assert caps
    for group in caps:
        assert group.get("data-destination")
        assert not group.findall(f"{SVG_NS}text")


def test_every_drawn_segment_is_a_memphis_strand_tagged_with_its_contract_type(root):
    segments = root.findall(f'.//{SVG_NS}path[@class="segment"]')

    assert segments
    assert {segment.get("data-holder") for segment in segments} == {"MEM"}
    for segment in segments:
        assert segment.get("data-contract-type") is not None
        assert segment.get("stroke-width") == "7.0"


def test_two_way_and_standard_strands_differ_in_color_not_in_weight(root):
    two_way = _strand(root, "1642914").find(f'{SVG_NS}path[@class="segment"]')
    standard = _strand(root, MORANT).find(f'{SVG_NS}path[@class="segment"]')

    assert two_way.get("data-contract-type") == "two_way"
    assert standard.get("data-contract-type") == "standard"
    assert two_way.get("stroke") != standard.get("stroke")
    assert two_way.get("stroke-width") == standard.get("stroke-width")


def test_hub_marker_fill_differs_between_a_trade_and_a_waiver(root):
    assert _hub_fill(root, TRADE) != _hub_fill(root, WAIVER)


def test_a_trade_hub_converges_its_departures_and_diverges_its_arrivals(root, export):
    tenures = [
        strand["asset_id"]
        for strand in export["strands"]
        for segment in strand["segments"]
        if segment["holder"] == "MEM" and segment["to_node"] == TRADE
    ]
    hub = _hub(root, TRADE)

    assert len(hub.findall(f'{SVG_NS}path[@class="out"]')) == len(tenures)
    assert hub.findall(f'{SVG_NS}path[@class="in"]')


# --- Render v4: the stack, its order, and the band crossings -------------------------------


def test_opening_night_roster_is_stacked_by_tenure_longest_serving_on_top(root, bands, export):
    expected = _baseline_holdings(export, "roster")
    labels = _labels(export)

    stacked = _stack_at(root, bands, 101.0, "roster")

    assert [labels[asset_id] for asset_id in stacked] == [labels[a] for a in expected]
    assert labels[stacked[0]] == "Jaren Jackson Jr."
    assert _rank(bands, "roster", _y_at(_strand_points(root, JJJ), 101.0)) == 0
    assert labels[stacked[-1]] == "Jock Landale"


def test_the_two_way_band_holds_the_three_two_way_players_in_tenure_order(root, bands, export):
    labels = _labels(export)

    stacked = _stack_at(root, bands, 101.0, "two_way")

    assert [labels[asset_id] for asset_id in stacked] == [
        labels[asset_id] for asset_id in _baseline_holdings(export, "two_way")
    ]
    assert set(labels[asset_id] for asset_id in stacked) == {
        "Javon Small",
        "PJ Hall",
        "Olivier-Maxence Prosper",
    }


def test_the_stack_closes_up_when_a_player_above_leaves(root, bands):
    x = _node_x(root, TRADE)
    morant = _strand_points(root, MORANT)

    before = _rank(bands, "roster", _y_at(morant, x - 5))
    shift = _shift_start(morant)
    after = _rank(bands, "roster", _y_at(morant, shift + TRANSITION + 1))

    # Jaren Jackson Jr. sat directly above him and left in this trade; the knock-on shift waits
    # a clear gap past the trade rather than starting at its hub.
    assert _y_at(_strand_points(root, JJJ), x - 5) < _y_at(morant, x - 5)
    assert shift >= x + SHIFT_GAP - 0.01
    assert after == before - 1


def test_a_conversion_lifts_the_strand_out_of_the_two_way_band(root, bands):
    x = _node_x(root, CONVERSION)
    prosper = _strand_points(root, PROSPER)

    assert _band_at(bands, _y_at(prosper, x - 5)) == "two_way"
    assert _band_at(bands, _y_at(prosper, x + TRANSITION + 1)) == "roster"

    types = [
        (segment.get("data-from-node"), segment.get("data-contract-type"))
        for segment in _strand(root, PROSPER).findall(f'{SVG_NS}path[@class="segment"]')
    ]
    assert (BASELINE, "two_way") in types
    assert (CONVERSION, "standard") in types


def test_a_drafted_pick_leaves_the_picks_band_and_continues_as_the_player(root, bands):
    x = _node_x(root, FIRST_DRAFT)
    pick = _strand_points(root, "2026-R1-MEM")
    player = _strand_points(root, BOOZER)

    assert _band_at(bands, _y_at(pick, x - 5)) == "pick"
    assert _x_range(pick)[1] == pytest.approx(x, abs=0.01)

    # The player picks the strand up exactly where the pick put it down.
    assert _x_range(player)[0] == pytest.approx(x, abs=0.01)
    assert player[0][1] == pytest.approx(_y_at(pick, x), abs=0.01)
    assert _band_at(bands, _y_at(player, x + TRANSITION + 1)) == "roster"

    # A pick that becomes a player is not also capped off as having left Memphis.
    assert not [
        group
        for group in root.findall(f'.//{SVG_NS}g[@class="exit"]')
        if group.get("data-asset-id") == "2026-R1-MEM"
    ]


def _pick_blocks(root):
    """{year: pick-year group} straight off the drawn picks band."""
    return {
        int(group.get("data-year")): group
        for group in root.findall(f'.//{SVG_NS}g[@class="pick-year"]')
    }


def _block_offsets(group):
    return [
        (float(x), float(offset))
        for x, offset in (item.split(":") for item in group.get("data-offsets").split())
    ]


def _date_x(export, date):
    scale = Scale(
        dt.date.fromisoformat(export["window"]["start"]),
        dt.date.fromisoformat(export["window"]["end"]),
        PLOT_X0,
        PLOT_X1,
    )
    return scale(dt.date.fromisoformat(date))


def test_the_2027_block_reserves_a_slot_per_pick_in_sort_key_order(root, bands):
    blocks = _pick_blocks(root)
    _, _, row_height = bands["pick"]

    assert blocks[2027].get("data-slots").split() == ["2027-R1-MEM", "2027-R1-LAL", "2027-R2-MEM"]

    # Before the trade the LAL slot is already there, empty, between the two MEM picks.
    own_first = _strand_points(root, "2027-R1-MEM")
    own_second = _strand_points(root, "2027-R2-MEM")
    assert _y_at(own_second, 101.0) - _y_at(own_first, 101.0) == pytest.approx(2 * row_height)

    after = _node_x(root, TRADE) + 100
    lal = _strand_points(root, "2027-R1-LAL")
    assert _y_at(lal, after) - _y_at(own_first, after) == pytest.approx(row_height)
    assert _y_at(own_second, after) - _y_at(lal, after) == pytest.approx(row_height)


def test_a_traded_in_pick_fills_its_slot_and_nothing_else_in_its_year_moves(root):
    x = _node_x(root, TRADE)
    block_shift = _block_offsets(_pick_blocks(root)[2027])[1][0]
    lal = _strand_points(root, "2027-R1-LAL")

    # The arriving pick holds one y from its connector's end to its block's one shift.
    entry = _x_range(lal)[0]
    assert {round(y, 2) for px, y in lal if entry <= px <= block_shift} == {
        round(_y_at(lal, entry), 2)
    }
    for asset_id in ("2027-R1-MEM", "2027-R2-MEM"):
        points = _strand_points(root, asset_id)
        assert _y_at(points, x - 5) == _y_at(points, x + 100)
        assert _shift_start(points) == pytest.approx(block_shift)


def test_after_the_draft_the_2026_block_is_gone_and_every_block_below_moves_up_together(
    root, bands
):
    blocks = _pick_blocks(root)
    draft_x = _node_x(root, LAST_DRAFT)

    assert float(blocks[2026].get("data-last-x")) == pytest.approx(draft_x)

    moves = {year: _block_offsets(blocks[year]) for year in range(2027, 2034)}
    assert all(len(offsets) == 2 for offsets in moves.values())
    shift_xs = {round(offsets[1][0], 2) for offsets in moves.values()}
    deltas = {offsets[1][1] - offsets[0][1] for offsets in moves.values()}
    assert len(shift_xs) == 1 and shift_xs.pop() >= draft_x + SHIFT_GAP
    assert len(deltas) == 1 and deltas.pop() < 0

    # The strands follow their blocks: every pick held across the shift rises by the same y.
    rises = set()
    for year in range(2027, 2033):
        for asset_id in blocks[year].get("data-slots").split():
            points = _strand_points(root, asset_id)
            if _x_range(points)[1] >= PLOT_X1:
                rises.add(round(_y_at(points, PLOT_X1) - _y_at(points, draft_x - 1), 2))
    assert len(rises) == 1


def test_the_2033_block_appears_at_its_horizon_below_2032(root, export):
    blocks = _pick_blocks(root)
    horizon = next(node for node in export["nodes"] if node["kind"] == "pick_horizon")
    x = _date_x(export, horizon["date"])

    assert float(blocks[2033].get("data-first-x")) == pytest.approx(x, abs=0.01)
    assert _x_range(_strand_points(root, "2033-R1-MEM"))[0] == pytest.approx(x, abs=0.01)
    assert _block_offsets(blocks[2033])[0][1] > _block_offsets(blocks[2032])[0][1]
    # A horizon is not a transaction with two sides, so it gets no marker.
    assert horizon["id"] not in {
        group.get("data-node-id") for group in root.findall(f'.//{SVG_NS}g[@class="hub"]')
    }


def test_hidden_players_and_their_nodes_are_not_drawn(root, export):
    hidden = [asset for asset in export["assets"] if asset.get("hidden")]
    assert HIDDEN_PLAYER in [asset["id"] for asset in hidden]

    drawn_ids = {
        group.get("data-asset-id")
        for group in root.iter(f"{SVG_NS}g")
        if group.get("data-asset-id") is not None
    }
    texts = " ".join(text.text or "" for text in root.iter(f"{SVG_NS}text"))
    for asset in hidden:
        assert asset["id"] not in drawn_ids
        assert asset["label"] not in texts

    hubs = {group.get("data-node-id") for group in root.findall(f'.//{SVG_NS}g[@class="hub"]')}
    assert HIDDEN_NODE not in hubs
    hidden_nodes = [node["id"] for node in export["nodes"] if node.get("hidden")]
    assert hidden_nodes
    assert not [node_id for node_id in hidden_nodes if node_id in hubs]


def test_a_knock_on_shift_waits_a_clear_gap_past_the_node_that_caused_it(root):
    # PJ Hall's waiver and Mashack's signing share one x; Prosper steps up into Hall's row,
    # but only well clear of Mashack's signing marker.
    x = _node_x(root, WAIVER)
    assert _node_x(root, MASHACK_SIGNING) == pytest.approx(x)
    prosper = _strand_points(root, PROSPER)

    assert _shift_start(prosper) >= x + SHIFT_GAP - 0.01
    assert _y_at(prosper, x + SHIFT_GAP - 1) == _y_at(prosper, x - 5)


def test_the_two_way_band_never_exceeds_the_three_contracts_the_rules_allow(root, bands, export):
    # Three rows by rule, plus at most one transient row where a same-day signing waits for
    # the row a waived two-way left to close up.
    assert 3 <= bands["two_way"][1] <= 4

    for node in export["nodes"]:
        hub = [
            group
            for group in root.findall(f'.//{SVG_NS}g[@class="hub"]')
            if group.get("data-node-id") == node["id"]
        ]
        if not hub:
            continue
        x = _hub_x(root, node["id"])
        assert len(_stack_at(root, bands, x + 40, "two_way")) <= 3


def test_synthetic_contract_void_and_draft_rights_get_their_family_colors(export):
    synthetic = copy.deepcopy(export)
    synthetic["nodes"].append(
        {
            "id": "Void-9999999",
            "date": synthetic["window"]["end"],
            "kind": "contract_void",
            "description": "Synthetic contract void",
            "counterparties": [],
            "note": None,
        }
    )
    synthetic["assets"].append(
        {
            "id": "9999999",
            "type": "player",
            "label": "Synthetic Player",
            "tenure_start": "2025-10-22",
            "tenure_tier_changes": [],
        }
    )
    synthetic["strands"].append(
        {
            "asset_id": "9999999",
            "asset_type": "player",
            "segments": [
                {
                    "from_node": BASELINE,
                    "to_node": "Void-9999999",
                    "holder": "MEM",
                    "contract_type": "draft_rights",
                },
            ],
        }
    )

    root = ET.fromstring(render_svg(synthetic))

    assert _hub_fill(root, "Void-9999999") == _hub_fill(root, WAIVER)
    synthetic_strand = _strand(root, "9999999").find(f'{SVG_NS}path[@class="segment"]')
    assert synthetic_strand.get("data-contract-type") == "draft_rights"
    assert synthetic_strand.get("stroke") != _strand(root, MORANT).find(
        f'{SVG_NS}path[@class="segment"]'
    ).get("stroke")


def test_a_dropped_label_gets_a_numbered_marker_and_a_matching_legend_entry(root):
    markers = root.findall(f'.//{SVG_NS}g[@class="short-tenure-marker"]')
    assert markers

    legend_texts = [
        text.text or ""
        for text in root.findall(f'.//{SVG_NS}g[@class="short-tenure-legend"]/{SVG_NS}text')
    ]
    assert legend_texts

    assert {marker.get("data-number") for marker in markers} == {
        text.split(".", 1)[0] for text in legend_texts
    }
    first = markers[0]
    entry = next(text for text in legend_texts if text.startswith(f"{first.get('data-number')}."))
    assert first.find(f"{SVG_NS}title").text in entry
    assert "→" in entry
