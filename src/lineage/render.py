"""Hand-written SVG rendering of graph.json: no plotting library, no PNG.

Layout ("compacting stack"): x is time (linear, window.start to window.end) and a row is a
*rank*, not a slot. Only Memphis tenure is drawn. At every transaction date the assets
Memphis currently holds are re-ranked inside three bands stacked top to bottom — the roster
(standard / 10-day / draft-rights contracts), the three reserved two-way rows, and the
Memphis-owned picks — so a strand's y is a step function of x. Every rank change is a short
cubic S-curve just after the transaction that caused it: when a player leaves, everyone below
him slides up one row; when one arrives he lands at the bottom of the stack.

Roster and two-way rows are ordered by tenure, longest-serving on top, which is why an
arrival always enters at the bottom. A two-way conversion and a draft selection are the two
places a strand crosses bands: the strand leaves its two-way row (or its pick row, continuing
as the drafted player) and curves up into the bottom of the roster band, changing color at
that node. Picks are ordered by (round, draft year, original team) with a half-row gap
between draft years, so a traded-in pick is inserted at its sorted position rather than
appended.

Stroke color encodes contract type (categorical, never thickness — every strand is the same
width); hub markers are colored by the kind of transaction they represent, and trades keep
the v3 convergence/divergence: connectors run from each departing strand's current y into the
hub and back out to each arriving strand's row.

Two runs over the same graph.json produce byte-identical output: every list here is built in
a fixed order derived from graph.json's own ordering, no set is ever iterated for emission,
and nothing reads the clock.
"""

import datetime as dt
import json
import math
import pathlib
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape, quoteattr

WIDTH = 1600
PLOT_X0 = 100
PLOT_X1 = WIDTH - 90
# A tenure MEM still holds runs past the axis end into this overhang, so an asset acquired on
# the window's last day still gets a visible strand.
OPEN_END_X = PLOT_X1 + 44
TITLE_Y = 22
NODE_LABEL_Y = 58
TOP_MARGIN = 110

# One rank = one row. Rows are dense (the stack compacts), so they are a touch tighter than
# v3's reusable lanes while the strand itself stays the same visual weight.
ROW_HEIGHT = 13.0
BAND_GAP = 22.0
# The picks band separates draft years by half a row so the year groups read as groups.
YEAR_GAP_ROWS = 0.5
# NBA rule: a team may carry three two-way contracts, so that band is three rows whatever the
# data says.
TWO_WAY_ROWS = 3

# A rank change is drawn as a cubic S-curve this wide, starting at the node that caused it.
TRANSITION = 24.0
# At a trade a strand stops this far short of the hub; the gap is where the connector lives.
CONNECTOR_OFFSET = 24.0
MIN_RUN = 4.0
HUB_RADIUS = 4.5
STRAND_WIDTH = 7.0

NODE_LABEL_MIN_GAP = 40.0
NODE_LABEL_STAGGER = 13
NODE_LABEL_LEVELS = 3
MONTH_ROTATE_THRESHOLD = 12

LABEL_FONT = 9
# Helvetica/Arial averages ~0.52em per character; used to decide whether a row leaves enough
# room for a tenure's full name, since there is no text-measuring API in plain SVG.
LABEL_CHAR_WIDTH = LABEL_FONT * 0.52
MIN_LABEL_WIDTH = 24.0

# Nodes of these kinds never get a marker: a baseline is the left edge of the window and an
# expiry is a 10-day contract simply lapsing, so neither has two sides to route between.
FLAT_NODE_KINDS = frozenset({"baseline", "expiry"})
LABELLED_NODE_KINDS = frozenset({"trade", "draft_selection"})

# Hub-marker kind families (owner feedback round 2): every transaction kind that starts or
# ends a tenure falls into exactly one of these, or is a plain baseline/expiry end-cap.
SIGNING_KINDS = frozenset({"signing", "two_way_signing", "two_way_conversion", "ten_day"})
WAIVER_KINDS = frozenset({"waiver", "contract_void"})

# Colors: the default validated categorical palette (see the dataviz skill), used in its
# documented fixed order across two independent categorical encodings that appear side by
# side in this chart — contract type (strands, slots 1-4) then pick strands (slot 5) then hub
# kind (markers, slots 6-8), plus one deliberate reuse (draft selection hubs echo the
# draft-rights strand color, since both are "about the draft"). Never cycled, never reordered.
COLOR_STANDARD = "#2a78d6"  # slot 1 blue — MEM's one long-running hue, kept from v1/v2
COLOR_TWO_WAY = "#eb6834"  # slot 2 orange
COLOR_TEN_DAY = "#1baf7a"  # slot 3 aqua
COLOR_DRAFT_RIGHTS = "#eda100"  # slot 4 yellow
COLOR_PICK = "#e87ba4"  # slot 5 magenta — muted fifth color for the picks band
COLOR_HUB_TRADE = "#008300"  # slot 6 green
COLOR_HUB_SIGNING = "#4a3aa7"  # slot 7 violet
COLOR_HUB_WAIVER = "#e34948"  # slot 8 red
COLOR_HUB_DRAFT_SELECTION = COLOR_DRAFT_RIGHTS  # deliberate reuse: both are "the draft"

CONTRACT_COLORS = {
    "standard": COLOR_STANDARD,
    None: COLOR_STANDARD,
    "two_way": COLOR_TWO_WAY,
    "ten_day": COLOR_TEN_DAY,
    "draft_rights": COLOR_DRAFT_RIGHTS,
}

# Connectors stay a neutral, darker ink so the colored hub marker (not the curve leading into
# it) is what reads as "trade" / "signing" / "waiver" / "draft selection".
COLOR_CONNECTOR = "#52514e"
COLOR_CAP = "#52514e"
COLOR_TEXT_PRIMARY = "#0b0b0b"
COLOR_TEXT_SECONDARY = "#52514e"
COLOR_TEXT_MUTED = "#898781"
COLOR_SURFACE = "#fcfcfb"
COLOR_GRID = "#e1e0d9"
COLOR_AXIS = "#c3c2b7"

