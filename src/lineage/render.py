"""Hand-written SVG rendering of graph.json: no plotting library, no PNG.

Layout ("compacting stack"): x is time (linear, window.start to window.end) and a row is a
*rank*, not a slot. Only Memphis tenure is drawn, and assets/nodes graph.json marks `hidden`
(10-day-only signings) are not drawn at all. Three bands stack top to bottom: the roster
(standard / 10-day / draft-rights contracts), the three reserved two-way rows, and the
Memphis-owned picks.

Roster and two-way rows are ordered by tenure, longest-serving on top, so an arrival always
enters at the bottom. A strand's own transaction is drawn at its node: an arrival starts there,
a departure ends there, and a two-way conversion or a draft selection curves up into the bottom
of the roster band right there. The *knock-on* re-rank a departure causes (the rows below
closing up) starts a fixed gap past the node that caused it, whatever else is nearby, so the
stack closes promptly. Each hole is closed by its own shift; when two shifts in a band overlap
in x, a strand caught by both runs one S-curve from the first start to the later finish, so
every strand's y is still a step function and no close waits on a later one. The two-way band
is the exception that proves the rule: it may never draw more than three rows, so a same-day
two-way swap closes its hole at the node itself.

The picks band is a column of fixed per-draft-year blocks, in year order: a block exists from
the first day Memphis holds one of that year's picks (or the year becomes tradeable at its
`pick_horizon` node) to the day its last pick is used or traded. Every pick of that year Memphis
holds at any point in the window owns one fixed slot in the block, in graph.json `sort_key`
order (round, Memphis's own first, original team), so a traded-in pick fills an empty slot and
nothing else moves. Blocks move only when one disappears after its draft: every block below
then shifts up together, once, the same gap past that draft.

Styling follows the owner's personal-site design system (DESIGN.md, the Grizzlies band
palette and its project artwork): a navy canvas, pale blue strands whose shade (opacity, never
hue or width) encodes contract type, and one lineage — by default the Jaren Jackson Jr. trade
tree — drawn in the gold accent on top of everything else, like the artwork's "hot" strand.

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

WIDTH = 2400
PLOT_X0 = 100
PLOT_X1 = WIDTH - 90
# A tenure MEM still holds runs past the axis end into this overhang, so an asset acquired on
# the window's last day still gets a visible strand.
OPEN_END_X = PLOT_X1 + 44
TITLE_Y = 38
SUBTITLE_Y = 62
# Transaction captions sit on up to NODE_LABEL_LEVELS staggered lines above the month axis.
NODE_LABEL_Y = 76
TOP_MARGIN = 164

# One rank = one row. Rows are dense (the stack compacts), so they are a touch tighter than
# v3's reusable lanes while the strand itself stays the same visual weight.
ROW_HEIGHT = 13.0
# Bands are separated by space and one hairline at the middle of the gap, nothing else.
BAND_GAP = 34.0
# Draft-year blocks in the picks band are separated by this many empty rows.
YEAR_GAP_ROWS = 1.0
# NBA rule: a team may carry three two-way contracts, so that band is three rows whatever the
# data says.
TWO_WAY_ROWS = 3

# Every rank change is drawn as a cubic S-curve this wide (the artwork's horizontal-tangent
# "flow" curve).
TRANSITION = 40.0
# A knock-on shift starts this far past the node that caused it.
SHIFT_GAP = 1.5 * TRANSITION
# At a trade a strand stops this far short of the hub; the gap is where the connector fans.
CONNECTOR_OFFSET = 56.0
MIN_RUN = 4.0
HUB_RADIUS = 4.5
STRAND_WIDTH = 7.0
# A departure ends in a filled dot a little wider than the strand, like the artwork's `ends`.
END_CAP_RADIUS = 5.0

NODE_LABEL_STAGGER = 14
NODE_LABEL_LEVELS = 4
NODE_LABEL_PAD = 10.0
MONTH_ROTATE_THRESHOLD = 24

LABEL_FONT = 9
# Instrument Sans averages ~0.52em per character; used to decide whether a row leaves enough
# room for a tenure's full name, since there is no text-measuring API in plain SVG.
LABEL_CHAR_WIDTH = LABEL_FONT * 0.52
MIN_LABEL_WIDTH = 24.0

# Nodes of these kinds never get a marker: a baseline is the left edge of the window and a
# pick_horizon is a draft year becoming tradeable (its year block appearing says that).
FLAT_NODE_KINDS = frozenset({"baseline", "pick_horizon"})
NODE_CAPTIONS = {"trade": "Trade", "draft_selection": "Draft"}

# Hub-marker kind families: every transaction kind that starts, ends or changes a tenure falls
# into exactly one of these.
SIGNING_KINDS = frozenset({"signing", "two_way_signing", "two_way_conversion", "ten_day"})
EXIT_KINDS = frozenset({"waiver", "contract_void", "expiry"})

# Colors: the Grizzlies band palette from the owner's site (projects.ts) plus the site's
# `--bad` token for exits. Contract type is a *shade* of the foreground (stroke-opacity), never
# a new hue, so the one gold lineage is the only thing on the page that shouts.
COLOR_BACKGROUND = "#1b2a5c"
COLOR_FOREGROUND = "#aebfe8"
COLOR_ACCENT = "#f6b61c"
COLOR_BAD = "#ef6b5e"
COLOR_HAIRLINE = "rgba(174,191,232,0.15)"
TEXT_SECONDARY_OPACITY = 0.7

# (stroke, stroke-opacity) per contract type; every strand is the same width.
CONTRACT_SHADES = {
    "standard": (COLOR_FOREGROUND, 1.0),
    None: (COLOR_FOREGROUND, 1.0),
    "two_way": (COLOR_FOREGROUND, 0.5),
    "ten_day": (COLOR_FOREGROUND, 0.75),
    # Gold, but faint enough not to compete with the highlighted lineage.
    "draft_rights": (COLOR_ACCENT, 0.45),
}
PICK_SHADE = (COLOR_FOREGROUND, 0.3)
HIGHLIGHT_SHADE = (COLOR_ACCENT, 1.0)
CONNECTOR_OPACITY = 0.4

# The seed of the lineage drawn in gold unless `--highlight` names another (or none).
DEFAULT_HIGHLIGHT = "1628991"  # Jaren Jackson Jr.

SERIF = '"Newsreader", Georgia, serif'
SANS = '"Instrument Sans", "Helvetica Neue", sans-serif'
# Newsreader as the site sets headings: weight 500, tightened tracking.
SERIF_ATTRS = f'font-family={quoteattr(SERIF)} font-weight="500" letter-spacing="-0.02em"'

ROSTER, TWO_WAY, PICK = "roster", "two_way", "pick"
BANDS = (ROSTER, TWO_WAY, PICK)
BAND_TITLES = {ROSTER: "Roster", TWO_WAY: "Two-Way", PICK: "Picks"}

TITLE = "Memphis Grizzlies Asset Lineage, 2025–26 to Today"

# Legend layout: two fixed rows (contract shades, then markers), plus a variable-height block
# of numbered entries for tenures whose full name didn't fit.
LEGEND_TOP_PAD = 40.0
LEGEND_ROW_GAP = 22.0
LEGEND_BOTTOM_PAD = 18.0
NUMBERED_LEGEND_GAP = 22.0
NUMBERED_ROW_HEIGHT = 14.0
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


def _pick_sort_key(asset: dict[str, Any]) -> tuple[int, int, int, str]:
    """A pick's (draft year, round, own_first, original team) key, as graph.json carries it.

    An export from before the four-part key carried (round, draft year, original team); it is
    read into the same shape, with Memphis's own pick first.
    """
    key = asset["sort_key"]
    if len(key) == 4:
        return (int(key[0]), int(key[1]), int(key[2]), str(key[3]))
    team = str(key[2])
    return (int(key[1]), int(key[0]), 0 if team == "MEM" else 1, team)


def _pick_short_label(pick_key: tuple[int, int, int, str]) -> str:
    """'R1 LAL': the year is already on the block, so a slot only names round and team."""
    return f"R{pick_key[1]} {pick_key[3]}"


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
    pick_key: tuple[int, int, int, str] | None
    restart_nodes: list[str]
    # Filled in by the rank walk and the placement pass.
    placements: list[tuple[float, str, float]] = field(default_factory=list)
    lead: float = 0.0
    lag: float = 0.0
    start_x: float = 0.0
    end_x: float = 0.0
    entry_y: float | None = None
    continues_as: str | None = None
    highlighted: bool = False
    bounds: list[float] = field(default_factory=list)

    def sort_key(self) -> tuple[Any, ...]:
        if self.pick_key is not None:
            return (*self.pick_key, self.asset_id)
        return (self.sort_start, self.label, self.asset_id)

    @property
    def display_label(self) -> str:
        """The name drawn beside the strand (a pick drops the year its block already shows)."""
        if self.pick_key is not None:
            return _pick_short_label(self.pick_key)
        return self.label

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
    """Split every visible strand into its MEM tenures, in graph.json asset order.

    An asset graph.json marks `hidden` never becomes a tenure, so it never takes a row.
    Consecutive MEM segments (a two-way conversion, a re-signing, a back-to-back 10-day) are
    one tenure with an internal boundary, not an exit and a re-entry.
    """
    segments_by_asset = {strand["asset_id"]: strand["segments"] for strand in strands}
    tenures: list[Tenure] = []
    for order, asset in enumerate(assets):
        if asset.get("hidden", False):
            continue
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


@dataclass
class PickBlock:
    """One draft year's block in the picks band: fixed slots, and where the block sat when."""

    year: int
    slots: list[str]
    first_x: float = 0.0
    # (x, rows offset of the block's first slot) every time the block is placed or moved.
    offsets: list[tuple[float, float]] = field(default_factory=list)
    last_x: float | None = None


