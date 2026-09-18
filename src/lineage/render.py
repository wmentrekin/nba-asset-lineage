"""Hand-written SVG rendering of graph.json: no plotting library, no PNG.

Layout: x is time (linear, window.start to window.end); one horizontal lane per asset,
players in a top band and picks in a band below, in the order `export` gives them; a
transaction node is a vertical tick spanning the lanes it touches, with a small circle on
each; a strand segment is a horizontal bar on its lane, colored by holder. Two runs over the
same graph.json produce byte-identical output: every list here is already in a fixed order,
and nothing reads the clock.
"""

import datetime as dt
import json
import pathlib
from typing import Any
from xml.sax.saxutils import escape, quoteattr

WIDTH = 1600
LEFT_GUTTER = 240
RIGHT_PADDING = 40
TOP_MARGIN = 130
LANE_HEIGHT = 18
BAND_GAP = 26
BOTTOM_LEGEND = 70
ROTATE_LABEL_THRESHOLD = 12

BAR_HEIGHT = {"standard": 10, None: 10, "two_way": 6, "ten_day": 3}

# Colors: MEM gets the strong categorical hue (blue, slot 1 of the validated default
# palette); any other NBA team is a muted neutral so MEM strands read as the subject; FA,
# DRAFT and USED (an asset that has left play) are drawn very light and dashed.
COLOR_MEM = "#2a78d6"
COLOR_OTHER_TEAM = "#9c9a92"
COLOR_INACTIVE = "#d8d6cd"
COLOR_TEXT_PRIMARY = "#0b0b0b"
COLOR_TEXT_SECONDARY = "#52514e"
COLOR_SURFACE = "#fcfcfb"
COLOR_GUIDE = "#e3e1d9"
COLOR_NODE_LINE = "#8a8880"

INACTIVE_HOLDERS = {"FA", "USED", "DRAFT"}

TITLE = "Memphis Grizzlies asset lineage, 2025-26 → today"


def _parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _holder_color(holder: str) -> str:
    if holder == "MEM":
        return COLOR_MEM
    if holder in INACTIVE_HOLDERS:
        return COLOR_INACTIVE
    return COLOR_OTHER_TEAM


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
    months = []
    year, month = start.year, start.month
    while dt.date(year, month, 1) <= end:
        months.append(dt.date(year, month, 1))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _lane_layout(assets: list[dict[str, Any]]) -> tuple[dict[str, float], float]:
    """Return {asset_id: lane_center_y} and the y just past the last lane."""
    y = TOP_MARGIN + LANE_HEIGHT / 2
    centers: dict[str, float] = {}
    previous_type: str | None = None
    for asset in assets:
        if previous_type is not None and asset["type"] != previous_type:
            y += BAND_GAP
        centers[asset["id"]] = y
        y += LANE_HEIGHT
        previous_type = asset["type"]
    return centers, y - LANE_HEIGHT / 2 + LANE_HEIGHT / 2


def _svg_open(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{COLOR_SURFACE}"/>'
    )


def render_svg(export: dict[str, Any]) -> str:
    """Render a graph.json dict (as produced by `lineage.export.build_export`) to SVG."""
    start = _parse_date(export["window"]["start"])
    end = _parse_date(export["window"]["end"])
    assets = export["assets"]
    nodes = export["nodes"]

    lane_centers, last_lane_y = _lane_layout(assets)
    height = int(last_lane_y + LANE_HEIGHT + BOTTOM_LEGEND) if assets else TOP_MARGIN + BOTTOM_LEGEND
    scale = Scale(start, end, LEFT_GUTTER, WIDTH - RIGHT_PADDING)

    parts = [_svg_open(WIDTH, height)]
    parts.append(
        f'<text x="{LEFT_GUTTER}" y="24" font-size="18" font-weight="bold" '
        f'fill="{COLOR_TEXT_PRIMARY}">{escape(TITLE)}</text>'
    )

    parts.append(_render_month_axis(start, end, scale))
    parts.append(_render_lanes(assets, lane_centers, scale, start, end))
    parts.append(_render_asset_labels(assets, lane_centers))

    strands_by_id = {strand["asset_id"]: strand for strand in export["strands"]}
    node_dates = {node["id"]: _parse_date(node["date"]) for node in nodes}
    touched_lanes = _touched_lanes(nodes, assets, strands_by_id)
    parts.append(
        _render_segments(assets, strands_by_id, lane_centers, scale, node_dates, end)
    )
    parts.append(_render_nodes(nodes, lane_centers, scale, touched_lanes))
    parts.append(_render_legend(height))

    parts.append("</svg>")
    return "".join(parts)