ROSTER, TWO_WAY, PICK = "roster", "two_way", "pick"
BANDS = (ROSTER, TWO_WAY, PICK)
BAND_TITLES = {ROSTER: "roster", TWO_WAY: "two-way", PICK: "picks"}

TITLE = "Memphis Grizzlies asset lineage, 2025-26 → today"

# Legend layout: two fixed rows of color swatches (contract types, then hub kinds + the plain
# exit marker), plus a variable-height block of numbered markers for tenures whose full name
# didn't fit.
LEGEND_TOP_PAD = 32.0
LEGEND_ROW_GAP = 20.0
LEGEND_BOTTOM_PAD = 14.0
NUMBERED_LEGEND_GAP = 18.0
NUMBERED_ROW_HEIGHT = 13.0
NUMBERED_COL_WIDTH = 228.0


def _parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


class Scale:
    """Linear date -> x mapping over [x0, x1]."""

    def __init__(self, start: dt.date, end: dt.date, x0: float, x1: float):
        self.start = start
        self.span_days = max((end - start).days, 1)
        self.x0 = x0
        self.x1 = x1

    def __call__(self, date: dt.date) -> float:
        t = (date - self.start).days / self.span_days
        return self.x0 + t * (self.x1 - self.x0)


def _month_starts(start: dt.date, end: dt.date) -> list[dt.date]:
    """Every month boundary inside the window; a partial first month has no tick."""
    months = []
    year, month = start.year, start.month
    while dt.date(year, month, 1) <= end:
        first = dt.date(year, month, 1)
        if first >= start:
            months.append(first)
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _segment_band(asset_type: str, segment: dict[str, Any]) -> str:
    if asset_type == "pick":
        return PICK
    return TWO_WAY if segment["contract_type"] == "two_way" else ROSTER


def _pick_sort_key(asset: dict[str, Any]) -> tuple[int, int, str]:
    """A pick's (round, draft year, original team) ordering key, as graph.json carries it."""
    key = asset["sort_key"]
    return (int(key[0]), int(key[1]), str(key[2]))


@dataclass
class Tenure:
    """One unbroken stretch of MEM ownership of one asset: the thing that holds a rank."""

    asset_id: str
    asset_type: str
    label: str
    order: int
    segments: list[dict[str, Any]]
    start_node: str
    end_node: str | None
    exit_holder: str | None
    sort_start: dt.date
    pick_key: tuple[int, int, str] | None
    restart_nodes: list[str]
    # Filled in by the rank walk and the placement pass.
    placements: list[tuple[float, str, float]] = field(default_factory=list)
    lead: float = 0.0
    lag: float = 0.0
    start_x: float = 0.0
    end_x: float = 0.0
    entry_y: float | None = None
    continues_as: str | None = None
    bounds: list[float] = field(default_factory=list)

    def sort_key(self) -> tuple[Any, ...]:
        if self.pick_key is not None:
            return (*self.pick_key, self.asset_id)
        return (self.sort_start, self.label, self.asset_id)

    def y_at(self, x: float, band_tops: dict[str, float]) -> float:
        """The row y this strand sits on at `x` (its latest placement at or before `x`)."""
        current = self.placements[0]
        for placement in self.placements:
            if placement[0] <= x + 0.001:
                current = placement
        return _row_y(band_tops, current[1], current[2])

    def first_y(self, band_tops: dict[str, float]) -> float:
        return _row_y(band_tops, self.placements[0][1], self.placements[0][2])

    def last_y(self, band_tops: dict[str, float]) -> float:
        return _row_y(band_tops, self.placements[-1][1], self.placements[-1][2])


def _row_y(band_tops: dict[str, float], band: str, rows: float) -> float:
    return band_tops[band] + rows * ROW_HEIGHT + ROW_HEIGHT / 2


def _restart_nodes(asset: dict[str, Any], segments: list[dict[str, Any]]) -> list[str]:
    """Nodes where a tenure's clock restarts: a two-way converting to a real contract.

    `tenure_tier_changes` (when the export carries it) names every MEM->MEM contract-type
    change; only the ones leaving a two-way deal restart the tenure, and the segment list is
    what says which side the change came from.
    """
    from_two_way = [
        segments[index]["to_node"]
        for index in range(len(segments) - 1)
        if segments[index]["holder"] == "MEM"
        and segments[index + 1]["holder"] == "MEM"
        and segments[index]["contract_type"] == "two_way"
        and segments[index + 1]["contract_type"] != "two_way"
    ]
    announced = [change["node"] for change in asset.get("tenure_tier_changes", [])]
    return [node for node in from_two_way if node in announced]


