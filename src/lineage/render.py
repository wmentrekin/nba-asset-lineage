"""Hand-written SVG rendering of graph.json: no plotting library, no PNG.

Layout ("slot lanes + node hubs"): x is time (linear, window.start to window.end). Only
Memphis tenure is drawn — a lane is a *roster slot*, not an asset, so a lane frees when its
occupant leaves MEM and the next arrival at that node takes it over. Players occupy a top
band of lanes, Memphis-owned picks a band below. Every transaction that starts or ends a MEM
tenure is a hub: a marker at (x, mean lane y) with a bezier per departing asset curving into
it and one per arriving asset curving out, so a trade reads as convergence then divergence.
Assets leaving MEM end in a plain end-cap marker (with a `<title>` tooltip naming the
destination); `baseline` and `expiry` nodes are plain end-caps rather than hubs.

Bar color encodes contract type (categorical, not thickness — every bar is the same height);
hub markers are colored by the kind of transaction they represent, so a trade, a signing, a
waiver and a draft selection each read as their own color while the connector curves stay a
neutral, darker stroke and let the hub marker carry the color.

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
# the window's last day still gets a visible bar.
OPEN_END_X = PLOT_X1 + 44
TITLE_Y = 22
NODE_LABEL_Y = 70
TOP_MARGIN = 110
LANE_HEIGHT = 16
BAND_GAP = 24

# A bar stops this far short of its node's x; the gap is where the connector curve lives.
CONNECTOR_OFFSET = 24.0
MIN_BAR_WIDTH = 6.0
HUB_RADIUS = 4.5

NODE_LABEL_MIN_GAP = 40.0
NODE_LABEL_STAGGER = 14
MONTH_ROTATE_THRESHOLD = 12

LABEL_FONT = 9
CAP_FONT = 8
# Helvetica/Arial averages ~0.52em per character; used to decide whether a lane leaves enough
# room for a tenure's full name, since there is no text-measuring API in plain SVG.
LABEL_CHAR_WIDTH = LABEL_FONT * 0.52
MIN_LABEL_WIDTH = 24.0
MIN_INLINE_CAP_WIDTH = 34.0

# Every bar is the same height: contract type is read from color, not thickness.
BAR_HEIGHT = 9

# Nodes of these kinds never become hubs: a baseline is the left edge of the window and an
# expiry is a 10-day contract simply lapsing, so neither has two sides to route between.
FLAT_NODE_KINDS = frozenset({"baseline", "expiry"})
LABELLED_NODE_KINDS = frozenset({"trade", "draft_selection"})

# Hub-marker kind families (owner feedback round 2): every transaction kind that starts or
# ends a tenure falls into exactly one of these, or is a plain baseline/expiry end-cap.
SIGNING_KINDS = frozenset({"signing", "two_way_signing", "two_way_conversion", "ten_day"})
WAIVER_KINDS = frozenset({"waiver", "contract_void"})

# Colors: the default validated categorical palette (see the dataviz skill), used in its
# documented fixed order across two independent categorical encodings that appear side by
# side in this chart — contract type (bars, slots 1-4) then pick strands (slot 5) then hub
# kind (markers, slots 6-8), plus one deliberate reuse (draft selection hubs echo the
# draft-rights bar color, since both are "about the draft"). Never cycled, never reordered.
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

# Connectors and internal ticks stay a neutral, darker ink so the colored hub marker (not the
# curve leading into it) is what reads as "trade" / "signing" / "waiver" / "draft selection".
COLOR_CONNECTOR = "#52514e"
COLOR_CAP = "#52514e"
COLOR_TEXT_PRIMARY = "#0b0b0b"
COLOR_TEXT_SECONDARY = "#52514e"
COLOR_TEXT_MUTED = "#898781"
COLOR_SURFACE = "#fcfcfb"
COLOR_GRID = "#e1e0d9"
COLOR_AXIS = "#c3c2b7"

BANDS = ("player", "pick")
OCCUPIED = math.inf

TITLE = "Memphis Grizzlies asset lineage, 2025-26 → today"

# Legend layout: two fixed rows of color swatches (contract types, then hub kinds + the plain
# exit marker), plus a variable-height block of numbered markers for tenures whose full name
# didn't fit on its bar.
LEGEND_TOP_PAD = 34.0
LEGEND_ROW_GAP = 20.0
LEGEND_BOTTOM_PAD = 16.0
NUMBERED_LEGEND_GAP = 20.0
NUMBERED_ROW_HEIGHT = 14.0
NUMBERED_COL_WIDTH = 260.0


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


@dataclass
class Tenure:
    """One unbroken stretch of MEM ownership of one asset: the thing a lane holds."""

    asset_id: str
    band: str
    label: str
    order: int
    start_node: str
    end_node: str | None
    exit_holder: str | None
    segments: list[dict[str, Any]]
    lane: int = -1
    start_x: float = 0.0
    end_x: float = 0.0
    lead: float = 0.0
    lag: float = 0.0
    y: float = 0.0
    boundaries: list[float] = field(default_factory=list)


def _tenures(assets: list[dict[str, Any]], strands: list[dict[str, Any]]) -> list[Tenure]:
    """Split every strand into its MEM tenures, in graph.json asset order.

    Consecutive MEM segments (a two-way conversion, a re-signing, a back-to-back 10-day) are
    one tenure with an internal boundary, not an exit and a re-entry.
    """
    segments_by_asset = {strand["asset_id"]: strand["segments"] for strand in strands}
    tenures: list[Tenure] = []
    for order, asset in enumerate(assets):
        segments = segments_by_asset.get(asset["id"], [])
        index = 0
        while index < len(segments):
            if segments[index]["holder"] != "MEM":
                index += 1
                continue
            last = index
            while last + 1 < len(segments) and segments[last + 1]["holder"] == "MEM":
                last += 1
            after = segments[last + 1] if last + 1 < len(segments) else None
            tenures.append(
                Tenure(
                    asset_id=asset["id"],
                    band=asset["type"],
                    label=asset["label"],
                    order=order,
                    start_node=segments[index]["from_node"],
                    end_node=segments[last]["to_node"],
                    exit_holder=after["holder"] if after else None,
                    segments=segments[index : last + 1],
                )
            )
            index = last + 1
    return tenures


def _reorder_full_window_players(tenures: list[Tenure], node_kind: dict[str, str]) -> None:
    """Move assets MEM held for the entire window to the front of the player band.

    An asset qualifies when its first MEM segment starts at the baseline node and its last
    MEM segment has `to_node is None` (still held at window end) — a MEM->MEM re-sign or
    conversion in between does not break it, since those stay inside one Tenure. Relative
    order within each of the two groups is preserved (graph.json's own asset order, which is
    also this band's original lane-reuse order), so this only changes who sorts first.
    """
    by_asset: dict[str, list[Tenure]] = {}
    for tenure in tenures:
        if tenure.band == "player":
            by_asset.setdefault(tenure.asset_id, []).append(tenure)

    full_window: set[str] = set()
    for asset_id, group in by_asset.items():
        first, last = group[0], group[-1]
        if node_kind.get(first.start_node) == "baseline" and last.end_node is None:
            full_window.add(asset_id)

    original_order = sorted(by_asset, key=lambda asset_id: by_asset[asset_id][0].order)
    front = [asset_id for asset_id in original_order if asset_id in full_window]
    back = [asset_id for asset_id in original_order if asset_id not in full_window]
    new_order = {asset_id: index for index, asset_id in enumerate(front + back)}

    for tenure in tenures:
        if tenure.band == "player":
            tenure.order = new_order[tenure.asset_id]


def _assign_lanes(
    tenures: list[Tenure],
    nodes: list[dict[str, Any]],
    node_x: dict[str, float],
) -> dict[str, int]:
    """Assign each tenure a lane in its band, reusing lanes freed at the same node.

    Nodes are walked in (date, id) order. At each node the departing tenures release their
    lanes, then the arriving ones take them: an asset returning to a still-free lane keeps it,
    otherwise the lanes just vacated here are handed out top to bottom, then the free lane
    closest to the departing group's centroid, and only then a fresh lane at the bottom of the
    band. Returns {band: lane count}.
    """
    # free_from[band][lane] is the x at which that lane is available again (OCCUPIED = never).
    free_from: dict[str, list[float]] = {band: [] for band in BANDS}
    starting: dict[str, list[Tenure]] = {}
    ending: dict[str, list[Tenure]] = {}
    for tenure in tenures:
        starting.setdefault(tenure.start_node, []).append(tenure)
        if tenure.end_node is not None:
            ending.setdefault(tenure.end_node, []).append(tenure)
    previous_lane: dict[tuple[str, str], int] = {}

    for node in nodes:
        x = node_x[node["id"]]
        leaving = sorted(ending.get(node["id"], []), key=lambda t: (t.lane, t.order))
        vacated: dict[str, list[int]] = {band: [] for band in BANDS}
        for tenure in leaving:
            free_from[tenure.band][tenure.lane] = x
            vacated[tenure.band].append(tenure.lane)
        centroid = {
            band: (sum(lanes) / len(lanes) if lanes else None) for band, lanes in vacated.items()
        }

        for tenure in sorted(starting.get(node["id"], []), key=lambda t: t.order):
            lanes = free_from[tenure.band]
            reclaimed = previous_lane.get((tenure.band, tenure.asset_id))
            if reclaimed is not None and lanes[reclaimed] <= x:
                chosen = reclaimed
            elif vacated[tenure.band]:
                chosen = vacated[tenure.band][0]
            else:
                free = [lane for lane, available in enumerate(lanes) if available <= x]
                if not free:
                    lanes.append(OCCUPIED)
                    chosen = len(lanes) - 1
                elif centroid[tenure.band] is None:
                    chosen = free[0]
                else:
                    middle = centroid[tenure.band]
                    chosen = min(free, key=lambda lane: (abs(lane - middle), lane))
            if chosen in vacated[tenure.band]:
                vacated[tenure.band].remove(chosen)
            lanes[chosen] = OCCUPIED
            tenure.lane = chosen
            previous_lane[(tenure.band, tenure.asset_id)] = chosen

    return {band: len(free_from[band]) for band in BANDS}


def _band_tops(lane_counts: dict[str, int]) -> dict[str, float]:
    top = float(TOP_MARGIN)
    tops = {}
    for band in BANDS:
        tops[band] = top
        if lane_counts[band]:
            top += lane_counts[band] * LANE_HEIGHT + BAND_GAP
    return tops


def _place(
    tenures: list[Tenure],
    node_x: dict[str, float],
    node_kind: dict[str, str],
    band_tops: dict[str, float],
) -> None:
    """Fill in each tenure's y, bar extent and per-segment boundaries."""
    for tenure in tenures:
        tenure.y = band_tops[tenure.band] + tenure.lane * LANE_HEIGHT + LANE_HEIGHT / 2
        start_flat = node_kind.get(tenure.start_node) in FLAT_NODE_KINDS
        if node_kind.get(tenure.start_node) == "baseline":
            raw_start = float(PLOT_X0)
        else:
            raw_start = node_x[tenure.start_node]
        lead = 0.0 if start_flat else CONNECTOR_OFFSET
        if tenure.end_node is None:
            raw_end, lag = float(OPEN_END_X), 0.0
        else:
            raw_end = node_x[tenure.end_node]
            lag = 0.0 if node_kind.get(tenure.end_node) in FLAT_NODE_KINDS else CONNECTOR_OFFSET
        span = raw_end - raw_start
        if lead + lag > 0 and span - lead - lag < MIN_BAR_WIDTH:
            # Two hubs closer together than 2*CONNECTOR_OFFSET: shrink both curves to fit.
            shrink = min(1.0, max(0.0, (span - MIN_BAR_WIDTH) / (lead + lag)))
            lead, lag = lead * shrink, lag * shrink
        tenure.lead, tenure.lag = lead, lag
        tenure.start_x = raw_start + lead
        tenure.end_x = max(raw_end - lag, raw_start + lead)

        inner = [node_x[segment["to_node"]] for segment in tenure.segments[:-1]]
        bounds = [tenure.start_x]
        for value in inner:
            bounds.append(min(max(value, bounds[-1]), tenure.end_x))
        bounds.append(tenure.end_x)
        tenure.boundaries = bounds


def _svg_open(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{COLOR_SURFACE}"/>'
    )


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


def _segment_fill(tenure: Tenure, segment: dict[str, Any]) -> str:
    if tenure.band == "pick":
        return COLOR_PICK
    return CONTRACT_COLORS.get(segment["contract_type"], CONTRACT_COLORS[None])


def _fits(tenure: Tenure, budget: float) -> bool:
    """Whether a tenure's full label fits in the room its lane leaves before the next bar."""
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

    tenures = _tenures(export["assets"], export["strands"])
    _reorder_full_window_players(tenures, node_kind)
    lane_counts = _assign_lanes(tenures, nodes, node_x)
    band_tops = _band_tops(lane_counts)
    _place(tenures, node_x, node_kind, band_tops)

    budgets = _label_budgets(tenures)
    numbered = _assign_short_tenure_numbers(tenures, budgets, node_kind, node_date, start, end)

    lane_total = sum(lane_counts[band] for band in BANDS)
    filled_bands = sum(1 for band in BANDS if lane_counts[band])
    legend_height = _legend_height(len(numbered))
    height = int(
        TOP_MARGIN + lane_total * LANE_HEIGHT + max(filled_bands - 1, 0) * BAND_GAP + legend_height
    )

    parts = [_svg_open(WIDTH, height)]
    parts.append(
        f'<text x="{PLOT_X0}" y="{TITLE_Y}" font-size="18" font-weight="bold" '
        f'fill="{COLOR_TEXT_PRIMARY}">{escape(TITLE)}</text>'
    )
    parts.append(_render_month_axis(start, end, scale))
    parts.append(_render_lanes(lane_counts, band_tops))
    parts.append(_render_bars(tenures))
    parts.append(_render_hubs(nodes, tenures, node_x, node_kind))
    parts.append(_render_overlay(tenures, budgets, numbered))
    parts.append(_render_node_labels(nodes, node_x))
    parts.append(_render_legend(height, legend_height, numbered))
    parts.append("</svg>")
    return "".join(parts)


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


def _render_lanes(lane_counts: dict[str, int], band_tops: dict[str, float]) -> str:
    parts = []
    for band in BANDS:
        for lane in range(lane_counts[band]):
            y = band_tops[band] + lane * LANE_HEIGHT + LANE_HEIGHT / 2
            parts.append(
                f'<g class="lane" data-band={quoteattr(band)} data-lane="{lane}">'
                f'<line x1="{PLOT_X0}" y1="{y:.1f}" x2="{PLOT_X1}" y2="{y:.1f}" '
                f'stroke="{COLOR_GRID}" stroke-width="1"/>'
                "</g>"
            )
    return "".join(parts)


def _label_budgets(tenures: list[Tenure]) -> dict[int, float]:
    """How much horizontal room each tenure's left-edge label has before the next bar.

    Keyed by id() of the tenure - lanes are reused, so a label can only run as far as the next
    occupant of the same lane.
    """
    by_lane: dict[tuple[str, int], list[Tenure]] = {}
    for tenure in tenures:
        by_lane.setdefault((tenure.band, tenure.lane), []).append(tenure)
    budgets: dict[int, float] = {}
    for occupants in by_lane.values():
        ordered = sorted(occupants, key=lambda t: (t.start_x, t.order))
        for index, tenure in enumerate(ordered):
            limit = ordered[index + 1].start_x if index + 1 < len(ordered) else float(OPEN_END_X)
            budgets[id(tenure)] = limit - tenure.start_x - 6
    return budgets


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
    budgets: dict[int, float],
    node_kind: dict[str, str],
    node_date: dict[str, dt.date],
    window_start: dt.date,
    window_end: dt.date,
) -> dict[int, tuple[int, dt.date, dt.date, str]]:
    """Number, in (start date, lane) order, every tenure whose full label doesn't fit.

    Returns {id(tenure): (number, start_date, end_date, label)} so both the marker and the
    legend entry it feeds can be built from one pass. Deterministic: ties break on lane, then
    on the tenure's own asset order.
    """
    candidates = [tenure for tenure in tenures if not _fits(tenure, budgets[id(tenure)])]
    ordered = sorted(
        candidates,
        key=lambda t: (
            _tenure_start_date(t, node_kind, node_date, window_start),
            t.lane,
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


def _render_bars(tenures: list[Tenure]) -> str:
    parts = []
    for tenure in tenures:
        parts.append(
            f'<g class="strand" data-asset-id={quoteattr(tenure.asset_id)} '
            f'data-band={quoteattr(tenure.band)} data-lane="{tenure.lane}">'
            f"<title>{escape(_strand_title(tenure))}</title>"
        )
        for index, segment in enumerate(tenure.segments):
            x_from, x_to = tenure.boundaries[index], tenure.boundaries[index + 1]
            fill = _segment_fill(tenure, segment)
            parts.append(
                f'<rect class="segment" data-asset-id={quoteattr(tenure.asset_id)} '
                f'data-holder={quoteattr(segment["holder"])} '
                f'data-from-node={quoteattr(segment["from_node"] or "")} '
                f'data-to-node={quoteattr(segment["to_node"] or "")} '
                f'data-contract-type={quoteattr(segment["contract_type"] or "")} '
                f'x="{x_from:.2f}" y="{tenure.y - BAR_HEIGHT / 2:.1f}" '
                f'width="{max(x_to - x_from, 0):.2f}" height="{BAR_HEIGHT}" '
                f'rx="2" fill="{fill}"/>'
            )
            if index:
                # A MEM -> MEM boundary (conversion, re-signing, consecutive 10-day): the bar
                # stays continuous and only gets a tick, in the neutral connector ink.
                parts.append(
                    f'<line class="tick" x1="{x_from:.2f}" y1="{tenure.y - 6:.1f}" '
                    f'x2="{x_from:.2f}" y2="{tenure.y + 6:.1f}" '
                    f'stroke="{COLOR_CONNECTOR}" stroke-width="1"/>'
                )
        if tenure.lead == 0 and tenure.start_x <= PLOT_X0 + 0.01:
            parts.append(
                f'<line class="origin-cap" x1="{tenure.start_x:.2f}" y1="{tenure.y - 5:.1f}" '
                f'x2="{tenure.start_x:.2f}" y2="{tenure.y + 5:.1f}" '
                f'stroke="{COLOR_AXIS}" stroke-width="1.5"/>'
            )
        parts.append("</g>")
    return "".join(parts)


def _strand_title(tenure: Tenure) -> str:
    destination = f" → {tenure.exit_holder}" if tenure.exit_holder else ""
    return f"{tenure.label}: MEM{destination}"


def _render_overlay(
    tenures: list[Tenure],
    budgets: dict[int, float],
    numbered: dict[int, tuple[int, dt.date, dt.date, str]],
) -> str:
    """Exit caps and asset labels, drawn last so hub markers never hide a name."""
    parts = []
    for tenure in tenures:
        if tenure.exit_holder:
            parts.append(_render_exit_cap(tenure))
        number = numbered.get(id(tenure))
        if number is not None:
            parts.append(_render_numbered_marker(tenure, number[0]))
        else:
            parts.append(_render_label(tenure, budgets[id(tenure)]))
    return "".join(parts)


def _render_label(tenure: Tenure, budget: float) -> str:
    if not _fits(tenure, budget):
        return ""
    return (
        f'<text class="asset-label" x="{tenure.start_x + 3:.2f}" y="{tenure.y + 3.2:.1f}" '
        f'font-size="{LABEL_FONT}" fill="{COLOR_TEXT_PRIMARY}">{escape(tenure.label)}</text>'
    )


def _render_numbered_marker(tenure: Tenure, number: int) -> str:
    """A small numbered badge at a bar's left edge, standing in for a name that doesn't fit."""
    x, y = tenure.start_x, tenure.y
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


def _render_exit_cap(tenure: Tenure) -> str:
    """A plain end-cap marker for an asset that left Memphis (no destination text on the cap)."""
    x, y = tenure.end_x, tenure.y
    marker = (
        f'<path class="exit-marker" d="M{x:.2f},{y - 4:.1f} L{x + 5:.2f},{y:.1f} '
        f'L{x:.2f},{y + 4:.1f} Z" fill="{COLOR_CAP}"/>'
    )
    return (
        f'<g class="exit" data-asset-id={quoteattr(tenure.asset_id)} '
        f'data-destination={quoteattr(tenure.exit_holder or "")}>'
        f'<title>{escape(f"Left MEM → {tenure.exit_holder}")}</title>'
        f"{marker}</g>"
    )


def _render_hubs(
    nodes: list[dict[str, Any]],
    tenures: list[Tenure],
    node_x: dict[str, float],
    node_kind: dict[str, str],
) -> str:
    arriving: dict[str, list[Tenure]] = {}
    departing: dict[str, list[Tenure]] = {}
    for tenure in tenures:
        arriving.setdefault(tenure.start_node, []).append(tenure)
        if tenure.end_node is not None:
            departing.setdefault(tenure.end_node, []).append(tenure)

    parts = []
    for node in nodes:
        if node["kind"] in FLAT_NODE_KINDS:
            continue
        outs = sorted(departing.get(node["id"], []), key=lambda t: (t.y, t.order))
        ins = sorted(arriving.get(node["id"], []), key=lambda t: (t.y, t.order))
        if not outs and not ins:
            continue
        x = node_x[node["id"]]
        hub_y = sum(t.y for t in outs + ins) / len(outs + ins)
        fill = _hub_kind_fill(node["kind"])
        parts.append(
            f'<g class="hub" data-node-id={quoteattr(node["id"])} data-kind={quoteattr(node["kind"])} '
            f'data-out="{len(outs)}" data-in="{len(ins)}">'
            f'<title>{escape(node["description"])}</title>'
        )
        for tenure in outs:
            parts.append(_connector("out", tenure, x - tenure.lag, tenure.y, x, hub_y, tenure.lag))
        for tenure in ins:
            parts.append(_connector("in", tenure, x, hub_y, x + tenure.lead, tenure.y, tenure.lead))
        parts.append(
            f'<circle class="hub-marker" cx="{x:.2f}" cy="{hub_y:.1f}" r="{HUB_RADIUS}" '
            f'fill="{fill}" stroke="{COLOR_SURFACE}" stroke-width="1.5"/>'
        )
        parts.append("</g>")
    return "".join(parts)


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
    for node in sorted(labelled, key=lambda n: (node_x[n["id"]], n["id"])):
        x = node_x[node["id"]]
        level = 1 - level if x - previous_x < NODE_LABEL_MIN_GAP else 0
        previous_x = x
        y = NODE_LABEL_Y + level * NODE_LABEL_STAGGER
        date = _parse_date(node["date"])
        kind = node["kind"].replace("_", " ")
        label = escape(f'{date.strftime("%b")} {date.day} {kind}')
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


def _legend_swatch_row(
    y: float, entries: list[tuple[str, str, str]]
) -> str:
    """One row of `(shape, color, caption)` swatches, `shape` one of "bar"/"circle"/"cap"."""
    parts = []
    x = float(PLOT_X0)
    for shape, color, caption in entries:
        if shape == "bar":
            parts.append(
                f'<rect x="{x:.1f}" y="{y - BAR_HEIGHT / 2:.1f}" width="26" height="{BAR_HEIGHT}" '
                f'rx="2" fill="{color}"/>'
            )
            text_x = x + 31
        elif shape == "circle":
            parts.append(f'<circle cx="{x + 6:.1f}" cy="{y - 3:.1f}" r="{HUB_RADIUS}" fill="{color}"/>')
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
        text = (
            f"{number}. {label} ({start_date.strftime('%b %d')} → {end_date.strftime('%b %d')})"
        )
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