def _render_month_axis(start: dt.date, end: dt.date, scale: Scale) -> str:
    months = _month_starts(start, end)
    rotate = len(months) > ROTATE_LABEL_THRESHOLD
    axis_y = TOP_MARGIN - 14
    parts = [
        f'<g class="axis">'
        f'<line x1="{scale(start):.1f}" y1="{axis_y:.1f}" x2="{scale(end):.1f}" '
        f'y2="{axis_y:.1f}" stroke="{COLOR_GUIDE}" stroke-width="1"/>'
    ]
    for month in months:
        x = scale(month)
        label = escape(month.strftime("%b %Y"))
        transform = f' transform="rotate(-45 {x:.1f} {axis_y - 6:.1f})"' if rotate else ""
        anchor = "end" if rotate else "middle"
        parts.append(
            f'<line x1="{x:.1f}" y1="{axis_y - 4:.1f}" x2="{x:.1f}" y2="{axis_y + 4:.1f}" '
            f'stroke="{COLOR_GUIDE}" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{axis_y - 6:.1f}" font-size="10" text-anchor="{anchor}" '
            f'fill="{COLOR_TEXT_SECONDARY}"{transform}>{label}</text>'
        )
    parts.append("</g>")
    return "".join(parts)


def _render_lanes(
    assets: list[dict[str, Any]],
    lane_centers: dict[str, float],
    scale: Scale,
    start: dt.date,
    end: dt.date,
) -> str:
    parts = []
    x0, x1 = scale(start), scale(end)
    for asset in assets:
        y = lane_centers[asset["id"]]
        parts.append(
            f'<g class="lane" data-asset-id={quoteattr(asset["id"])} '
            f'data-asset-type={quoteattr(asset["type"])}>'
            f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x1:.1f}" y2="{y:.1f}" '
            f'stroke="{COLOR_GUIDE}" stroke-width="1"/>'
            "</g>"
        )
    return "".join(parts)


def _render_asset_labels(assets: list[dict[str, Any]], lane_centers: dict[str, float]) -> str:
    parts = []
    for asset in assets:
        y = lane_centers[asset["id"]]
        parts.append(
            f'<text x="{LEFT_GUTTER - 10:.1f}" y="{y + 3:.1f}" font-size="10" '
            f'text-anchor="end" fill="{COLOR_TEXT_PRIMARY}">{escape(asset["label"])}</text>'
        )
    return "".join(parts)


def _render_segments(
    assets: list[dict[str, Any]],
    strands_by_id: dict[str, dict[str, Any]],
    lane_centers: dict[str, float],
    scale: Scale,
    node_dates: dict[str, dt.date],
    window_end: dt.date,
) -> str:
    parts = []
    for asset in assets:
        strand = strands_by_id.get(asset["id"])
        if strand is None:
            continue
        y = lane_centers[asset["id"]]
        for segment in strand["segments"]:
            from_date = node_dates[segment["from_node"]]
            to_date = node_dates[segment["to_node"]] if segment["to_node"] else window_end
            x_from, x_to = scale(from_date), scale(to_date)
            bar_height = BAR_HEIGHT.get(segment["contract_type"], BAR_HEIGHT[None])
            color = _holder_color(segment["holder"])
            dash = ' stroke-dasharray="4,3"' if segment["holder"] in INACTIVE_HOLDERS else ""
            stroke = f' stroke="{color}" stroke-width="1"{dash}' if dash else ""
            parts.append(
                f'<rect class="segment" data-asset-id={quoteattr(asset["id"])} '
                f'data-from-node={quoteattr(segment["from_node"] or "")} '
                f'data-to-node={quoteattr(segment["to_node"] or "")} '
                f'x="{min(x_from, x_to):.2f}" y="{y - bar_height / 2:.1f}" '
                f'width="{max(x_to - x_from, 0):.2f}" height="{bar_height}" '
                f'rx="2" fill="{color}"{stroke}/>'
            )
    return "".join(parts)