def _tenures(
    assets: list[dict[str, Any]],
    strands: list[dict[str, Any]],
    node_date: dict[str, dt.date],
    window_start: dt.date,
) -> list[Tenure]:
    """Split every strand into its MEM tenures, in graph.json asset order.

    Consecutive MEM segments (a two-way conversion, a re-signing, a back-to-back 10-day) are
    one tenure with an internal boundary, not an exit and a re-entry.
    """
    segments_by_asset = {strand["asset_id"]: strand["segments"] for strand in strands}
    tenures: list[Tenure] = []
    for order, asset in enumerate(assets):
        segments = segments_by_asset.get(asset["id"], [])
        restarts = _restart_nodes(asset, segments)
        first = True
        index = 0
        while index < len(segments):
            if segments[index]["holder"] != "MEM":
                index += 1
                continue
            last = index
            while last + 1 < len(segments) and segments[last + 1]["holder"] == "MEM":
                last += 1
            after = segments[last + 1] if last + 1 < len(segments) else None
            start_node = segments[index]["from_node"]
            arrival = node_date.get(start_node, window_start)
            # graph.json's tenure_start is how long Memphis has held the asset, which can
            # predate the window; a later stint starts its own clock at the day it began.
            if first and asset["type"] == "player":
                sort_start = _parse_date(asset["tenure_start"])
            else:
                sort_start = arrival
            tenures.append(
                Tenure(
                    asset_id=asset["id"],
                    asset_type=asset["type"],
                    label=asset["label"],
                    order=order,
                    segments=segments[index : last + 1],
                    start_node=start_node,
                    end_node=segments[last]["to_node"],
                    exit_holder=after["holder"] if after else None,
                    sort_start=sort_start,
                    pick_key=_pick_sort_key(asset) if asset["type"] == "pick" else None,
                    restart_nodes=[node for node in restarts if node is not None],
                )
            )
            first = False
            index = last + 1
    return tenures


def _draft_continuations(
    nodes: list[dict[str, Any]], tenures: list[Tenure]
) -> dict[str, Tenure]:
    """{departing pick tenure asset id: the player tenure it becomes} at each draft node.

    A draft selection is one continuous strand on the page even though graph.json models it as
    a pick ending (holder USED) and a player beginning. Pairing is positional within the node,
    which is unambiguous here: a draft node moves exactly one pick and creates one player.
    """
    pairs: dict[str, Tenure] = {}
    for node in nodes:
        if node["kind"] != "draft_selection":
            continue
        picks = [t for t in tenures if t.end_node == node["id"] and t.asset_type == "pick"]
        players = [t for t in tenures if t.start_node == node["id"] and t.asset_type == "player"]
        for pick, player in zip(picks, players):
            pairs[pick.asset_id] = player
            pick.continues_as = player.asset_id
    return pairs


def _year_gaps(ordered: list[Tenure]) -> list[float]:
    """Cumulative half-row offsets: a gap opens wherever the draft year changes."""
    offsets = []
    gaps = 0.0
    for index, tenure in enumerate(ordered):
        if index and tenure.pick_key[1] != ordered[index - 1].pick_key[1]:
            gaps += YEAR_GAP_ROWS
        offsets.append(gaps)
    return offsets


def _walk_ranks(
    tenures: list[Tenure],
    nodes: list[dict[str, Any]],
    scale: Scale,
) -> dict[str, float]:
    """Assign every tenure its rank on every interval; return each band's height in rows.

    Dates, not nodes, are the beat: two transactions on the same day land on the same x, so
    they are applied together (departures, then tenure restarts, then arrivals) and produce one
    re-ranking. Inside a date the nodes are still walked in (date, id) order.
    """
    arrivals: dict[str, list[Tenure]] = {}
    departures: dict[str, list[Tenure]] = {}
    moves: dict[str, list[tuple[Tenure, str, str]]] = {}
    restarts: dict[str, list[Tenure]] = {}
    for tenure in tenures:
        bands = [_segment_band(tenure.asset_type, segment) for segment in tenure.segments]
        arrivals.setdefault(tenure.start_node, []).append(tenure)
        if tenure.end_node is not None:
            departures.setdefault(tenure.end_node, []).append(tenure)
        for index in range(len(bands) - 1):
            if bands[index] != bands[index + 1]:
                node = tenure.segments[index]["to_node"]
                moves.setdefault(node, []).append((tenure, bands[index], bands[index + 1]))
        for node in tenure.restart_nodes:
            restarts.setdefault(node, []).append(tenure)

    band_of: dict[int, str] = {
        id(tenure): _segment_band(tenure.asset_type, tenure.segments[0]) for tenure in tenures
    }
    occupancy: dict[str, list[Tenure]] = {band: [] for band in BANDS}
    heights = {band: 0.0 for band in BANDS}

    dates: list[dt.date] = []
    by_date: dict[dt.date, list[dict[str, Any]]] = {}
    for node in nodes:
        date = _parse_date(node["date"])
        if date not in by_date:
            by_date[date] = []
            dates.append(date)
        by_date[date].append(node)

    for date in dates:
        same_day = by_date[date]
        for node in same_day:
            for tenure in departures.get(node["id"], []):
                occupancy[band_of[id(tenure)]].remove(tenure)
            for tenure, from_band, _ in moves.get(node["id"], []):
                occupancy[from_band].remove(tenure)
        for node in same_day:
            for tenure in restarts.get(node["id"], []):
                tenure.sort_start = date
        for node in same_day:
            for tenure, _, to_band in moves.get(node["id"], []):
                occupancy[to_band].append(tenure)
                band_of[id(tenure)] = to_band
            for tenure in arrivals.get(node["id"], []):
                band = _segment_band(tenure.asset_type, tenure.segments[0])
                occupancy[band].append(tenure)
                band_of[id(tenure)] = band

        x = scale(date)
        for band in BANDS:
            ordered = sorted(occupancy[band], key=lambda tenure: tenure.sort_key())
            occupancy[band] = ordered
            offsets = _year_gaps(ordered) if band == PICK else [0.0] * len(ordered)
            for rank, tenure in enumerate(ordered):
                rows = rank + offsets[rank]
                if not tenure.placements or tenure.placements[-1][1:] != (band, rows):
                    tenure.placements.append((x, band, rows))
            if ordered:
                heights[band] = max(heights[band], len(ordered) + offsets[-1])
    heights[TWO_WAY] = max(heights[TWO_WAY], float(TWO_WAY_ROWS))
    return heights


def _band_tops(heights: dict[str, float]) -> dict[str, float]:
    top = float(TOP_MARGIN)
    tops = {}
    for band in BANDS:
        tops[band] = top
        if heights[band]:
            top += heights[band] * ROW_HEIGHT + BAND_GAP
    return tops