def _pick_blocks(tenures: list[Tenure]) -> dict[int, PickBlock]:
    """{draft year: block}, each block's slots every pick of that year MEM ever holds, sorted."""
    keys: dict[str, tuple[int, int, int, str]] = {}
    for tenure in tenures:
        if tenure.pick_key is not None:
            keys[tenure.asset_id] = tenure.pick_key
    ordered = sorted(keys, key=lambda asset_id: (keys[asset_id], asset_id))
    blocks: dict[int, PickBlock] = {}
    for asset_id in ordered:
        year = keys[asset_id][0]
        blocks.setdefault(year, PickBlock(year=year, slots=[])).slots.append(asset_id)
    return blocks


class _Stack:
    """The rows every band holds at the x the walk has reached.

    Roster and two-way rows are tenure ranks with holes allowed: a departure leaves its row
    empty, remembered with the x it was made at, until the shift scheduled for it closes it.
    Pick rows are a year block's offset plus a fixed slot; a used-up block keeps its space the
    same way until its shift.
    """

    def __init__(self, blocks: dict[int, PickBlock]):
        self.rows: dict[str, list[tuple[Tenure, float]]] = {ROSTER: [], TWO_WAY: [], PICK: []}
        # (row, x the hole was made at), per rank band.
        self.holes: dict[str, list[tuple[float, float]]] = {ROSTER: [], TWO_WAY: []}
        self.blocks = blocks
        # Every block taking space in the picks band, live or used up and not yet closed.
        self.block_offset: dict[int, float] = {}
        self.block_live: dict[int, int] = {}
        self.heights = {band: 0.0 for band in BANDS}

    def _place(self, tenure: Tenure, x: float, band: str, rows: float) -> None:
        if not tenure.placements or tenure.placements[-1][1:] != (band, rows):
            tenure.placements.append((x, band, rows))
        self.heights[band] = max(self.heights[band], rows + 1)

    def _trim(self, band: str) -> None:
        """Forget holes below the last occupied row: nothing sits under them to close up."""
        bottom = max((rows for _, rows in self.rows[band]), default=-1.0)
        self.holes[band] = [hole for hole in self.holes[band] if hole[0] < bottom]

    def remove(self, tenure: Tenure, band: str, x: float) -> bool:
        """Take `tenure` out of `band` at `x`; True when that leaves something to close."""
        row = next(rows for entry, rows in self.rows[band] if entry is tenure)
        self.rows[band] = [entry for entry in self.rows[band] if entry[0] is not tenure]
        if band == PICK:
            year = tenure.pick_key[0]
            self.block_live[year] -= 1
            if self.block_live[year]:
                return False
            self.blocks[year].last_x = x
            return True
        self.holes[band].append((row, x))
        self._trim(band)
        return bool(self.holes[band])

    def add(self, arrivals: list[Tenure], band: str, x: float) -> None:
        """Arrivals take the rows below the band's last occupied row, in tenure order."""
        if band == PICK:
            for tenure in arrivals:
                self._add_pick(tenure, x)
            return
        if not arrivals:
            return
        self._trim(band)
        bottom = max((rows for _, rows in self.rows[band]), default=-1.0)
        if band == TWO_WAY and bottom + len(arrivals) >= TWO_WAY_ROWS and self.holes[band]:
            # A two-way swap: the band may never draw a fourth row, so close up at the node.
            self.compact(band, x, x)
            bottom = max((rows for _, rows in self.rows[band]), default=-1.0)
        for tenure in sorted(arrivals, key=lambda t: t.sort_key()):
            bottom += 1
            self.rows[band].append((tenure, bottom))
            self._place(tenure, x, band, bottom)

    def _add_pick(self, tenure: Tenure, x: float) -> None:
        year = tenure.pick_key[0]
        block = self.blocks[year]
        if year not in self.block_offset:
            # A new block goes below every block on the page, held or still waiting to close.
            offset = 0.0
            for other, other_offset in self.block_offset.items():
                offset = max(offset, other_offset + len(self.blocks[other].slots) + YEAR_GAP_ROWS)
            self.block_offset[year] = offset
            self.block_live[year] = 0
            block.first_x = x
            block.offsets.append((x, offset))
        self.block_live[year] += 1
        rows = self.block_offset[year] + block.slots.index(tenure.asset_id)
        self.rows[PICK].append((tenure, rows))
        self._place(tenure, x, PICK, rows)

    def compact(self, band: str, x: float, upto: float) -> None:
        """At `x`, close every hole in `band` made at or before `upto`; later holes stay open
        (renumbered) for their own shifts. One synchronized shift for all who move."""
        if band == PICK:
            self._compact_picks(x, upto)
            return
        closing = [row for row, made in self.holes[band] if made <= upto]
        if not closing:
            return

        def closed_above(row: float) -> int:
            return sum(1 for hole in closing if hole < row)

        self.holes[band] = [
            (row - closed_above(row), made) for row, made in self.holes[band] if made > upto
        ]
        self.rows[band] = [(tenure, rows - closed_above(rows)) for tenure, rows in self.rows[band]]
        for tenure, rows in self.rows[band]:
            self._place(tenure, x, band, rows)

    def _compact_picks(self, x: float, upto: float) -> None:
        for year in sorted(self.block_offset):
            last_x = self.blocks[year].last_x
            if last_x is not None and last_x <= upto:
                del self.block_offset[year]
                del self.block_live[year]
        top = 0.0
        for year in sorted(self.block_offset):
            block = self.blocks[year]
            self.block_offset[year] = top
            if block.last_x is None and block.offsets[-1][1] != top:
                block.offsets.append((x, top))
            top += len(block.slots) + YEAR_GAP_ROWS
        entries = []
        for tenure, _ in self.rows[PICK]:
            year = tenure.pick_key[0]
            entries.append(
                (tenure, self.block_offset[year] + self.blocks[year].slots.index(tenure.asset_id))
            )
        self.rows[PICK] = entries
        for tenure, rows in entries:
            self._place(tenure, x, PICK, rows)


