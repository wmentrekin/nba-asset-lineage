export type AssetKind = "player_tenure" | "pick_continuity";

export interface TimelineContractNode {
  node_id: string;
  event_id: string | null;
  event_date: string;
  event_order: number;
  node_type: string;
  label: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface TimelineContractEdge {
  edge_id: string;
  asset_id: string;
  source_node_id: string;
  target_node_id: string;
  start_date: string;
  end_date: string;
  edge_type: string;
  lane_group: string;
  lane_index: number;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface TimelineContractLane {
  asset_lane_id: string;
  asset_id: string;
  lane_group: string;
  lane_index: number;
  effective_start_date: string;
  effective_end_date: string;
  assignment_method: string;
  created_at: string;
}

export interface TimelineChapter {
  story_chapter_id: string;
  slug: string;
  chapter_order: number;
  title: string;
  body: string;
  start_date: string;
  end_date: string;
  focus_payload: {
    date_range?: {
      start_date?: string;
      end_date?: string;
    };
    event_ids?: string[];
    asset_ids?: string[];
    lane_groups?: string[];
    default_zoom?: number;
    highlight_mode?: string;
  };
  era_id: string | null;
}

export interface TimelineContract {
  nodes: TimelineContractNode[];
  edges: TimelineContractEdge[];
  lanes: TimelineContractLane[];
  meta: Record<string, unknown>;
  editorial?: {
    annotations?: Array<Record<string, unknown>>;
    calendar_markers?: Array<Record<string, unknown>>;
    game_overlays?: Array<Record<string, unknown>>;
    eras?: Array<Record<string, unknown>>;
    story_chapters?: TimelineChapter[];
    meta?: Record<string, unknown>;
  };
}

export interface TimelineUiState {
  windowStart: string;
  windowEnd: string;
  zoom: number;
  assetKinds: AssetKind[];
  selectedChapterId: string | null;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
}

export interface TimelineFocus {
  windowStart: string;
  windowEnd: string;
  zoom: number;
  assetKinds: AssetKind[];
  eventIds: string[];
  assetIds: string[];
  laneGroups: string[];
  highlightMode: string;
}

export interface TimelineNodeLayout extends TimelineContractNode {
  x: number;
  y: number;
  visible: boolean;
  focused: boolean;
  connectedEdgeIds: string[];
}

export interface TimelineEdgeLayout extends TimelineContractEdge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  d: string;
  visible: boolean;
  focused: boolean;
}

export interface TimelineLaneLayout extends TimelineContractLane {
  y: number;
  label: string;
}

export interface TimelineTickLayout {
  x: number;
  date: string;
  label: string;
  major: boolean;
}

export interface TimelineMarkerLayout {
  id: string;
  x: number;
  label: string;
  date: string;
  visible: boolean;
  payload: Record<string, unknown>;
}

export interface TimelineLayout {
  width: number;
  height: number;
  dayWidth: number;
  laneRows: TimelineLaneLayout[];
  axisTicks: TimelineTickLayout[];
  markers: TimelineMarkerLayout[];
  nodes: TimelineNodeLayout[];
  edges: TimelineEdgeLayout[];
}

const DAY_IN_MS = 24 * 60 * 60 * 1000;
const LANE_GROUP_ORDER = ["main_roster", "two_way", "future_picks"];
const ASSET_KIND_ORDER: AssetKind[] = ["player_tenure", "pick_continuity"];

function toUtcDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function toIsoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function addDays(value: string, days: number): string {
  return toIsoDate(new Date(toUtcDate(value).getTime() + days * DAY_IN_MS));
}

export function compareIsoDates(left: string, right: string): number {
  return toUtcDate(left).getTime() - toUtcDate(right).getTime();
}

export function clampIsoDate(value: string, min: string, max: string): string {
  if (compareIsoDates(value, min) < 0) {
    return min;
  }
  if (compareIsoDates(value, max) > 0) {
    return max;
  }
  return value;
}

export function daysBetween(start: string, end: string): number {
  return Math.max(0, Math.round((toUtcDate(end).getTime() - toUtcDate(start).getTime()) / DAY_IN_MS));
}

export function getContractBounds(contract: TimelineContract): { start: string; end: string } {
  const dates = [
    ...contract.nodes.map((row) => row.event_date),
    ...contract.edges.flatMap((row) => [row.start_date, row.end_date]),
    ...contract.lanes.flatMap((row) => [row.effective_start_date, row.effective_end_date]),
  ].filter(Boolean);

  const sorted = dates.sort(compareIsoDates);
  if (sorted.length === 0) {
    const today = new Date().toISOString().slice(0, 10);
    return { start: today, end: today };
  }
  return { start: sorted[0], end: sorted[sorted.length - 1] };
}

export function normalizeAssetKinds(value: string[] | undefined): AssetKind[] {
  const selected = new Set<AssetKind>();
  for (const item of value ?? []) {
    if (ASSET_KIND_ORDER.includes(item as AssetKind)) {
      selected.add(item as AssetKind);
    }
  }
  return ASSET_KIND_ORDER.filter((item) => selected.has(item));
}

export function getDefaultUiState(contract: TimelineContract, chapter?: TimelineChapter | null): TimelineUiState {
  const bounds = getContractBounds(contract);
  const focus = chapter ? chapterFocus(chapter, bounds) : null;
  return {
    windowStart: focus?.windowStart ?? bounds.start,
    windowEnd: focus?.windowEnd ?? bounds.end,
    zoom: focus?.zoom ?? 1,
    assetKinds: focus?.assetKinds ?? [...ASSET_KIND_ORDER],
    selectedChapterId: chapter?.story_chapter_id ?? null,
    selectedNodeId: null,
    selectedEdgeId: null,
  };
}

export function chapterFocus(chapter: TimelineChapter, fallbackBounds: { start: string; end: string }): TimelineFocus {
  const focusPayload = chapter.focus_payload ?? {};
  const dateRange = focusPayload.date_range ?? {};
  const windowStart = dateRange.start_date ?? chapter.start_date ?? fallbackBounds.start;
  const windowEnd = dateRange.end_date ?? chapter.end_date ?? fallbackBounds.end;
  return {
    windowStart,
    windowEnd,
    zoom: focusPayload.default_zoom ?? 1,
    assetKinds: [...ASSET_KIND_ORDER],
    eventIds: [...(focusPayload.event_ids ?? [])],
    assetIds: [...(focusPayload.asset_ids ?? [])],
    laneGroups: [...(focusPayload.lane_groups ?? [])],
    highlightMode: focusPayload.highlight_mode ?? "focus",
  };
}

function isDateVisible(date: string, windowStart: string, windowEnd: string): boolean {
  return compareIsoDates(date, windowStart) >= 0 && compareIsoDates(date, windowEnd) <= 0;
}

function dateRangesOverlap(leftStart: string, leftEnd: string, rightStart: string, rightEnd: string): boolean {
  return compareIsoDates(leftStart, rightEnd) <= 0 && compareIsoDates(rightStart, leftEnd) <= 0;
}

function assetKindForEdge(edge: TimelineContractEdge): AssetKind | null {
  const kind = edge.payload.asset_kind;
  return kind === "player_tenure" || kind === "pick_continuity" ? kind : null;
}

function laneRowsForContract(contract: TimelineContract): TimelineLaneLayout[] {
  const grouped = new Map<string, TimelineContractLane[]>();
  for (const lane of contract.lanes) {
    const rows = grouped.get(lane.lane_group) ?? [];
    rows.push(lane);
    grouped.set(lane.lane_group, rows);
  }

  const orderedGroups = [
    ...LANE_GROUP_ORDER.filter((group) => grouped.has(group)),
    ...Array.from(grouped.keys()).filter((group) => !LANE_GROUP_ORDER.includes(group)).sort(),
  ];

  const rows: TimelineLaneLayout[] = [];
  let cursorY = 120;
  for (const group of orderedGroups) {
    const lanes = grouped.get(group)?.slice().sort((left, right) => left.lane_index - right.lane_index) ?? [];
    for (const lane of lanes) {
      rows.push({
        ...lane,
        y: cursorY,
        label: `${group.replaceAll("_", " ")} ${lane.lane_index + 1}`,
      });
      cursorY += 64;
    }
    cursorY += 40;
  }
  return rows;
}

function axisTicksForBounds(start: string, end: string, dayWidth: number, leftPad: number): TimelineTickLayout[] {
  const totalDays = Math.max(1, daysBetween(start, end));
  const ticks: TimelineTickLayout[] = [];
  for (let dayOffset = 0; dayOffset <= totalDays; dayOffset += 7) {
    const date = addDays(start, dayOffset);
    const x = leftPad + dayOffset * dayWidth;
    ticks.push({
      x,
      date,
      label: date,
      major: dayOffset % 28 === 0,
    });
  }
  if (ticks[ticks.length - 1]?.date !== end) {
    const x = leftPad + totalDays * dayWidth;
    ticks.push({ x, date: end, label: end, major: true });
  }
  return ticks;
}

function pointForDate(date: string, start: string, dayWidth: number, leftPad: number): number {
  return leftPad + daysBetween(start, date) * dayWidth;
}

function edgePath(x1: number, y1: number, x2: number, y2: number): string {
  const midX = x1 + (x2 - x1) / 2;
  return `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${midX.toFixed(1)} ${y1.toFixed(1)}, ${midX.toFixed(1)} ${y2.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`;
}

function nodeLabel(node: TimelineContractNode): string {
  return node.label || node.event_id || node.node_id;
}

function buildEdgeFocusState(edge: TimelineContractEdge, focus: TimelineFocus | null): boolean {
  if (!focus) {
    return false;
  }
  const assetMatch = focus.assetIds.includes(edge.asset_id);
  const laneMatch = focus.laneGroups.includes(edge.lane_group);
  return assetMatch || laneMatch;
}

function buildNodeFocusState(node: TimelineContractNode, focus: TimelineFocus | null, connectedEdges: TimelineEdgeLayout[]): boolean {
  if (!focus) {
    return false;
  }
  const eventMatch = node.event_id ? focus.eventIds.includes(node.event_id) : false;
  const assetMatch = connectedEdges.some((edge) => focus.assetIds.includes(edge.asset_id));
  const laneMatch = connectedEdges.some((edge) => focus.laneGroups.includes(edge.lane_group));
  return eventMatch || assetMatch || laneMatch;
}

export function buildTimelineLayout(contract: TimelineContract, state: TimelineUiState): TimelineLayout {
  const bounds = getContractBounds(contract);
  const selectedChapter = contract.editorial?.story_chapters?.find((chapter) => chapter.story_chapter_id === state.selectedChapterId) ?? null;
  const focus = selectedChapter ? chapterFocus(selectedChapter, bounds) : null;
  const dayWidth = 18;
  const leftPad = 160;
  const rightPad = 120;
  const laneRows = laneRowsForContract(contract);
  const windowStart = clampIsoDate(state.windowStart, bounds.start, bounds.end);
  const windowEnd = clampIsoDate(state.windowEnd, windowStart, bounds.end);
  const width = leftPad + daysBetween(bounds.start, bounds.end) * dayWidth + rightPad;

  const visibleEdges = contract.edges
    .filter((edge) => dateRangesOverlap(edge.start_date, edge.end_date, windowStart, windowEnd))
    .filter((edge) => {
      const kind = assetKindForEdge(edge);
      return kind ? state.assetKinds.includes(kind) : true;
    });

  const edgeById = new Map<string, TimelineEdgeLayout>();
  const edgeLayouts = visibleEdges.map((edge) => {
    const laneRow = laneRows.find((row) => row.lane_group === edge.lane_group && row.lane_index === edge.lane_index);
    const y = laneRow ? laneRow.y : 120;
    const clippedStart = clampIsoDate(edge.start_date, windowStart, windowEnd);
    const clippedEnd = clampIsoDate(edge.end_date, windowStart, windowEnd);
    const x1 = pointForDate(clippedStart, bounds.start, dayWidth, leftPad);
    const x2 = pointForDate(clippedEnd, bounds.start, dayWidth, leftPad);
    const layout: TimelineEdgeLayout = {
      ...edge,
      x1,
      y1: y,
      x2,
      y2: y,
      d: edgePath(x1, y, x2, y),
      visible: true,
      focused: buildEdgeFocusState(edge, focus),
    };
    edgeById.set(edge.edge_id, layout);
    return layout;
  });

  const edgesByNode = new Map<string, string[]>();
  for (const edge of edgeLayouts) {
    const source = edgesByNode.get(edge.source_node_id) ?? [];
    source.push(edge.edge_id);
    edgesByNode.set(edge.source_node_id, source);
    const target = edgesByNode.get(edge.target_node_id) ?? [];
    target.push(edge.edge_id);
    edgesByNode.set(edge.target_node_id, target);
  }

  const nodeLayouts = contract.nodes.map((node) => {
    const x = pointForDate(node.event_date, bounds.start, dayWidth, leftPad);
    const connectedEdges = (edgesByNode.get(node.node_id) ?? [])
      .map((edgeId) => edgeById.get(edgeId))
      .filter((value): value is TimelineEdgeLayout => Boolean(value));
    const centeredY = connectedEdges.length > 0
      ? connectedEdges.reduce((sum, edge) => sum + edge.y1, 0) / connectedEdges.length
      : laneRows[0]?.y ?? 120;
    const y = centeredY + (node.event_order - 1) * 16;
    return {
      ...node,
      x,
      y,
      visible: isDateVisible(node.event_date, windowStart, windowEnd),
      focused: buildNodeFocusState(node, focus, connectedEdges),
      connectedEdgeIds: connectedEdges.map((edge) => edge.edge_id),
    };
  });

  const markers = (contract.editorial?.calendar_markers ?? []).map((marker) => ({
    id: String(marker.calendar_marker_id ?? marker.label),
    x: pointForDate(String(marker.marker_date), bounds.start, dayWidth, leftPad),
    label: String(marker.label ?? marker.marker_type),
    date: String(marker.marker_date),
    visible: isDateVisible(String(marker.marker_date), windowStart, windowEnd),
    payload: marker.payload as Record<string, unknown>,
  }));

  return {
    width,
    height: Math.max(860, (laneRows[laneRows.length - 1]?.y ?? 120) + 180),
    dayWidth,
    laneRows,
    axisTicks: axisTicksForBounds(bounds.start, bounds.end, dayWidth, leftPad),
    markers,
    nodes: nodeLayouts,
    edges: edgeLayouts,
  };
}

export function nodeIdForEventId(contract: TimelineContract, eventId: string): string | null {
  return contract.nodes.find((node) => node.event_id === eventId)?.node_id ?? null;
}

function serializeValue(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function cssClass(parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function renderTimelineScene(layout: TimelineLayout): string {
  const laneLines = layout.laneRows
    .map(
      (lane) => `
        <line x1="0" y1="${lane.y}" x2="${layout.width}" y2="${lane.y}" class="timeline-grid__lane"></line>
        <text x="20" y="${lane.y - 16}" class="timeline-lane-label">${lane.label}</text>
      `,
    )
    .join("");

  const axis = layout.axisTicks
    .map(
      (tick) => `
        <line x1="${tick.x}" y1="60" x2="${tick.x}" y2="${layout.height - 72}" class="${cssClass(["timeline-axis__tick", tick.major && "timeline-axis__tick--major"])}"></line>
        <text x="${tick.x}" y="42" class="${cssClass(["timeline-axis__label", tick.major && "timeline-axis__label--major"])}">${tick.label}</text>
      `,
    )
    .join("");

  const markers = layout.markers
    .map(
      (marker) => `
        <g class="${cssClass(["timeline-marker", !marker.visible && "is-hidden"])}" data-marker-id="${marker.id}" data-inspectable="true" data-kind="marker">
          <line x1="${marker.x}" y1="56" x2="${marker.x}" y2="${layout.height - 72}" class="timeline-marker__line"></line>
          <rect x="${marker.x + 8}" y="68" rx="8" ry="8" width="180" height="28" class="timeline-marker__badge"></rect>
          <text x="${marker.x + 18}" y="87" class="timeline-marker__text">${marker.label}</text>
        </g>
      `,
    )
    .join("");

  const edges = layout.edges
    .map(
      (edge) => `
        <path
          d="${edge.d}"
          class="${cssClass([
            "timeline-edge",
            `timeline-edge--${edge.edge_type}`,
            edge.focused && "is-focused",
            !edge.visible && "is-hidden",
          ])}"
          data-edge-id="${edge.edge_id}"
          data-asset-id="${edge.asset_id}"
          data-asset-kind="${String(edge.payload.asset_kind ?? "")}"
          data-kind="edge"
          data-inspectable="true"
          tabindex="0"
        ></path>
        <circle
          cx="${edge.x1}"
          cy="${edge.y1}"
          r="5"
          class="${cssClass(["timeline-edge__anchor", edge.focused && "is-focused", !edge.visible && "is-hidden"])}"
        ></circle>
        <circle
          cx="${edge.x2}"
          cy="${edge.y2}"
          r="5"
          class="${cssClass(["timeline-edge__anchor", edge.focused && "is-focused", !edge.visible && "is-hidden"])}"
        ></circle>
      `,
    )
    .join("");

  const nodes = layout.nodes
    .map(
      (node) => `
        <g
          class="${cssClass(["timeline-node", node.focused && "is-focused", !node.visible && "is-hidden"])}"
          data-node-id="${node.node_id}"
          data-inspectable="true"
          data-kind="node"
          tabindex="0"
          transform="translate(${node.x} ${node.y})"
        >
          <circle r="${node.event_order > 1 ? 11 : 13}" class="timeline-node__dot"></circle>
          <circle r="${node.event_order > 1 ? 15 : 17}" class="timeline-node__ring"></circle>
          <text y="-24" class="timeline-node__label">${nodeLabel(node)}</text>
          <text y="26" class="timeline-node__meta">${node.event_date} · ${String(node.event_order).padStart(2, "0")}</text>
        </g>
      `,
    )
    .join("");

  return `
    <g class="timeline-grid">
      ${laneLines}
    </g>
    <g class="timeline-axis">
      ${axis}
    </g>
    <g class="timeline-markers">
      ${markers}
    </g>
    <g class="timeline-edges">
      ${edges}
    </g>
    <g class="timeline-nodes">
      ${nodes}
    </g>
  `;
}

export function describeTimelineRow(value: TimelineNodeLayout | TimelineEdgeLayout | TimelineMarkerLayout | undefined): string {
  if (!value) {
    return "Nothing selected";
  }
  if ("node_id" in value) {
    return `${value.label} on ${value.event_date}`;
  }
  if ("edge_id" in value) {
    return `${value.edge_type} for ${value.asset_id} from ${value.start_date} to ${value.end_date}`;
  }
  return `${value.label} on ${value.date}`;
}

export function serializeTimelineSelection(value: unknown): string {
  return serializeValue(value);
}