def _place(
    tenures: list[Tenure],
    node_x: dict[str, float],
    node_kind: dict[str, str],
    band_tops: dict[str, float],
    continuations: dict[str, Tenure],
) -> None:
    """Fill in each tenure's horizontal extent and, for a drafted player, its entry y."""
    for tenure in tenures:
        start_kind = node_kind.get(tenure.start_node)
        if start_kind == "baseline":
            raw_start = float(PLOT_X0)
        else:
            raw_start = node_x[tenure.start_node]
        lead = CONNECTOR_OFFSET if start_kind == "trade" else 0.0
        if tenure.end_node is None:
            raw_end, lag = float(OPEN_END_X), 0.0
        else:
            raw_end = node_x[tenure.end_node]
            lag = CONNECTOR_OFFSET if node_kind.get(tenure.end_node) == "trade" else 0.0
        span = raw_end - raw_start
        if lead + lag > 0 and span - lead - lag < MIN_RUN:
            # Two trades closer together than 2*CONNECTOR_OFFSET: shrink both curves to fit.
            shrink = min(1.0, max(0.0, (span - MIN_RUN) / (lead + lag)))
            lead, lag = lead * shrink, lag * shrink
        tenure.lead, tenure.lag = lead, lag
        tenure.start_x = raw_start + lead
        tenure.end_x = max(raw_end - lag, raw_start + lead)
        # Every internal contract boundary is a MEM->MEM node, so it always has an x.
        bounds = [tenure.start_x]
        for segment in tenure.segments[:-1]:
            bounds.append(min(max(node_x[segment["to_node"]], bounds[-1]), tenure.end_x))
        bounds.append(max(tenure.end_x, bounds[-1]))
        tenure.bounds = bounds

    for pick_asset_id, player in continuations.items():
        pick = next(t for t in tenures if t.asset_id == pick_asset_id and t.continues_as)
        player.entry_y = pick.last_y(band_tops)


def _geometry(tenure: Tenure, band_tops: dict[str, float]) -> list[tuple[str, float, ...]]:
    """The strand's shape: alternating ("H", x1, x2, y) runs and ("S", x1, x2, y1, y2) curves.

    A rank change at x is drawn as a cubic starting at x, so the curve reads as "this node
    caused it"; it is clipped short when the next change (or the strand's end) arrives first.
    """
    stops: list[tuple[float, float]] = []
    if tenure.entry_y is not None:
        stops.append((tenure.start_x, tenure.entry_y))
    for x, band, rows in tenure.placements:
        y = _row_y(band_tops, band, rows)
        x = max(x, tenure.start_x)
        if stops and abs(stops[-1][1] - y) < 0.001:
            continue
        stops.append((x, y))

    pieces: list[tuple[str, float, ...]] = []
    cursor = tenure.start_x
    for index, (x, y) in enumerate(stops):
        if index == 0:
            continue
        start = max(x, cursor)
        if start >= tenure.end_x:
            break
        following = stops[index + 1][0] if index + 1 < len(stops) else tenure.end_x
        width = max(min(TRANSITION, following - start, tenure.end_x - start), 0.0)
        if start > cursor:
            pieces.append(("H", cursor, start, stops[index - 1][1]))
        pieces.append(("S", start, start + width, stops[index - 1][1], y))
        cursor = start + width
    if cursor < tenure.end_x or not pieces:
        pieces.append(("H", cursor, max(tenure.end_x, cursor), stops[-1][1]))
    return pieces


def _clip(pieces: list[tuple[str, float, ...]], x_from: float, x_to: float) -> str:
    """The `d` of the part of a strand between two x's, or "" when nothing falls inside.

    An S-curve belongs to the segment that *begins* at its x, so the rise out of a two-way row
    or a pick row carries the new segment's color.
    """
    kept: list[tuple[str, float, ...]] = []
    for piece in pieces:
        if piece[0] == "H":
            _, x1, x2, y = piece
            left, right = max(x1, x_from), min(x2, x_to)
            if right - left > 0.001:
                kept.append(("H", left, right, y))
        else:
            _, x1, x2, y1, y2 = piece
            if x1 >= x_from - 0.001 and x1 < x_to - 0.001:
                kept.append(piece)
    if not kept:
        return ""
    first = kept[0]
    start_y = first[3] if first[0] == "H" else first[3]
    parts = [f"M{first[1]:.2f},{start_y:.2f}"]
    for piece in kept:
        if piece[0] == "H":
            parts.append(f"L{piece[2]:.2f},{piece[3]:.2f}")
        else:
            _, x1, x2, y1, y2 = piece
            mid = (x1 + x2) / 2
            parts.append(f"L{x1:.2f},{y1:.2f}C{mid:.2f},{y1:.2f} {mid:.2f},{y2:.2f} {x2:.2f},{y2:.2f}")
    return " ".join(parts)


def _segment_fill(tenure: Tenure, segment: dict[str, Any]) -> str:
    if tenure.asset_type == "pick":
        return COLOR_PICK
    return CONTRACT_COLORS.get(segment["contract_type"], CONTRACT_COLORS[None])


def _hub_kind_fill(kind: str) -> str:
    """Hub-marker fill by transaction kind family (owner feedback round 2)."""
    if kind == "trade":
        return COLOR_HUB_TRADE
    if kind in SIGNING_KINDS:
        return COLOR_HUB_SIGNING
    if kind in WAIVER_KINDS:
        return COLOR_HUB_WAIVER
    if kind == "draft_selection":
        return COLOR_HUB_DRAFT_SELECTION
    return COLOR_CONNECTOR