def _walk_ranks(
    tenures: list[Tenure], nodes: list[dict[str, Any]], scale: Scale
) -> tuple[dict[str, float], dict[int, PickBlock]]:
    """Assign every tenure its rows over x; return each band's height and the pick blocks.

    Dates, not nodes, are the beat: two transactions on the same day land on the same x, so
    they are applied together (departures, then tenure restarts, then arrivals) at that x. Each
    date that opens a hole schedules that band's shift at x + SHIFT_GAP, closing only the holes
    made up to that date, so nearby markers and later departures never delay it.
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

    blocks = _pick_blocks(tenures)
    stack = _Stack(blocks)
    band_of: dict[int, str] = {
        id(tenure): _segment_band(tenure.asset_type, tenure.segments[0]) for tenure in tenures
    }
    # (shift x, band, close holes made up to this x), in the order they were scheduled.
    scheduled: list[tuple[float, str, float]] = []

    def run_shifts(until: float) -> None:
        due = sorted(
            (entry for entry in scheduled if entry[0] <= until),
            key=lambda entry: (entry[0], BANDS.index(entry[1])),
        )
        for entry in due:
            scheduled.remove(entry)
            stack.compact(entry[1], entry[0], entry[2])

    dates: list[dt.date] = []
    by_date: dict[dt.date, list[dict[str, Any]]] = {}
    for node in nodes:
        date = _parse_date(node["date"])
        if date not in by_date:
            by_date[date] = []
            dates.append(date)
        by_date[date].append(node)

    for date in dates:
        x = scale(date)
        same_day = by_date[date]
        run_shifts(x)

        opened: list[str] = []
        for node in same_day:
            leaving = [(tenure, band_of[id(tenure)]) for tenure in departures.get(node["id"], [])]
            leaving += [(tenure, from_band) for tenure, from_band, _ in moves.get(node["id"], [])]
            for tenure, band in leaving:
                if stack.remove(tenure, band, x) and band not in opened:
                    opened.append(band)
        for node in same_day:
            for tenure in restarts.get(node["id"], []):
                tenure.sort_start = date
        incoming: dict[str, list[Tenure]] = {band: [] for band in BANDS}
        for node in same_day:
            for tenure, _, to_band in moves.get(node["id"], []):
                incoming[to_band].append(tenure)
                band_of[id(tenure)] = to_band
            for tenure in arrivals.get(node["id"], []):
                band = _segment_band(tenure.asset_type, tenure.segments[0])
                incoming[band].append(tenure)
                band_of[id(tenure)] = band
        for band in BANDS:
            stack.add(incoming[band], band, x)
        for band in BANDS:
            if band in opened:
                scheduled.append((x + SHIFT_GAP, band, x))

    run_shifts(math.inf)

    heights = dict(stack.heights)
    heights[TWO_WAY] = max(heights[TWO_WAY], float(TWO_WAY_ROWS))
    return heights, blocks


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
    caused it". A change that starts while the previous one is still running joins it: one
    curve from the earlier start to the later finish, so overlapping shifts compose instead of
    stacking two steep curves. A curve is clipped short when the strand ends first.
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
    current_y = stops[0][1]
    index = 1
    while index < len(stops):
        start = max(stops[index][0], cursor)
        # A shift scheduled past the strand's end (the window closes first) is never drawn.
        if start >= tenure.end_x:
            break
        finish, target = start + TRANSITION, stops[index][1]
        while index + 1 < len(stops) and stops[index + 1][0] < finish:
            index += 1
            finish, target = max(finish, stops[index][0] + TRANSITION), stops[index][1]
        finish = min(finish, tenure.end_x)
        if start > cursor:
            pieces.append(("H", cursor, start, current_y))
        pieces.append(("S", start, finish, current_y, target))
        cursor, current_y = finish, target
        index += 1
    if cursor < tenure.end_x or not pieces:
        pieces.append(("H", cursor, max(tenure.end_x, cursor), current_y))
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


def _highlight_lineage(
    tenures: list[Tenure], node_kind: dict[str, str], seed: str | None
) -> str | None:
    """Mark the seed's trade tree as highlighted; return the seed's label (None: no seed).

    The lineage is every tenure of the seed asset plus, transitively, every asset Memphis
    received in a trade a highlighted tenure left Memphis in, and the player a highlighted pick
    was used on. Tenures are visited in graph.json order until nothing changes, so the result
    depends only on graph.json.
    """
    if seed is None:
        return None
    seeds = [tenure for tenure in tenures if tenure.asset_id == seed]
    if not seeds:
        raise ValueError(f"--highlight {seed}: no drawn asset has that id")
    for tenure in seeds:
        tenure.highlighted = True
    changed = True
    while changed:
        changed = False
        for tenure in tenures:
            if tenure.highlighted:
                continue
            traded_for = node_kind.get(tenure.start_node) == "trade" and any(
                other.highlighted and other.exit_holder and other.end_node == tenure.start_node
                for other in tenures
            )
            drafted_with = any(
                other.highlighted
                and other.continues_as == tenure.asset_id
                and other.end_node == tenure.start_node
                for other in tenures
            )
            if traded_for or drafted_with:
                tenure.highlighted = True
                changed = True
    return seeds[0].label


def _segment_shade(tenure: Tenure, segment: dict[str, Any]) -> tuple[str, float]:
    """(stroke, stroke-opacity) of one contract segment: gold for the lineage, else its shade."""
    if tenure.highlighted:
        return HIGHLIGHT_SHADE
    if tenure.asset_type == "pick":
        return PICK_SHADE
    return CONTRACT_SHADES.get(segment["contract_type"], CONTRACT_SHADES[None])


def _hub_marker_paint(kind: str) -> tuple[str, str]:
    """(fill, stroke) of a hub marker: gold trade, pale signing, red exit, gold draft ring."""
    if kind == "trade":
        return COLOR_ACCENT, COLOR_BACKGROUND
    if kind in EXIT_KINDS:
        return COLOR_BAD, COLOR_BACKGROUND
    if kind == "draft_selection":
        return COLOR_BACKGROUND, COLOR_ACCENT
    return COLOR_FOREGROUND, COLOR_BACKGROUND


def _fits(tenure: Tenure, budget: float) -> bool:
    """Whether a tenure's full label fits in the room its row leaves before the next occupant."""
    return budget >= MIN_LABEL_WIDTH and budget >= len(tenure.display_label) * LABEL_CHAR_WIDTH