def _touched_lanes(
    nodes: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    strands_by_id: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    """A lane is "touched" by a node when a segment starts there, i.e. some movement in
    that transaction affected that asset.

    Returns plain lists, each in lane order (the fixed `assets` order), never sets: a set's
    iteration order for string keys depends on PYTHONHASHSEED, which would make the emitted
    circle order - and so the SVG bytes - vary across processes.
    """
    touched: dict[str, list[str]] = {node["id"]: [] for node in nodes}
    seen: dict[str, set[str]] = {node["id"]: set() for node in nodes}
    for asset in assets:
        strand = strands_by_id.get(asset["id"])
        if strand is None:
            continue
        for segment in strand["segments"]:
            from_node = segment["from_node"]
            if from_node in touched and asset["id"] not in seen[from_node]:
                touched[from_node].append(asset["id"])
                seen[from_node].add(asset["id"])
    return touched


def _render_nodes(
    nodes: list[dict[str, Any]],
    lane_centers: dict[str, float],
    scale: Scale,
    touched_lanes: dict[str, list[str]],
) -> str:
    return "".join(
        _render_one_node(node, lane_centers, scale, touched_lanes[node["id"]])
        for node in nodes
    )


def _render_one_node(
    node: dict[str, Any],
    lane_centers: dict[str, float],
    scale: Scale,
    touched_asset_ids: list[str],
) -> str:
    x = scale(_parse_date(node["date"]))
    ys = [lane_centers[asset_id] for asset_id in touched_asset_ids if asset_id in lane_centers]
    if not ys:
        y_top = y_bottom = TOP_MARGIN
    else:
        y_top, y_bottom = min(ys) - LANE_HEIGHT / 2, max(ys) + LANE_HEIGHT / 2

    label = escape(f'{node["date"]} {node["kind"]}')
    parts = [
        f'<g class="node" data-node-id={quoteattr(node["id"])}>'
        f'<title>{escape(node["description"])}</title>'
        f'<line x1="{x:.2f}" y1="{y_top:.1f}" x2="{x:.2f}" y2="{y_bottom:.1f}" '
        f'stroke="{COLOR_NODE_LINE}" stroke-width="1"/>'
    ]
    for y in ys:
        parts.append(
            f'<circle cx="{x:.2f}" cy="{y:.1f}" r="2.5" fill="{COLOR_SURFACE}" '
            f'stroke="{COLOR_NODE_LINE}" stroke-width="1"/>'
        )
    parts.append(
        f'<text x="{x:.2f}" y="{TOP_MARGIN - 20:.1f}" font-size="8" '
        f'text-anchor="start" fill="{COLOR_TEXT_SECONDARY}" '
        f'transform="rotate(-45 {x:.2f} {TOP_MARGIN - 20:.1f})">{label}</text>'
    )
    parts.append("</g>")
    return "".join(parts)


def _render_legend(height: int) -> str:
    y = height - BOTTOM_LEGEND + 24
    entries = [
        (COLOR_MEM, "Memphis Grizzlies"),
        (COLOR_OTHER_TEAM, "Other NBA team"),
        (COLOR_INACTIVE, "Free agency / drafted / used"),
    ]
    parts = ['<g class="legend">']
    x = LEFT_GUTTER
    for color, label in entries:
        parts.append(
            f'<rect x="{x}" y="{y - 8}" width="14" height="10" fill="{color}"/>'
            f'<text x="{x + 20}" y="{y}" font-size="10" fill="{COLOR_TEXT_PRIMARY}">'
            f"{escape(label)}</text>"
        )
        x += 20 + 12 * len(label) + 30
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