def _fits(tenure: Tenure, budget: float) -> bool:
    """Whether a tenure's full label fits in the room its row leaves before the next occupant."""
    return budget >= MIN_LABEL_WIDTH and budget >= len(tenure.label) * LABEL_CHAR_WIDTH


def render_svg(export: dict[str, Any]) -> str:
    """Render a graph.json dict (as produced by `lineage.export.build_export`) to SVG."""
    start = _parse_date(export["window"]["start"])
    end = _parse_date(export["window"]["end"])
    scale = Scale(start, end, PLOT_X0, PLOT_X1)

    nodes = sorted(export["nodes"], key=lambda node: (node["date"], node["id"]))
    node_x = {node["id"]: scale(_parse_date(node["date"])) for node in nodes}
    node_kind = {node["id"]: node["kind"] for node in nodes}
    node_date = {node["id"]: _parse_date(node["date"]) for node in nodes}

    tenures = _tenures(export["assets"], export["strands"], node_date, start)
    continuations = _draft_continuations(nodes, tenures)
    heights = _walk_ranks(tenures, nodes, scale)
    band_tops = _band_tops(heights)
    _place(tenures, node_x, node_kind, band_tops, continuations)

    geometry = {id(tenure): _geometry(tenure, band_tops) for tenure in tenures}
    anchors = _label_anchors(tenures, geometry, band_tops)
    numbered = _assign_short_tenure_numbers(tenures, anchors, node_kind, node_date, start, end)

    rows_total = sum(heights[band] for band in BANDS)
    filled_bands = sum(1 for band in BANDS if heights[band])
    legend_height = _legend_height(len(numbered))
    height = int(
        math.ceil(
            TOP_MARGIN
            + rows_total * ROW_HEIGHT
            + max(filled_bands - 1, 0) * BAND_GAP
            + legend_height
        )
    )

    parts = [_svg_open(WIDTH, height)]
    parts.append(
        f'<text x="{PLOT_X0}" y="{TITLE_Y}" font-size="18" font-weight="bold" '
        f'fill="{COLOR_TEXT_PRIMARY}">{escape(TITLE)}</text>'
    )
    parts.append(_render_month_axis(start, end, scale))
    parts.append(_render_bands(tenures, heights, band_tops))
    parts.append(_render_strands(tenures, geometry))
    parts.append(_render_hubs(nodes, tenures, node_x, band_tops))
    parts.append(_render_overlay(tenures, anchors, numbered, band_tops))
    parts.append(_render_node_labels(nodes, node_x))
    parts.append(_render_legend(height, legend_height, numbered))
    parts.append("</svg>")
    return "".join(parts)


def _svg_open(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{COLOR_SURFACE}"/>'
    )


def _render_month_axis(start: dt.date, end: dt.date, scale: Scale) -> str:
    months = _month_starts(start, end)
    rotate = len(months) > MONTH_ROTATE_THRESHOLD
    axis_y = TOP_MARGIN - 14
    parts = [
        f'<g class="axis">'
        f'<line x1="{scale(start):.1f}" y1="{axis_y:.1f}" x2="{scale(end):.1f}" '
        f'y2="{axis_y:.1f}" stroke="{COLOR_AXIS}" stroke-width="1"/>'
    ]
    for month in months:
        x = scale(month)
        label = escape(month.strftime("%b %Y"))
        transform = f' transform="rotate(-45 {x:.1f} {axis_y - 6:.1f})"' if rotate else ""
        anchor = "end" if rotate else "middle"
        parts.append(
            f'<line x1="{x:.1f}" y1="{axis_y - 4:.1f}" x2="{x:.1f}" y2="{axis_y + 4:.1f}" '
            f'stroke="{COLOR_AXIS}" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{axis_y - 6:.1f}" font-size="10" text-anchor="{anchor}" '
            f'fill="{COLOR_TEXT_SECONDARY}"{transform}>{label}</text>'
        )
    parts.append("</g>")
    return "".join(parts)


def _render_bands(
    tenures: list[Tenure], heights: dict[str, float], band_tops: dict[str, float]
) -> str:
    """Each band's caption and extent, plus a recessive guide line per roster/two-way row.

    The picks band offsets its rows by half a row per draft-year boundary and those offsets
    move as picks come and go, so a fixed grid there would be a lie: only the bands whose rows
    sit at a constant pitch get guide lines.
    """
    used: dict[str, list[float]] = {band: [] for band in BANDS}
    for tenure in tenures:
        for _, band, rows in tenure.placements:
            if rows not in used[band]:
                used[band].append(rows)
    parts = []
    for band in BANDS:
        if not heights[band]:
            continue
        parts.append(
            f'<g class="band" data-band={quoteattr(band)} data-top="{band_tops[band]:.1f}" '
            f'data-rows="{heights[band]:g}" data-row-height="{ROW_HEIGHT:g}">'
            f'<text class="band-title" x="{PLOT_X0 - 8}" y="{band_tops[band] + 10:.1f}" '
            f'font-size="9" text-anchor="end" fill="{COLOR_TEXT_MUTED}">'
            f"{escape(BAND_TITLES[band])}</text>"
        )
        if band != PICK:
            for rows in sorted(used[band]):
                y = _row_y(band_tops, band, rows)
                parts.append(
                    f'<g class="row" data-band={quoteattr(band)} data-rows="{rows:g}">'
                    f'<line x1="{PLOT_X0}" y1="{y:.1f}" x2="{PLOT_X1}" y2="{y:.1f}" '
                    f'stroke="{COLOR_GRID}" stroke-width="1"/>'
                    "</g>"
                )
        parts.append("</g>")
    return "".join(parts)