def render_svg(export: dict[str, Any], highlight: str | None = DEFAULT_HIGHLIGHT) -> str:
    """Render a graph.json dict (as produced by `lineage.export.build_export`) to SVG.

    `highlight` is the asset id whose trade tree is drawn in gold; None draws no lineage.
    """
    start = _parse_date(export["window"]["start"])
    end = _parse_date(export["window"]["end"])
    scale = Scale(start, end, PLOT_X0, PLOT_X1)

    nodes = sorted(export["nodes"], key=lambda node: (node["date"], node["id"]))
    node_x = {node["id"]: scale(_parse_date(node["date"])) for node in nodes}
    node_kind = {node["id"]: node["kind"] for node in nodes}
    node_date = {node["id"]: _parse_date(node["date"]) for node in nodes}

    tenures = _tenures(export["assets"], export["strands"], node_date, start)
    continuations = _draft_continuations(nodes, tenures)
    highlight_label = _highlight_lineage(tenures, node_kind, highlight)
    heights, blocks = _walk_ranks(tenures, nodes, scale)
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
    parts.append(_render_title(highlight_label))
    parts.append(_render_month_axis(start, end, scale))
    parts.append(_render_bands(heights, band_tops, blocks))
    parts.append(_render_strands(tenures, geometry, band_tops))
    parts.append(_render_hubs(nodes, tenures, node_x, band_tops))
    parts.append(_render_overlay(tenures, anchors, numbered))
    parts.append(_render_node_labels(nodes, node_x))
    parts.append(_render_legend(height, legend_height, numbered, highlight_label))
    parts.append("</svg>")
    return "".join(parts)


def _svg_open(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family={quoteattr(SANS)} '
        f'style="font-variant-numeric: tabular-nums">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{COLOR_BACKGROUND}"/>'
    )


def _render_title(highlight_label: str | None) -> str:
    parts = [
        f'<text class="title" x="{PLOT_X0}" y="{TITLE_Y}" font-size="26" {SERIF_ATTRS} '
        f'fill="{COLOR_FOREGROUND}">{escape(TITLE)}</text>'
    ]
    if highlight_label is not None:
        parts.append(
            f'<text class="highlight-note" x="{PLOT_X0}" y="{SUBTITLE_Y}" font-size="14" '
            f'fill="{COLOR_FOREGROUND}" fill-opacity="{TEXT_SECONDARY_OPACITY}">'
            f"Highlighted in gold: the {escape(highlight_label)} trade tree.</text>"
        )
    return "".join(parts)


def _render_month_axis(start: dt.date, end: dt.date, scale: Scale) -> str:
    months = _month_starts(start, end)
    rotate = len(months) > MONTH_ROTATE_THRESHOLD
    axis_y = TOP_MARGIN - 18
    parts = [
        (
            f'<g class="axis" fill="{COLOR_FOREGROUND}" fill-opacity="{TEXT_SECONDARY_OPACITY}">'
            f'<line x1="{scale(start):.1f}" y1="{axis_y:.1f}" x2="{scale(end):.1f}" '
            f'y2="{axis_y:.1f}" stroke="{COLOR_HAIRLINE}" stroke-width="1"/>'
        )
    ]
    for month in months:
        x = scale(month)
        label = escape(month.strftime("%b %Y"))
        transform = f' transform="rotate(-45 {x:.1f} {axis_y - 6:.1f})"' if rotate else ""
        anchor = "end" if rotate else "middle"
        parts.append(
            f'<line x1="{x:.1f}" y1="{axis_y - 3:.1f}" x2="{x:.1f}" y2="{axis_y + 3:.1f}" '
            f'stroke="{COLOR_HAIRLINE}" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{axis_y - 7:.1f}" font-size="11" {SERIF_ATTRS} '
            f'text-anchor="{anchor}"{transform}>{label}</text>'
        )
    parts.append("</g>")
    return "".join(parts)