def _label_anchors(
    tenures: list[Tenure],
    geometry: dict[int, list[tuple[str, float, ...]]],
    band_tops: dict[str, float],
) -> dict[int, tuple[float, float, float]]:
    """Where each tenure's name sits, and how much room it has: its roomiest horizontal run.

    Rows are ranks, so a strand can hold several of them over its life. The name goes at the
    left edge of the strand when it fits there, and otherwise on its roomiest flat stretch;
    past the end of the strand it may only run until something else takes over that row.
    Keyed by id() of the tenure.
    """
    claims: dict[float, list[tuple[float, int]]] = {}
    for tenure in tenures:
        for x, band, rows in tenure.placements:
            y = _row_y(band_tops, band, rows)
            claims.setdefault(y, []).append((max(x, tenure.start_x), id(tenure)))
    for entries in claims.values():
        entries.sort(key=lambda entry: entry[0])

    anchors: dict[int, tuple[float, float, float]] = {}
    for tenure in tenures:
        runs = [piece for piece in geometry[id(tenure)] if piece[0] == "H"]
        options: list[tuple[float, float, float]] = []
        for index, (_, x1, x2, y) in enumerate(runs):
            if index + 1 < len(runs):
                limit = x2
            else:
                limit = float(OPEN_END_X)
                for x, owner in claims.get(y, []):
                    if x > x1 + 0.001 and owner != id(tenure):
                        limit = x
                        break
                limit = max(limit, x2)
            options.append((x1, y, limit - x1 - 6))
        if not options:
            anchors[id(tenure)] = (tenure.start_x, tenure.first_y(band_tops), 0.0)
            continue
        # The eye looks for a name where the strand starts; only when it cannot fit there does
        # the label move to the strand's roomiest stretch.
        fitting = next((option for option in options if _fits(tenure, option[2])), None)
        anchors[id(tenure)] = fitting or max(options, key=lambda option: option[2])
    return anchors


def _tenure_start_date(
    tenure: Tenure, node_kind: dict[str, str], node_date: dict[str, dt.date], window_start: dt.date
) -> dt.date:
    if node_kind.get(tenure.start_node) == "baseline":
        return window_start
    return node_date[tenure.start_node]


def _tenure_end_date(tenure: Tenure, node_date: dict[str, dt.date], window_end: dt.date) -> dt.date:
    if tenure.end_node is None:
        return window_end
    return node_date[tenure.end_node]


def _assign_short_tenure_numbers(
    tenures: list[Tenure],
    anchors: dict[int, tuple[float, float, float]],
    node_kind: dict[str, str],
    node_date: dict[str, dt.date],
    window_start: dt.date,
    window_end: dt.date,
) -> dict[int, tuple[int, dt.date, dt.date, str]]:
    """Number, in (start date, asset order) order, every tenure whose full label doesn't fit.

    Returns {id(tenure): (number, start_date, end_date, label)} so both the marker and the
    legend entry it feeds can be built from one pass.
    """
    candidates = [tenure for tenure in tenures if not _fits(tenure, anchors[id(tenure)][2])]
    ordered = sorted(
        candidates,
        key=lambda t: (
            _tenure_start_date(t, node_kind, node_date, window_start),
            anchors[id(t)][1],
            t.order,
        ),
    )
    numbered = {}
    for index, tenure in enumerate(ordered, start=1):
        numbered[id(tenure)] = (
            index,
            _tenure_start_date(tenure, node_kind, node_date, window_start),
            _tenure_end_date(tenure, node_date, window_end),
            tenure.label,
        )
    return numbered


def _render_strands(
    tenures: list[Tenure], geometry: dict[int, list[tuple[str, float, ...]]]
) -> str:
    parts = []
    for tenure in tenures:
        pieces = geometry[id(tenure)]
        parts.append(
            f'<g class="strand" data-asset-id={quoteattr(tenure.asset_id)} '
            f'data-asset-type={quoteattr(tenure.asset_type)}>'
            f"<title>{escape(_strand_title(tenure))}</title>"
        )
        bounds = tenure.bounds
        for index, segment in enumerate(tenure.segments):
            d = _clip(pieces, bounds[index], bounds[index + 1])
            if not d:
                continue
            parts.append(
                f'<path class="segment" data-asset-id={quoteattr(tenure.asset_id)} '
                f'data-holder={quoteattr(segment["holder"])} '
                f'data-from-node={quoteattr(segment["from_node"] or "")} '
                f'data-to-node={quoteattr(segment["to_node"] or "")} '
                f'data-contract-type={quoteattr(segment["contract_type"] or "")} '
                f'd="{d}" fill="none" stroke="{_segment_fill(tenure, segment)}" '
                f'stroke-width="{STRAND_WIDTH}" stroke-linecap="butt"/>'
            )
        parts.append("</g>")
    return "".join(parts)


def _strand_title(tenure: Tenure) -> str:
    destination = f" → {tenure.exit_holder}" if tenure.exit_holder else ""
    return f"{tenure.label}: MEM{destination}"


def _render_overlay(
    tenures: list[Tenure],
    anchors: dict[int, tuple[float, float, float]],
    numbered: dict[int, tuple[int, dt.date, dt.date, str]],
    band_tops: dict[str, float],
) -> str:
    """Exit caps and asset labels, drawn last so hub markers never hide a name."""
    parts = []
    for tenure in tenures:
        if tenure.exit_holder and not tenure.continues_as:
            parts.append(_render_exit_cap(tenure, band_tops))
        label_x, label_y, _ = anchors[id(tenure)]
        number = numbered.get(id(tenure))
        if number is not None:
            parts.append(_render_numbered_marker(tenure, number[0], label_x, label_y))
        else:
            parts.append(_render_label(tenure, label_x, label_y))
    return "".join(parts)


def _render_label(tenure: Tenure, x: float, y: float) -> str:
    return (
        f'<text class="asset-label" x="{x + 3:.2f}" y="{y + 3.2:.1f}" '
        f'font-size="{LABEL_FONT}" fill="{COLOR_TEXT_PRIMARY}">{escape(tenure.label)}</text>'
    )