def _render_bands(
    heights: dict[str, float], band_tops: dict[str, float], blocks: dict[int, PickBlock]
) -> str:
    """Each band's caption and extent, one hairline between neighbouring bands, and a year
    caption beside each pick block where it first appears.

    Pick rows move with their block; the block's own `pick-year` group records its slots and
    every (x, offset) it took, for tooling and tests.
    """
    parts = []
    drawn = [band for band in BANDS if heights[band]]
    for index, band in enumerate(drawn):
        parts.append(
            f'<g class="band" data-band={quoteattr(band)} data-top="{band_tops[band]:.1f}" '
            f'data-rows="{heights[band]:g}" data-row-height="{ROW_HEIGHT:g}">'
            f'<text class="band-title" x="{PLOT_X0 - 12}" y="{band_tops[band] + 11:.1f}" '
            f'font-size="15" {SERIF_ATTRS} text-anchor="end" fill="{COLOR_FOREGROUND}">'
            f"{escape(BAND_TITLES[band])}</text>"
        )
        if index:
            y = band_tops[band] - BAND_GAP / 2
            parts.append(
                f'<line class="band-rule" x1="{PLOT_X0}" y1="{y:.1f}" x2="{OPEN_END_X}" '
                f'y2="{y:.1f}" stroke="{COLOR_HAIRLINE}" stroke-width="1"/>'
            )
        if band == PICK:
            for year in sorted(blocks):
                parts.append(_render_pick_block(blocks[year], band_tops))
        parts.append("</g>")
    return "".join(parts)