def _render_numbered_marker(tenure: Tenure, number: int, x: float, y: float) -> str:
    """A small numbered badge at a strand's left edge, standing in for a name that won't fit."""
    size = 10.0
    return (
        f'<g class="short-tenure-marker" data-asset-id={quoteattr(tenure.asset_id)} '
        f'data-number="{number}">'
        f"<title>{escape(tenure.label)}</title>"
        f'<rect x="{x - 1:.2f}" y="{y - size / 2:.2f}" width="{size:.1f}" height="{size:.1f}" '
        f'rx="2" fill="{COLOR_CAP}"/>'
        f'<text x="{x - 1 + size / 2:.2f}" y="{y + 2.8:.1f}" font-size="7" '
        f'text-anchor="middle" fill="{COLOR_SURFACE}">{number}</text>'
        "</g>"
    )


def _render_exit_cap(tenure: Tenure, band_tops: dict[str, float]) -> str:
    """A plain end-cap marker for an asset that left Memphis (no destination text on the cap)."""
    x, y = tenure.end_x, tenure.last_y(band_tops)
    return (
        f'<g class="exit" data-asset-id={quoteattr(tenure.asset_id)} '
        f'data-destination={quoteattr(tenure.exit_holder or "")}>'
        f'<title>{escape(f"Left MEM → {tenure.exit_holder}")}</title>'
        f'<path class="exit-marker" d="M{x:.2f},{y - 4:.1f} L{x + 5:.2f},{y:.1f} '
        f'L{x:.2f},{y + 4:.1f} Z" fill="{COLOR_CAP}"/>'
        "</g>"
    )


def _render_hubs(
    nodes: list[dict[str, Any]],
    tenures: list[Tenure],
    node_x: dict[str, float],
    band_tops: dict[str, float],
) -> str:
    """A kind-colored marker per transaction; trades also converge and diverge their strands."""
    arriving: dict[str, list[Tenure]] = {}
    departing: dict[str, list[Tenure]] = {}
    touching: dict[str, list[Tenure]] = {}
    for tenure in tenures:
        arriving.setdefault(tenure.start_node, []).append(tenure)
        if tenure.end_node is not None:
            departing.setdefault(tenure.end_node, []).append(tenure)
        for segment in tenure.segments[:-1]:
            touching.setdefault(segment["to_node"], []).append(tenure)

    parts = []
    for node in nodes:
        if node["kind"] in FLAT_NODE_KINDS:
            continue
        node_id = node["id"]
        x = node_x[node_id]
        outs = departing.get(node_id, [])
        ins = arriving.get(node_id, [])
        internal = touching.get(node_id, [])
        if not outs and not ins and not internal:
            continue
        ys = (
            [tenure.last_y(band_tops) for tenure in outs]
            + [_entry_y(tenure, band_tops) for tenure in ins]
            + [tenure.y_at(x, band_tops) for tenure in internal]
        )
        hub_y = sum(ys) / len(ys)
        parts.append(
            f'<g class="hub" data-node-id={quoteattr(node_id)} data-kind={quoteattr(node["kind"])} '
            f'data-out="{len(outs)}" data-in="{len(ins)}">'
            f'<title>{escape(node["description"])}</title>'
        )
        if node["kind"] == "trade":
            for tenure in sorted(outs, key=lambda t: (t.last_y(band_tops), t.order)):
                parts.append(
                    _connector(
                        "out", tenure, x - tenure.lag, tenure.last_y(band_tops), x, hub_y, tenure.lag
                    )
                )
            for tenure in sorted(ins, key=lambda t: (_entry_y(t, band_tops), t.order)):
                parts.append(
                    _connector(
                        "in", tenure, x, hub_y, x + tenure.lead, _entry_y(tenure, band_tops),
                        tenure.lead,
                    )
                )
        parts.append(
            f'<circle class="hub-marker" cx="{x:.2f}" cy="{hub_y:.1f}" r="{HUB_RADIUS}" '
            f'fill="{_hub_kind_fill(node["kind"])}" stroke="{COLOR_SURFACE}" stroke-width="1.5"/>'
        )
        parts.append("</g>")
    return "".join(parts)


def _entry_y(tenure: Tenure, band_tops: dict[str, float]) -> float:
    """Where a strand enters the page: its own row, or the pick row a draftee rises out of."""
    if tenure.entry_y is not None:
        return tenure.entry_y
    return tenure.first_y(band_tops)


def _connector(
    kind: str, tenure: Tenure, x1: float, y1: float, x2: float, y2: float, reach: float
) -> str:
    bend = max(reach, 6.0) * 0.55
    return (
        f'<path class={quoteattr(kind)} data-asset-id={quoteattr(tenure.asset_id)} '
        f'd="M{x1:.2f},{y1:.1f} C{x1 + bend:.2f},{y1:.1f} {x2 - bend:.2f},{y2:.1f} '
        f'{x2:.2f},{y2:.1f}" fill="none" stroke="{COLOR_CONNECTOR}" stroke-width="1.6" '
        f'stroke-opacity="0.6"/>'
    )


def _render_node_labels(nodes: list[dict[str, Any]], node_x: dict[str, float]) -> str:
    labelled = [node for node in nodes if node["kind"] in LABELLED_NODE_KINDS]
    if not labelled:
        return ""
    xs = sorted(node_x[node["id"]] for node in labelled)
    rotate = any(b - a < NODE_LABEL_MIN_GAP for a, b in zip(xs, xs[1:]))
    parts = ['<g class="node-labels">']
    previous_x = -NODE_LABEL_MIN_GAP
    level = 0
    drawn: list[tuple[float, str]] = []
    for node in sorted(labelled, key=lambda n: (node_x[n["id"]], n["id"])):
        x = node_x[node["id"]]
        date = _parse_date(node["date"])
        kind = node["kind"].replace("_", " ")
        caption = f'{date.strftime("%b")} {date.day} {kind}'
        # Two drafts on the same day would print the same caption twice on the same tick.
        if (x, caption) in drawn:
            continue
        drawn.append((x, caption))
        level = (level + 1) % NODE_LABEL_LEVELS if x - previous_x < NODE_LABEL_MIN_GAP else 0
        previous_x = x
        y = NODE_LABEL_Y + level * NODE_LABEL_STAGGER
        label = escape(caption)
        transform = f' transform="rotate(-45 {x:.2f} {y})"' if rotate else ""
        anchor = "start" if rotate else "middle"
        parts.append(
            f'<line x1="{x:.2f}" y1="{y + 4}" x2="{x:.2f}" y2="{TOP_MARGIN - 18}" '
            f'stroke="{COLOR_GRID}" stroke-width="1"/>'
            f'<text class="node-label" x="{x:.2f}" y="{y}" font-size="9" '
            f'text-anchor="{anchor}" fill="{COLOR_TEXT_SECONDARY}"{transform}>{label}</text>'
        )
    parts.append("</g>")
    return "".join(parts)


def _legend_height(numbered_count: int) -> float:
    height = LEGEND_TOP_PAD + LEGEND_ROW_GAP + LEGEND_BOTTOM_PAD
    if numbered_count:
        cols = max(1, int((WIDTH - 2 * PLOT_X0) // NUMBERED_COL_WIDTH))
        rows = math.ceil(numbered_count / cols)
        height += NUMBERED_LEGEND_GAP + rows * NUMBERED_ROW_HEIGHT
    return height


def _legend_swatch_row(y: float, entries: list[tuple[str, str, str]]) -> str:
    """One row of `(shape, color, caption)` swatches, `shape` one of "bar"/"circle"/"cap"."""
    parts = []
    x = float(PLOT_X0)
    for shape, color, caption in entries:
        if shape == "bar":
            parts.append(
                f'<line x1="{x:.1f}" y1="{y - 3:.1f}" x2="{x + 26:.1f}" y2="{y - 3:.1f}" '
                f'stroke="{color}" stroke-width="{STRAND_WIDTH}"/>'
            )
            text_x = x + 31
        elif shape == "circle":
            parts.append(
                f'<circle cx="{x + 6:.1f}" cy="{y - 3:.1f}" r="{HUB_RADIUS}" fill="{color}"/>'
            )
            text_x = x + 18
        else:  # plain exit-cap marker
            parts.append(
                f'<path d="M{x:.1f},{y - 7:.1f} L{x + 5:.1f},{y - 3:.1f} L{x:.1f},{y + 1:.1f} Z" '
                f'fill="{color}"/>'
            )
            text_x = x + 11
        parts.append(f'<text x="{text_x:.1f}" y="{y:.1f}">{escape(caption)}</text>')
        x = text_x + 6.2 * len(caption) + 24
    return "".join(parts)


def _render_legend(
    height: int, legend_height: float, numbered: dict[int, tuple[int, dt.date, dt.date, str]]
) -> str:
    top = height - legend_height
    parts = [f'<g class="legend" font-size="10" fill="{COLOR_TEXT_PRIMARY}">']

    row1_y = top + LEGEND_TOP_PAD
    parts.append(
        _legend_swatch_row(
            row1_y,
            [
                ("bar", COLOR_STANDARD, "standard"),
                ("bar", COLOR_TWO_WAY, "two-way"),
                ("bar", COLOR_TEN_DAY, "10-day"),
                ("bar", COLOR_DRAFT_RIGHTS, "draft rights"),
                ("bar", COLOR_PICK, "pick"),
            ],
        )
    )

    row2_y = row1_y + LEGEND_ROW_GAP
    parts.append(
        _legend_swatch_row(
            row2_y,
            [
                ("circle", COLOR_HUB_TRADE, "trade"),
                ("circle", COLOR_HUB_SIGNING, "signing"),
                ("circle", COLOR_HUB_WAIVER, "waiver"),
                ("circle", COLOR_HUB_DRAFT_SELECTION, "draft selection"),
                ("cap", COLOR_CAP, "left Memphis"),
            ],
        )
    )

    if numbered:
        parts.append(_render_numbered_legend(row2_y + NUMBERED_LEGEND_GAP, numbered))

    parts.append("</g>")
    return "".join(parts)


def _render_numbered_legend(
    top_y: float, numbered: dict[int, tuple[int, dt.date, dt.date, str]]
) -> str:
    """Deterministic `n. Full Name (start → end)` block for tenures whose label was dropped."""
    entries = sorted(numbered.values(), key=lambda entry: entry[0])
    cols = max(1, int((WIDTH - 2 * PLOT_X0) // NUMBERED_COL_WIDTH))
    parts = [f'<g class="short-tenure-legend" font-size="9" fill="{COLOR_TEXT_SECONDARY}">']
    for index, (number, start_date, end_date, label) in enumerate(entries):
        col, row = index % cols, index // cols
        x = PLOT_X0 + col * NUMBERED_COL_WIDTH
        y = top_y + row * NUMBERED_ROW_HEIGHT
        text = f"{number}. {label} ({start_date.strftime('%b %d')} → {end_date.strftime('%b %d')})"
        parts.append(f'<text x="{x:.1f}" y="{y:.1f}">{escape(text)}</text>')
    parts.append("</g>")
    return "".join(parts)


def run_render(in_path: pathlib.Path, out_path: pathlib.Path) -> str:
    """Read graph.json from `in_path`, render its SVG, write it to `out_path`."""
    export = json.loads(in_path.read_text())
    svg = render_svg(export)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg)
    print(f"wrote {out_path}")
    return svg