def _render_pick_block(block: PickBlock, band_tops: dict[str, float]) -> str:
    """The year caption, set left of the block where it first appears and, for a block still
    held at the end, again past the right edge at the block's final position."""
    moves = " ".join(f"{x:.2f}:{offset:g}" for x, offset in block.offsets)
    end = "" if block.last_x is None else f' data-last-x="{block.last_x:.2f}"'
    parts = [
        (
            f'<g class="pick-year" data-year="{block.year}" '
            f'data-slots={quoteattr(" ".join(block.slots))} data-first-x="{block.first_x:.2f}"'
            f"{end} data-offsets={quoteattr(moves)}>"
        )
    ]
    first_caption_x = PLOT_X0 - 12 if block.first_x <= PLOT_X0 else block.first_x - 8
    captions = [(first_caption_x, block.offsets[0][1], "end")]
    if block.last_x is None:
        captions.append((OPEN_END_X + 10, block.offsets[-1][1], "start"))
    for x, offset, anchor in captions:
        middle = band_tops[PICK] + (offset + len(block.slots) / 2) * ROW_HEIGHT
        parts.append(
            f'<text class="pick-year-caption" x="{x:.2f}" y="{middle + 4:.1f}" font-size="13" '
            f'{SERIF_ATTRS} text-anchor="{anchor}" fill="{COLOR_FOREGROUND}" '
            f'fill-opacity="{TEXT_SECONDARY_OPACITY}">{block.year}</text>'
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
    tenures: list[Tenure],
    geometry: dict[int, list[tuple[str, float, ...]]],
    band_tops: dict[str, float],
) -> str:
    """Every strand with its exit cap; the highlighted lineage is drawn last, on top."""
    ordered = [t for t in tenures if not t.highlighted] + [t for t in tenures if t.highlighted]
    parts = []
    for tenure in ordered:
        pieces = geometry[id(tenure)]
        highlighted = ' data-highlighted="true"' if tenure.highlighted else ""
        parts.append(
            f'<g class="strand" data-asset-id={quoteattr(tenure.asset_id)} '
            f'data-asset-type={quoteattr(tenure.asset_type)}{highlighted}>'
            f"<title>{escape(_strand_title(tenure))}</title>"
        )
        bounds = tenure.bounds
        for index, segment in enumerate(tenure.segments):
            d = _clip(pieces, bounds[index], bounds[index + 1])
            if not d:
                continue
            stroke, opacity = _segment_shade(tenure, segment)
            parts.append(
                f'<path class="segment" data-asset-id={quoteattr(tenure.asset_id)} '
                f'data-holder={quoteattr(segment["holder"])} '
                f'data-from-node={quoteattr(segment["from_node"] or "")} '
                f'data-to-node={quoteattr(segment["to_node"] or "")} '
                f'data-contract-type={quoteattr(segment["contract_type"] or "")} '
                f'd="{d}" fill="none" stroke="{stroke}" stroke-opacity="{opacity:g}" '
                f'stroke-width="{STRAND_WIDTH}" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        if tenure.exit_holder and not tenure.continues_as:
            parts.append(_render_exit_cap(tenure, band_tops))
        parts.append("</g>")
    return "".join(parts)


def _strand_title(tenure: Tenure) -> str:
    destination = f" → {tenure.exit_holder}" if tenure.exit_holder else ""
    return f"{tenure.label}: MEM{destination}"


def _render_exit_cap(tenure: Tenure, band_tops: dict[str, float]) -> str:
    """A filled dot in the strand's own shade where an asset left Memphis (no destination
    text on the page; it is in the tooltip). A marker drawn later covers it at a waiver."""
    x, y = tenure.end_x, tenure.last_y(band_tops)
    fill, opacity = _segment_shade(tenure, tenure.segments[-1])
    return (
        f'<g class="exit" data-asset-id={quoteattr(tenure.asset_id)} '
        f'data-destination={quoteattr(tenure.exit_holder or "")}>'
        f'<title>{escape(f"Left MEM → {tenure.exit_holder}")}</title>'
        f'<circle class="exit-marker" cx="{x:.2f}" cy="{y:.1f}" r="{END_CAP_RADIUS}" '
        f'fill="{fill}" fill-opacity="{opacity:g}"/>'
        "</g>"
    )


def _render_overlay(
    tenures: list[Tenure],
    anchors: dict[int, tuple[float, float, float]],
    numbered: dict[int, tuple[int, dt.date, dt.date, str]],
) -> str:
    """Asset labels, drawn last so hub markers never hide a name."""
    parts = []
    for tenure in tenures:
        label_x, label_y, _ = anchors[id(tenure)]
        number = numbered.get(id(tenure))
        if number is not None:
            parts.append(_render_numbered_marker(tenure, number[0], label_x, label_y))
        else:
            parts.append(_render_label(tenure, label_x, label_y))
    return "".join(parts)


# A navy knockout under each name: the strand it sits on breaks around the text, so pale
# text never sits on a pale strand.
_HALO = (
    f'stroke="{COLOR_BACKGROUND}" stroke-width="5" stroke-linejoin="round" paint-order="stroke"'
)


def _render_label(tenure: Tenure, x: float, y: float) -> str:
    return (
        f'<text class="asset-label" x="{x + 3:.2f}" y="{y + 3.2:.1f}" '
        f'font-size="{LABEL_FONT}" fill="{COLOR_FOREGROUND}" {_HALO}>'
        f"{escape(tenure.display_label)}</text>"
    )


def _render_numbered_marker(tenure: Tenure, number: int, x: float, y: float) -> str:
    """A plain numeral at a strand's left edge, standing in for a name that won't fit."""
    return (
        f'<g class="short-tenure-marker" data-asset-id={quoteattr(tenure.asset_id)} '
        f'data-number="{number}">'
        f"<title>{escape(tenure.label)}</title>"
        f'<text x="{x + 2:.2f}" y="{y + 3.2:.1f}" font-size="{LABEL_FONT}" '
        f'fill="{COLOR_FOREGROUND}" {_HALO}>{number}</text>'
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
        if node["kind"] in FLAT_NODE_KINDS or node.get("hidden", False):
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
            # A contract change curves away from the node, so its marker sits where it starts.
            + [tenure.y_at(x - 0.01, band_tops) for tenure in internal]
        )
        hub_y = sum(ys) / len(ys)
        parts.append(
            f'<g class="hub" data-node-id={quoteattr(node_id)} data-kind={quoteattr(node["kind"])} '
            f'data-out="{len(outs)}" data-in="{len(ins)}">'
            f'<title>{escape(node["description"])}</title>'
        )
        if node["kind"] == "trade":
            connectors = []
            for tenure in sorted(outs, key=lambda t: (t.last_y(band_tops), t.order)):
                connectors.append(
                    _connector(
                        "out", tenure, x - tenure.lag, tenure.last_y(band_tops), x, hub_y, tenure.lag
                    )
                )
            for tenure in sorted(ins, key=lambda t: (_entry_y(t, band_tops), t.order)):
                connectors.append(
                    _connector(
                        "in", tenure, x, hub_y, x + tenure.lead, _entry_y(tenure, band_tops),
                        tenure.lead,
                    )
                )
            # Gold connectors last, so the lineage's own path is never crossed out.
            parts += [c for c, hot in connectors if not hot] + [c for c, hot in connectors if hot]
        fill, stroke = _hub_marker_paint(node["kind"])
        # A ring's stroke is the marker itself; a dot's is a thin navy gap around it.
        ring = 2.2 if stroke == COLOR_ACCENT else 1.5
        parts.append(
            f'<circle class="hub-marker" cx="{x:.2f}" cy="{hub_y:.1f}" r="{HUB_RADIUS}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{ring}"/>'
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
) -> tuple[str, bool]:
    """(path, highlighted): the artwork's flow curve from a strand's end into its trade hub."""
    mid = (x1 + x2) / 2 if reach else x1
    if tenure.highlighted:
        stroke, opacity = HIGHLIGHT_SHADE
    else:
        stroke, opacity = COLOR_FOREGROUND, CONNECTOR_OPACITY
    path = (
        f'<path class={quoteattr(kind)} data-asset-id={quoteattr(tenure.asset_id)} '
        f'd="M{x1:.2f},{y1:.1f} C{mid:.2f},{y1:.1f} {mid:.2f},{y2:.1f} '
        f'{x2:.2f},{y2:.1f}" fill="none" stroke="{stroke}" stroke-width="1.6" '
        f'stroke-opacity="{opacity:g}" stroke-linecap="round"/>'
    )
    return path, tenure.highlighted


def _render_node_labels(nodes: list[dict[str, Any]], node_x: dict[str, float]) -> str:
    """'Feb 3 Trade' captions above the month axis, each on the lowest of NODE_LABEL_LEVELS
    lines where it clears its neighbours, with a hairline down to the axis."""
    labelled = [
        node
        for node in nodes
        if node["kind"] in NODE_CAPTIONS and not node.get("hidden", False)
    ]
    if not labelled:
        return ""
    axis_y = TOP_MARGIN - 18
    font = 11
    parts = [
        (
            f'<g class="node-labels" font-size="{font}" fill="{COLOR_FOREGROUND}" '
            f'fill-opacity="{TEXT_SECONDARY_OPACITY}">'
        )
    ]
    right_edge = [-math.inf] * NODE_LABEL_LEVELS
    drawn: list[tuple[float, str]] = []
    for node in sorted(labelled, key=lambda n: (node_x[n["id"]], n["id"])):
        x = node_x[node["id"]]
        date = _parse_date(node["date"])
        caption = f'{date.strftime("%b")} {date.day} {NODE_CAPTIONS[node["kind"]]}'
        # Two drafts on the same day would print the same caption twice on the same tick.
        if (x, caption) in drawn:
            continue
        drawn.append((x, caption))
        half = len(caption) * font * 0.52 / 2
        free = [level for level in range(NODE_LABEL_LEVELS) if right_edge[level] <= x - half]
        level = free[0] if free else min(range(NODE_LABEL_LEVELS), key=lambda i: right_edge[i])
        right_edge[level] = x + half + NODE_LABEL_PAD
        y = NODE_LABEL_Y + (NODE_LABEL_LEVELS - 1 - level) * NODE_LABEL_STAGGER
        parts.append(
            f'<line x1="{x:.2f}" y1="{y + 4}" x2="{x:.2f}" y2="{axis_y:.1f}" '
            f'stroke="{COLOR_HAIRLINE}" stroke-width="1"/>'
            f'<text class="node-label" x="{x:.2f}" y="{y}" text-anchor="middle">'
            f"{escape(caption)}</text>"
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


def _legend_swatch_row(y: float, entries: list[tuple[str, str, float, str]]) -> str:
    """One row of `(shape, color, opacity, caption)` swatches; `shape` is "line" (a strand
    shade), "dot" or "ring" (a hub marker) or "end" (a strand ending in its exit dot)."""
    parts = []
    x = float(PLOT_X0)
    for shape, color, opacity, caption in entries:
        cy = y - 4
        if shape in ("line", "end"):
            parts.append(
                f'<line x1="{x + 4:.1f}" y1="{cy:.1f}" x2="{x + 26:.1f}" y2="{cy:.1f}" '
                f'stroke="{color}" stroke-opacity="{opacity:g}" stroke-width="{STRAND_WIDTH}" '
                f'stroke-linecap="round"/>'
            )
            if shape == "end":
                parts.append(
                    f'<circle cx="{x + 26:.1f}" cy="{cy:.1f}" r="{END_CAP_RADIUS}" '
                    f'fill="{color}" fill-opacity="{opacity:g}"/>'
                )
            text_x = x + 38
        elif shape == "ring":
            parts.append(
                f'<circle cx="{x + 6:.1f}" cy="{cy:.1f}" r="{HUB_RADIUS}" '
                f'fill="{COLOR_BACKGROUND}" stroke="{color}" stroke-width="2.2"/>'
            )
            text_x = x + 18
        else:
            parts.append(
                f'<circle cx="{x + 6:.1f}" cy="{cy:.1f}" r="{HUB_RADIUS}" fill="{color}"/>'
            )
            text_x = x + 18
        parts.append(f'<text x="{text_x:.1f}" y="{y:.1f}">{escape(caption)}</text>')
        x = text_x + 6.6 * len(caption) + 30
    return "".join(parts)


def _render_legend(
    height: int,
    legend_height: float,
    numbered: dict[int, tuple[int, dt.date, dt.date, str]],
    highlight_label: str | None,
) -> str:
    top = height - legend_height
    parts = [f'<g class="legend" font-size="12" fill="{COLOR_FOREGROUND}">']

    row1_y = top + LEGEND_TOP_PAD
    shades = [
        ("line", *CONTRACT_SHADES["standard"], "Standard"),
        ("line", *CONTRACT_SHADES["two_way"], "Two-Way"),
        ("line", *CONTRACT_SHADES["ten_day"], "10-Day"),
        ("line", *CONTRACT_SHADES["draft_rights"], "Draft Rights"),
        ("line", *PICK_SHADE, "Pick"),
    ]
    if highlight_label is not None:
        shades.append(("line", *HIGHLIGHT_SHADE, f"{highlight_label} Trade Tree"))
    parts.append(_legend_swatch_row(row1_y, shades))

    row2_y = row1_y + LEGEND_ROW_GAP
    parts.append(
        _legend_swatch_row(
            row2_y,
            [
                ("dot", COLOR_ACCENT, 1.0, "Trade"),
                ("dot", COLOR_FOREGROUND, 1.0, "Signing or Conversion"),
                ("dot", COLOR_BAD, 1.0, "Waiver, Void or Expiry"),
                ("ring", COLOR_ACCENT, 1.0, "Draft Selection"),
                ("end", COLOR_FOREGROUND, 1.0, "Left Memphis"),
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
    parts = [
        (
            f'<g class="short-tenure-legend" font-size="11" fill="{COLOR_FOREGROUND}" '
            f'fill-opacity="{TEXT_SECONDARY_OPACITY}">'
        )
    ]
    for index, (number, start_date, end_date, label) in enumerate(entries):
        col, row = index % cols, index // cols
        x = PLOT_X0 + col * NUMBERED_COL_WIDTH
        y = top_y + row * NUMBERED_ROW_HEIGHT
        text = f"{number}. {label} ({start_date.strftime('%b %d')} → {end_date.strftime('%b %d')})"
        parts.append(f'<text x="{x:.1f}" y="{y:.1f}">{escape(text)}</text>')
    parts.append("</g>")
    return "".join(parts)


def run_render(
    in_path: pathlib.Path, out_path: pathlib.Path, highlight: str | None = DEFAULT_HIGHLIGHT
) -> str:
    """Read graph.json from `in_path`, render its SVG, write it to `out_path`."""
    export = json.loads(in_path.read_text())
    svg = render_svg(export, highlight)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg)
    print(f"wrote {out_path}")
    return svg
