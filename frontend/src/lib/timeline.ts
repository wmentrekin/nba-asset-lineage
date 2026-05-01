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
  focus_payload?: {
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
  era_id?: string | null;
}

export interface TimelineChapterExport {
  story_chapter_id: string;
  slug: string;
  chapter_order: number;
  title: string;
  body: string;
  start_date: string;
  end_date: string;
}

export interface TimelineChapterLayout {
  story_chapter_id: string;
  window_start: string;
  window_end: string;
  highlight_asset_ids: string[];
  highlight_event_ids: string[];
  minimap_anchor_id: string;
  default_zoom: number | null;
}

export interface TimelineLayoutAxisStrategy {
  minor_tick_unit: "month";
  major_tick_unit: "season_boundary";
  season_boundary_rule: "july_1";
}

export interface TimelineLayoutMinimapSegment {
  segment_id: string;
  start_date: string;
  end_date: string;
  anchor_date: string;
  label: string;
}

export interface TimelineLayoutMeta {
  start_date: string;
  end_date: string;
  default_window_start: string;
  default_window_end: string;
  default_day_width: number;
  axis_strategy: TimelineLayoutAxisStrategy;
  minimap_segments: TimelineLayoutMinimapSegment[];
}

export interface TimelineLayoutLaneSegment {
  segment_id: string;
  asset_id: string;
  lane_group: string;
  date_start: string;
  date_end: string;
  display_rank: number;
  band_slot: number;
  compaction_group: string | null;
  continuity_anchor: string;
  entry_slot: number;
  exit_slot: number;
  identity_marker: {
    image_path: string | null;
    label_text: string;
    marker_variant: "headshot_text" | "text_only";
  };
}

export interface TimelineLayoutLabel {
  segment_id: string;
  asset_id: string;
  date_start: string;
  date_end: string;
  inline_label_allowed: boolean;
  label_priority: number;
  fallback_marker_required: boolean;
  marker_side: "left";
}

export interface TimelineLayoutTransitionAnchor {
  segment_id: string;
  asset_id: string;
  anchor_date: string;
  from_slot: number;
  to_slot: number;
}

export interface TimelineLayoutTransitionLink {
  transition_link_id: string;
  source_segment_id: string;
  target_segment_id: string;
  source_asset_id: string;
  target_asset_id: string;
  link_type: "same_asset" | "pick_to_player" | "event_transition";
}

export interface TimelineLayoutEvent {
  event_id: string;
  cluster_id: string;
  cluster_date: string;
  cluster_order: number;
  junction_type: "transaction" | "draft_transition" | "state_boundary";
  member_event_ids: string[];
  connected_asset_ids: string[];
  incoming_slots: Record<string, number>;
  outgoing_slots: Record<string, number>;
  transition_anchors: TimelineLayoutTransitionAnchor[];
  transition_links: TimelineLayoutTransitionLink[];
}

export interface TimelineGeneratedLayoutContract {
  layout_meta: TimelineLayoutMeta;
  lane_layout: TimelineLayoutLaneSegment[];
  label_layout: TimelineLayoutLabel[];
  event_layout: TimelineLayoutEvent[];
  chapter_layout: TimelineChapterLayout[];
}

export interface TimelinePresentationContract {
  nodes: TimelineContractNode[];
  edges: TimelineContractEdge[];
  lanes: TimelineContractLane[];
  meta: Record<string, unknown>;
}

export interface TimelineContract {
  nodes: TimelineContractNode[];
  edges: TimelineContractEdge[];
  lanes: TimelineContractLane[];
  meta: Record<string, unknown>;
  layout?: TimelineGeneratedLayoutContract;
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

export interface TimelineViewportMetrics {
  boundsStart: string;
  boundsEnd: string;
  defaultWindowStart: string;
  defaultWindowEnd: string;
  defaultWindowDays: number;
  minWindowDays: number;
  maxWindowDays: number;
  minZoom: number;
  maxZoom: number;
  zoom: number;
  windowStart: string;
  windowEnd: string;
  windowDays: number;
  viewportWidth: number;
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
  strokeWidth: number;
  continuityAnchor: string | null;
  visible: boolean;
  focused: boolean;
}

export interface TimelineLaneLayout {
  lane_id: string;
  lane_group: string;
  lane_index: number;
  y: number;
  label: string;
}

export interface TimelineTickLayout {
  x: number;
  date: string;
  label: string;
  major: boolean;
  kind: "month" | "season_boundary";
}

export interface TimelineMarkerLayout {
  id: string;
  x: number;
  label: string;
  date: string;
  visible: boolean;
  payload: Record<string, unknown>;
}

export interface TimelineInlineLabelLayout {
  segment_id: string;
  asset_id: string;
  lane_group: string;
  label: string;
  priority: number;
  x: number;
  y: number;
  width: number;
  height: number;
  visible: boolean;
}

export interface TimelineIdentityMarkerLayout {
  segment_id: string;
  asset_id: string;
  lane_group: string;
  label: string;
  priority: number;
  x: number;
  y: number;
  width: number;
  height: number;
  markerSide: "left";
  markerVariant: "headshot_text" | "text_only";
  imagePath: string | null;
  usesHeadshot: boolean;
  visible: boolean;
}

export interface TimelineBandLayout {
  band_id: string;
  lane_group: string;
  label: string;
  visible: boolean;
  startY: number;
  endY: number;
  rows: TimelineLaneLayout[];
}

export interface TimelineMinimapSegmentLayout extends TimelineLayoutMinimapSegment {
  x1: number;
  x2: number;
  anchorX: number;
  active: boolean;
  linkedChapterIds: string[];
}

export interface TimelineSceneChapterFocus {
  story_chapter_id: string;
  slug: string;
  chapter_order: number;
  title: string;
  body: string;
  windowStart: string;
  windowEnd: string;
  defaultZoom: number | null;
  highlightAssetIds: string[];
  highlightEventIds: string[];
  minimapAnchorId: string | null;
  anchorX: number | null;
  windowX1: number;
  windowX2: number;
  active: boolean;
}

export interface TimelineChronologyLayout {
  startDate: string;
  endDate: string;
  windowStart: string;
  windowEnd: string;
  dayWidth: number;
  axisStrategy: TimelineLayoutAxisStrategy | null;
  ticks: TimelineTickLayout[];
  minimapSegments: TimelineMinimapSegmentLayout[];
}

export interface TimelineScenePrimitives {
  leftPad: number;
  rightPad: number;
  bands: TimelineBandLayout[];
  chronology: TimelineChronologyLayout;
  chapters: TimelineSceneChapterFocus[];
  activeFocus: TimelineSceneChapterFocus | null;
}

export interface TimelineJunctionStemLayout {
  stem_id: string;
  segment_id: string;
  lane_group: string;
  direction: "incoming" | "outgoing";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  d: string;
}

export interface TimelineJunctionTransitionLayout {
  transition_link_id: string;
  cluster_id: string;
  lane_group: string;
  link_type: "same_asset" | "pick_to_player" | "event_transition";
  source_segment_id: string;
  target_segment_id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  d: string;
  visible: boolean;
}

export interface TimelineJunctionLayout {
  junction_id: string;
  event_id: string;
  cluster_id: string;
  cluster_date: string;
  cluster_order: number;
  junction_type: "transaction" | "draft_transition" | "state_boundary";
  x: number;
  y: number;
  spineY1: number;
  spineY2: number;
  visible: boolean;
  memberEventIds: string[];
  connectedAssetIds: string[];
  stems: TimelineJunctionStemLayout[];
  transitions: TimelineJunctionTransitionLayout[];
}

export interface TimelineLayout {
  width: number;
  height: number;
  dayWidth: number;
  scene: TimelineScenePrimitives;
  laneRows: TimelineLaneLayout[];
  axisTicks: TimelineTickLayout[];
  markers: TimelineMarkerLayout[];
  inlineLabels: TimelineInlineLabelLayout[];
  identityMarkers: TimelineIdentityMarkerLayout[];
  nodes: TimelineNodeLayout[];
  edges: TimelineEdgeLayout[];
  junctions: TimelineJunctionLayout[];
}

const DAY_IN_MS = 24 * 60 * 60 * 1000;
const LANE_GROUP_ORDER = ["main_roster", "two_way", "future_picks"];
const ASSET_KIND_ORDER: AssetKind[] = ["player_tenure", "pick_continuity"];
const SCENE_LEFT_PAD = 160;
const SCENE_RIGHT_PAD = 120;
const SCENE_ROW_START_Y = 120;
const SCENE_ROW_HEIGHT = 48;
const SCENE_BAND_GAP = 40;
const SCENE_EVENT_RAIL_Y = 72;
const JUNCTION_INSET_X = 20;
const INLINE_LABEL_HEIGHT = 24;
const INLINE_LABEL_HORIZONTAL_PADDING = 12;
const INLINE_LABEL_MIN_CLEARANCE = 28;
const IDENTITY_MARKER_HEIGHT = 28;
const IDENTITY_MARKER_HEADSHOT_SIZE = 28;
const IDENTITY_MARKER_HORIZONTAL_PADDING = 12;
const IDENTITY_MARKER_X_OFFSET = 14;
const TIMELINE_MIN_WINDOW_DAYS = 30;
const TIMELINE_MAX_WINDOW_DAYS = 180;
const UTC_MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

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
  if (contract.layout?.layout_meta) {
    return {
      start: contract.layout.layout_meta.start_date,
      end: contract.layout.layout_meta.end_date,
    };
  }

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

function clampNumber(value: number, min: number, max: number): number {
  if (value < min) {
    return min;
  }
  if (value > max) {
    return max;
  }
  return value;
}

function generatedContractError(message: string): never {
  throw new Error(`Generated timeline artifacts are inconsistent: ${message}`);
}

function validateGeneratedReferences(
  presentation: TimelinePresentationContract,
  layout: TimelineGeneratedLayoutContract,
  chapters: TimelineChapterExport[],
): void {
  const edgeById = new Map(presentation.edges.map((edge) => [edge.edge_id, edge]));
  const assetIds = new Set(presentation.edges.map((edge) => edge.asset_id));
  const eventIds = new Set(
    presentation.nodes
      .map((node) => node.event_id)
      .filter((eventId): eventId is string => Boolean(eventId)),
  );
  const chapterIds = new Set(chapters.map((chapter) => chapter.story_chapter_id));
  const minimapIds = new Set(layout.layout_meta.minimap_segments.map((segment) => segment.segment_id));

  for (const row of layout.lane_layout) {
    const edge = edgeById.get(row.segment_id);
    if (!edge) {
      generatedContractError(`lane_layout segment ${row.segment_id} does not match a presentation edge`);
    }
    if (edge.asset_id !== row.asset_id) {
      generatedContractError(`lane_layout segment ${row.segment_id} points at asset ${row.asset_id}, expected ${edge.asset_id}`);
    }
  }

  for (const row of layout.label_layout) {
    const edge = edgeById.get(row.segment_id);
    if (!edge) {
      generatedContractError(`label_layout segment ${row.segment_id} does not match a presentation edge`);
    }
    if (edge.asset_id !== row.asset_id) {
      generatedContractError(`label_layout segment ${row.segment_id} points at asset ${row.asset_id}, expected ${edge.asset_id}`);
    }
  }

  for (const row of layout.event_layout) {
    if (!eventIds.has(row.event_id)) {
      generatedContractError(`event_layout event ${row.event_id} does not match a presentation node event_id`);
    }
    for (const memberEventId of row.member_event_ids) {
      if (!eventIds.has(memberEventId)) {
        generatedContractError(`event_layout member event ${memberEventId} does not match a presentation node event_id`);
      }
    }
    for (const assetId of row.connected_asset_ids) {
      if (!assetIds.has(assetId)) {
        generatedContractError(`event_layout asset ${assetId} does not match a presentation asset_id`);
      }
    }
    for (const segmentId of [...Object.keys(row.incoming_slots), ...Object.keys(row.outgoing_slots)]) {
      if (!edgeById.has(segmentId)) {
        generatedContractError(`event_layout segment ${segmentId} does not match a presentation edge`);
      }
    }
    for (const link of row.transition_links) {
      if (!edgeById.has(link.source_segment_id) || !edgeById.has(link.target_segment_id)) {
        generatedContractError(`event_layout transition link for event ${row.event_id} references a missing segment`);
      }
      if (!assetIds.has(link.source_asset_id) || !assetIds.has(link.target_asset_id)) {
        generatedContractError(`event_layout transition link for event ${row.event_id} references a missing asset`);
      }
    }
  }

  for (const row of layout.chapter_layout) {
    if (!chapterIds.has(row.story_chapter_id)) {
      generatedContractError(`chapter_layout chapter ${row.story_chapter_id} does not match editorial-chapters.json`);
    }
    if (!minimapIds.has(row.minimap_anchor_id)) {
      generatedContractError(`chapter_layout chapter ${row.story_chapter_id} references missing minimap anchor ${row.minimap_anchor_id}`);
    }
    for (const assetId of row.highlight_asset_ids) {
      if (!assetIds.has(assetId)) {
        generatedContractError(`chapter_layout chapter ${row.story_chapter_id} references missing asset ${assetId}`);
      }
    }
    for (const eventId of row.highlight_event_ids) {
      if (!eventIds.has(eventId)) {
        generatedContractError(`chapter_layout chapter ${row.story_chapter_id} references missing event ${eventId}`);
      }
    }
  }
}

export function buildTimelineContract(
  presentation: TimelinePresentationContract,
  layout: TimelineGeneratedLayoutContract,
  chapters: TimelineChapterExport[],
): TimelineContract {
  validateGeneratedReferences(presentation, layout, chapters);

  const chapterLayoutById = new Map(layout.chapter_layout.map((chapter) => [chapter.story_chapter_id, chapter]));
  const storyChapters = chapters
    .slice()
    .sort((left, right) => left.chapter_order - right.chapter_order)
    .map((chapter) => {
      const chapterLayout = chapterLayoutById.get(chapter.story_chapter_id);
      return {
        ...chapter,
        focus_payload: {
          date_range: {
            start_date: chapterLayout?.window_start ?? chapter.start_date,
            end_date: chapterLayout?.window_end ?? chapter.end_date,
          },
          event_ids: [...(chapterLayout?.highlight_event_ids ?? [])],
          asset_ids: [...(chapterLayout?.highlight_asset_ids ?? [])],
          lane_groups: [],
          default_zoom: chapterLayout?.default_zoom ?? undefined,
          highlight_mode: "focus",
        },
        era_id: null,
      };
    });

  return {
    nodes: presentation.nodes,
    edges: presentation.edges,
    lanes: presentation.lanes,
    meta: presentation.meta,
    layout,
    editorial: {
      story_chapters: storyChapters,
    },
  };
}

export function coerceGeneratedLayoutContract(value: unknown): TimelineGeneratedLayoutContract {
  return value as TimelineGeneratedLayoutContract;
}

export function getDefaultUiState(contract: TimelineContract, chapter?: TimelineChapter | null): TimelineUiState {
  const bounds = getContractBounds(contract);
  const defaultWindowStart = contract.layout?.layout_meta.default_window_start ?? bounds.start;
  const defaultWindowEnd = contract.layout?.layout_meta.default_window_end ?? bounds.end;
  const baseState: TimelineUiState = {
    windowStart: defaultWindowStart,
    windowEnd: defaultWindowEnd,
    zoom: 1,
    assetKinds: [...ASSET_KIND_ORDER],
    selectedChapterId: null,
    selectedNodeId: null,
    selectedEdgeId: null,
  };
  return chapter ? activateTimelineChapter(contract, baseState, chapter.story_chapter_id) : baseState;
}

export function chapterFocus(chapter: TimelineChapter, fallbackBounds: { start: string; end: string }): TimelineFocus {
  const focusPayload = chapter.focus_payload ?? {};
  const dateRange = focusPayload.date_range ?? {};
  const windowStart = dateRange.start_date ?? chapter.start_date ?? fallbackBounds.start;
  const windowEnd = dateRange.end_date ?? chapter.end_date ?? fallbackBounds.end;
  return {
    windowStart,
    windowEnd,
    zoom: 1,
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

function formatLaneGroupLabel(value: string): string {
  return value.replaceAll("_", " ");
}

function formatMonthYearLabel(value: string): string {
  const date = toUtcDate(value);
  return `${UTC_MONTH_LABELS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

function legacyLaneRowsForContract(contract: TimelineContract): TimelineLaneLayout[] {
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
        lane_id: lane.asset_lane_id,
        lane_group: lane.lane_group,
        lane_index: lane.lane_index,
        y: cursorY,
        label: `${formatLaneGroupLabel(group)} ${lane.lane_index + 1}`,
      });
      cursorY += SCENE_ROW_HEIGHT;
    }
    cursorY += SCENE_BAND_GAP;
  }
  return rows;
}

function legacyAxisTicksForBounds(start: string, end: string, dayWidth: number, leftPad: number): TimelineTickLayout[] {
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
      kind: dayOffset % 28 === 0 ? "season_boundary" : "month",
    });
  }
  if (ticks[ticks.length - 1]?.date !== end) {
    const x = leftPad + totalDays * dayWidth;
    ticks.push({ x, date: end, label: end, major: true, kind: "season_boundary" });
  }
  return ticks;
}

function laneRowsFromLayoutSegments(
  segments: TimelineLayoutLaneSegment[],
  visibleSegmentIds: Set<string>,
): TimelineBandLayout[] {
  const grouped = new Map<string, Set<number>>();
  const visibleGrouped = new Map<string, Set<number>>();

  for (const segment of segments) {
    const slots = grouped.get(segment.lane_group) ?? new Set<number>();
    slots.add(segment.band_slot);
    grouped.set(segment.lane_group, slots);

    if (visibleSegmentIds.has(segment.segment_id)) {
      const visibleSlots = visibleGrouped.get(segment.lane_group) ?? new Set<number>();
      visibleSlots.add(segment.band_slot);
      visibleGrouped.set(segment.lane_group, visibleSlots);
    }
  }

  const orderedGroups = [
    ...LANE_GROUP_ORDER.filter((group) => grouped.has(group)),
    ...Array.from(grouped.keys()).filter((group) => !LANE_GROUP_ORDER.includes(group)).sort(),
  ];

  const bands: TimelineBandLayout[] = [];
  let cursorY = SCENE_ROW_START_Y;

  for (const group of orderedGroups) {
    const slots = [...(grouped.get(group) ?? new Set<number>())].sort((left, right) => left - right);
    const rows = slots.map((slot) => {
      const row: TimelineLaneLayout = {
        lane_id: `${group}:${slot}`,
        lane_group: group,
        lane_index: slot,
        y: cursorY,
        label: `${formatLaneGroupLabel(group)} ${slot + 1}`,
      };
      cursorY += SCENE_ROW_HEIGHT;
      return row;
    });

    bands.push({
      band_id: `band:${group}`,
      lane_group: group,
      label: formatLaneGroupLabel(group),
      visible: rows.some((row) => visibleGrouped.get(group)?.has(row.lane_index) ?? false),
      startY: rows[0]?.y ?? cursorY,
      endY: rows[rows.length - 1]?.y ?? cursorY,
      rows,
    });

    cursorY += SCENE_BAND_GAP;
  }

  return bands;
}

function legacyBandPrimitives(contract: TimelineContract): TimelineBandLayout[] {
  const laneRows = legacyLaneRowsForContract(contract);
  const grouped = new Map<string, TimelineLaneLayout[]>();

  for (const row of laneRows) {
    const rows = grouped.get(row.lane_group) ?? [];
    rows.push(row);
    grouped.set(row.lane_group, rows);
  }

  return [...grouped.entries()].map(([laneGroup, rows]) => ({
    band_id: `band:${laneGroup}`,
    lane_group: laneGroup,
    label: formatLaneGroupLabel(laneGroup),
    visible: true,
    startY: rows[0]?.y ?? SCENE_ROW_START_Y,
    endY: rows[rows.length - 1]?.y ?? SCENE_ROW_START_Y,
    rows,
  }));
}

function viewportRangeFromStart(
  bounds: { start: string; end: string },
  requestedStart: string,
  windowDays: number,
): { start: string; end: string } {
  const totalDays = Math.max(1, daysBetween(bounds.start, bounds.end));
  if (windowDays >= totalDays) {
    return {
      start: bounds.start,
      end: bounds.end,
    };
  }

  const latestStart = addDays(bounds.end, -windowDays);
  const safeLatestStart = compareIsoDates(latestStart, bounds.start) < 0 ? bounds.start : latestStart;
  const start = clampIsoDate(requestedStart, bounds.start, safeLatestStart);
  return {
    start,
    end: addDays(start, windowDays),
  };
}

function viewportRangeFromAnchor(
  bounds: { start: string; end: string },
  anchorDate: string,
  windowDays: number,
): { start: string; end: string } {
  const halfWindow = Math.floor(windowDays / 2);
  return viewportRangeFromStart(bounds, addDays(anchorDate, -halfWindow), windowDays);
}

function viewportDayBounds(bounds: { start: string; end: string }): { minWindowDays: number; maxWindowDays: number } {
  const totalDays = Math.max(1, daysBetween(bounds.start, bounds.end));
  const maxWindowDays = Math.max(1, Math.min(TIMELINE_MAX_WINDOW_DAYS, totalDays));
  const minWindowDays = Math.max(1, Math.min(TIMELINE_MIN_WINDOW_DAYS, maxWindowDays));
  return { minWindowDays, maxWindowDays };
}

function defaultViewportRange(contract: TimelineContract, bounds: { start: string; end: string }): {
  start: string;
  end: string;
  defaultWindowDays: number;
  minWindowDays: number;
  maxWindowDays: number;
} {
  const { minWindowDays, maxWindowDays } = viewportDayBounds(bounds);
  const requestedStart = contract.layout?.layout_meta.default_window_start ?? bounds.start;
  const requestedEnd = contract.layout?.layout_meta.default_window_end ?? bounds.end;
  const requestedDays = Math.max(1, daysBetween(requestedStart, requestedEnd));
  const defaultWindowDays = clampNumber(requestedDays, minWindowDays, maxWindowDays);
  const range = viewportRangeFromStart(bounds, requestedStart, defaultWindowDays);
  return {
    start: range.start,
    end: range.end,
    defaultWindowDays,
    minWindowDays,
    maxWindowDays,
  };
}

function zoomBoundsForWindow(defaultWindowDays: number, minWindowDays: number, maxWindowDays: number): {
  minZoom: number;
  maxZoom: number;
} {
  return {
    minZoom: defaultWindowDays / maxWindowDays,
    maxZoom: defaultWindowDays / minWindowDays,
  };
}

function windowDaysForZoom(
  defaultWindowDays: number,
  zoom: number,
  minWindowDays: number,
  maxWindowDays: number,
): number {
  const rawDays = Math.round(defaultWindowDays / zoom);
  return clampNumber(rawDays, minWindowDays, maxWindowDays);
}

export function getTimelineViewportMetrics(contract: TimelineContract, state: TimelineUiState): TimelineViewportMetrics {
  const bounds = getContractBounds(contract);
  const defaults = defaultViewportRange(contract, bounds);
  const zoomBounds = zoomBoundsForWindow(defaults.defaultWindowDays, defaults.minWindowDays, defaults.maxWindowDays);
  const fallbackWindowDays = Math.max(1, daysBetween(state.windowStart, state.windowEnd));
  const fallbackZoom = fallbackWindowDays > 0 ? defaults.defaultWindowDays / fallbackWindowDays : 1;
  const requestedZoom = Number.isFinite(state.zoom) && state.zoom > 0 ? state.zoom : fallbackZoom;
  const zoom = clampNumber(requestedZoom, zoomBounds.minZoom, zoomBounds.maxZoom);
  const windowDays = windowDaysForZoom(
    defaults.defaultWindowDays,
    zoom,
    defaults.minWindowDays,
    defaults.maxWindowDays,
  );
  const requestedStart = state.windowStart || defaults.start;
  const range = viewportRangeFromStart(bounds, requestedStart, windowDays);
  const dayWidth = contract.layout?.layout_meta.default_day_width ?? 18;

  return {
    boundsStart: bounds.start,
    boundsEnd: bounds.end,
    defaultWindowStart: defaults.start,
    defaultWindowEnd: defaults.end,
    defaultWindowDays: defaults.defaultWindowDays,
    minWindowDays: defaults.minWindowDays,
    maxWindowDays: defaults.maxWindowDays,
    minZoom: zoomBounds.minZoom,
    maxZoom: zoomBounds.maxZoom,
    zoom,
    windowStart: range.start,
    windowEnd: range.end,
    windowDays,
    viewportWidth: SCENE_LEFT_PAD + windowDays * dayWidth + SCENE_RIGHT_PAD,
  };
}

export function normalizeTimelineUiState(contract: TimelineContract, state: TimelineUiState): TimelineUiState {
  const viewport = getTimelineViewportMetrics(contract, state);
  const validChapterIds = new Set((contract.editorial?.story_chapters ?? []).map((chapter) => chapter.story_chapter_id));
  return {
    ...state,
    windowStart: viewport.windowStart,
    windowEnd: viewport.windowEnd,
    zoom: viewport.zoom,
    assetKinds: normalizeAssetKinds(state.assetKinds) || [],
    selectedChapterId: state.selectedChapterId && validChapterIds.has(state.selectedChapterId) ? state.selectedChapterId : null,
  };
}

export function setTimelineViewportWindow(
  contract: TimelineContract,
  state: TimelineUiState,
  windowStart: string,
  windowEnd: string,
): TimelineUiState {
  const bounds = getContractBounds(contract);
  const defaults = defaultViewportRange(contract, bounds);
  const safeStart = clampIsoDate(windowStart, bounds.start, bounds.end);
  const safeEnd = clampIsoDate(windowEnd, safeStart, bounds.end);
  const requestedDays = Math.max(1, daysBetween(safeStart, safeEnd));
  const windowDays = clampNumber(requestedDays, defaults.minWindowDays, defaults.maxWindowDays);
  const zoomBounds = zoomBoundsForWindow(defaults.defaultWindowDays, defaults.minWindowDays, defaults.maxWindowDays);
  const range = viewportRangeFromStart(bounds, safeStart, windowDays);
  return {
    ...state,
    windowStart: range.start,
    windowEnd: range.end,
    zoom: clampNumber(defaults.defaultWindowDays / windowDays, zoomBounds.minZoom, zoomBounds.maxZoom),
  };
}

export function setTimelineZoomLevel(
  contract: TimelineContract,
  state: TimelineUiState,
  zoom: number,
  anchorDate?: string,
): TimelineUiState {
  const viewport = getTimelineViewportMetrics(contract, state);
  const nextZoom = clampNumber(zoom, viewport.minZoom, viewport.maxZoom);
  const nextWindowDays = windowDaysForZoom(
    viewport.defaultWindowDays,
    nextZoom,
    viewport.minWindowDays,
    viewport.maxWindowDays,
  );
  const currentAnchor = anchorDate
    ? clampIsoDate(anchorDate, viewport.boundsStart, viewport.boundsEnd)
    : addDays(viewport.windowStart, Math.floor(viewport.windowDays / 2));
  const range = viewportRangeFromAnchor(
    { start: viewport.boundsStart, end: viewport.boundsEnd },
    currentAnchor,
    nextWindowDays,
  );
  return {
    ...state,
    windowStart: range.start,
    windowEnd: range.end,
    zoom: nextZoom,
  };
}

export function shiftTimelineViewport(
  contract: TimelineContract,
  state: TimelineUiState,
  deltaDays: number,
): TimelineUiState {
  const viewport = getTimelineViewportMetrics(contract, state);
  const nextStart = addDays(viewport.windowStart, Math.round(deltaDays));
  const range = viewportRangeFromStart(
    { start: viewport.boundsStart, end: viewport.boundsEnd },
    nextStart,
    viewport.windowDays,
  );
  return {
    ...state,
    windowStart: range.start,
    windowEnd: range.end,
    zoom: viewport.zoom,
  };
}

function setTimelineViewportDays(
  contract: TimelineContract,
  state: TimelineUiState,
  windowDays: number,
  options: {
    anchorDate?: string;
    windowStart?: string;
    selectedChapterId?: string | null;
  } = {},
): TimelineUiState {
  const bounds = getContractBounds(contract);
  const defaults = defaultViewportRange(contract, bounds);
  const zoomBounds = zoomBoundsForWindow(defaults.defaultWindowDays, defaults.minWindowDays, defaults.maxWindowDays);
  const safeWindowDays = clampNumber(
    Math.round(windowDays),
    defaults.minWindowDays,
    defaults.maxWindowDays,
  );
  const range = options.anchorDate
    ? viewportRangeFromAnchor(
      bounds,
      clampIsoDate(options.anchorDate, bounds.start, bounds.end),
      safeWindowDays,
    )
    : viewportRangeFromStart(
      bounds,
      clampIsoDate(options.windowStart ?? state.windowStart ?? defaults.start, bounds.start, bounds.end),
      safeWindowDays,
    );

  return {
    ...state,
    windowStart: range.start,
    windowEnd: range.end,
    zoom: clampNumber(defaults.defaultWindowDays / safeWindowDays, zoomBounds.minZoom, zoomBounds.maxZoom),
    selectedChapterId: options.selectedChapterId === undefined ? state.selectedChapterId : options.selectedChapterId,
  };
}

function orderedSceneChapters(contract: TimelineContract): TimelineSceneChapterFocus[] {
  const bounds = getContractBounds(contract);
  const chapterLayoutById = new Map(contract.layout?.chapter_layout.map((chapter) => [chapter.story_chapter_id, chapter]) ?? []);

  return (contract.editorial?.story_chapters ?? [])
    .slice()
    .sort((left, right) => left.chapter_order - right.chapter_order)
    .map((chapter) => {
      const chapterLayout = chapterLayoutById.get(chapter.story_chapter_id);
      const focus = chapterFocus(chapter, bounds);
      return {
        story_chapter_id: chapter.story_chapter_id,
        slug: chapter.slug,
        chapter_order: chapter.chapter_order,
        title: chapter.title,
        body: chapter.body,
        windowStart: focus.windowStart,
        windowEnd: focus.windowEnd,
        defaultZoom: chapterLayout?.default_zoom ?? null,
        highlightAssetIds: [...focus.assetIds],
        highlightEventIds: [...focus.eventIds],
        minimapAnchorId: chapterLayout?.minimap_anchor_id ?? null,
        anchorX: null,
        windowX1: 0,
        windowX2: 0,
        active: false,
      };
    });
}

function firstLinkedChapterIdForMinimapSegment(contract: TimelineContract, segmentId: string): string | null {
  return orderedSceneChapters(contract).find((chapter) => chapter.minimapAnchorId === segmentId)?.story_chapter_id ?? null;
}

export function jumpTimelineToMinimapSegment(
  contract: TimelineContract,
  state: TimelineUiState,
  segmentId: string,
): TimelineUiState {
  const segment = contract.layout?.layout_meta.minimap_segments.find((row) => row.segment_id === segmentId);
  if (!segment) {
    return normalizeTimelineUiState(contract, state);
  }

  const viewport = getTimelineViewportMetrics(contract, state);
  return setTimelineViewportDays(contract, state, viewport.windowDays, {
    anchorDate: segment.anchor_date,
    selectedChapterId: firstLinkedChapterIdForMinimapSegment(contract, segmentId),
  });
}

export function activateTimelineChapter(
  contract: TimelineContract,
  state: TimelineUiState,
  chapterId: string,
): TimelineUiState {
  const chapter = orderedSceneChapters(contract).find((row) => row.story_chapter_id === chapterId);
  if (!chapter) {
    return normalizeTimelineUiState(contract, {
      ...state,
      selectedChapterId: null,
    });
  }

  const viewport = getTimelineViewportMetrics(contract, state);
  const nextWindowDays = chapter.defaultZoom ?? viewport.windowDays;

  if (chapter.minimapAnchorId) {
    const segment = contract.layout?.layout_meta.minimap_segments.find((row) => row.segment_id === chapter.minimapAnchorId);
    if (segment) {
      return setTimelineViewportDays(contract, state, nextWindowDays, {
        anchorDate: segment.anchor_date,
        selectedChapterId: chapter.story_chapter_id,
      });
    }
  }

  return setTimelineViewportDays(contract, state, nextWindowDays, {
    windowStart: chapter.windowStart,
    selectedChapterId: chapter.story_chapter_id,
  });
}

function firstMonthTickOnOrAfter(start: string): string {
  const date = toUtcDate(start);
  if (date.getUTCDate() !== 1) {
    date.setUTCDate(1);
    date.setUTCMonth(date.getUTCMonth() + 1);
  }
  return toIsoDate(date);
}

function firstSeasonBoundaryOnOrAfter(start: string): string {
  const startDate = toUtcDate(start);
  const boundaryYear = startDate.getUTCMonth() > 6 || (startDate.getUTCMonth() === 6 && startDate.getUTCDate() > 1)
    ? startDate.getUTCFullYear() + 1
    : startDate.getUTCFullYear();
  return `${boundaryYear}-07-01`;
}

function addMonths(value: string, months: number): string {
  const date = toUtcDate(value);
  date.setUTCMonth(date.getUTCMonth() + months, 1);
  return toIsoDate(date);
}

function addYears(value: string, years: number): string {
  const date = toUtcDate(value);
  date.setUTCFullYear(date.getUTCFullYear() + years);
  return toIsoDate(date);
}

function chronologyTicksForLayout(
  windowStart: string,
  windowEnd: string,
  dayWidth: number,
  leftPad: number,
  axisStrategy: TimelineLayoutAxisStrategy | undefined,
): TimelineTickLayout[] {
  if (!axisStrategy) {
    return legacyAxisTicksForBounds(windowStart, windowEnd, dayWidth, leftPad);
  }

  const ticksByDate = new Map<string, TimelineTickLayout>();

  if (axisStrategy.minor_tick_unit === "month") {
    for (
      let date = firstMonthTickOnOrAfter(windowStart);
      compareIsoDates(date, windowEnd) <= 0;
      date = addMonths(date, 1)
    ) {
      ticksByDate.set(date, {
        x: pointForDate(date, windowStart, dayWidth, leftPad),
        date,
        label: formatMonthYearLabel(date),
        major: false,
        kind: "month",
      });
    }
  }

  if (axisStrategy.major_tick_unit === "season_boundary" && axisStrategy.season_boundary_rule === "july_1") {
    for (
      let date = firstSeasonBoundaryOnOrAfter(windowStart);
      compareIsoDates(date, windowEnd) <= 0;
      date = addYears(date, 1)
    ) {
      ticksByDate.set(date, {
        x: pointForDate(date, windowStart, dayWidth, leftPad),
        date,
        label: formatMonthYearLabel(date),
        major: true,
        kind: "season_boundary",
      });
    }
  }

  return [...ticksByDate.values()].sort((left, right) => compareIsoDates(left.date, right.date));
}

function timelineFocusFromSceneChapter(chapter: TimelineSceneChapterFocus): TimelineFocus {
  return {
    windowStart: chapter.windowStart,
    windowEnd: chapter.windowEnd,
    zoom: chapter.defaultZoom ?? 1,
    assetKinds: [...ASSET_KIND_ORDER],
    eventIds: [...chapter.highlightEventIds],
    assetIds: [...chapter.highlightAssetIds],
    laneGroups: [],
    highlightMode: "focus",
  };
}

export function buildTimelineScenePrimitives(contract: TimelineContract, state: TimelineUiState): TimelineScenePrimitives {
  const bounds = getContractBounds(contract);
  const viewport = getTimelineViewportMetrics(contract, state);
  const dayWidth = contract.layout?.layout_meta.default_day_width ?? 18;
  const windowStart = viewport.windowStart;
  const windowEnd = viewport.windowEnd;
  const edgeById = new Map(contract.edges.map((edge) => [edge.edge_id, edge]));
  const linkedChapterIdsByMinimapSegment = new Map<string, string[]>();

  for (const chapter of orderedSceneChapters(contract)) {
    if (!chapter.minimapAnchorId) {
      continue;
    }
    const rows = linkedChapterIdsByMinimapSegment.get(chapter.minimapAnchorId) ?? [];
    rows.push(chapter.story_chapter_id);
    linkedChapterIdsByMinimapSegment.set(chapter.minimapAnchorId, rows);
  }

  const visibleSegmentIds = new Set(
    (contract.layout?.lane_layout ?? [])
      .filter((segment) => dateRangesOverlap(segment.date_start, segment.date_end, windowStart, windowEnd))
      .filter((segment) => {
        const edge = edgeById.get(segment.segment_id);
        const kind = edge ? assetKindForEdge(edge) : null;
        return kind ? state.assetKinds.includes(kind) : true;
      })
      .map((segment) => segment.segment_id),
  );

  const bands = contract.layout?.lane_layout.length
    ? laneRowsFromLayoutSegments(contract.layout.lane_layout, visibleSegmentIds)
    : legacyBandPrimitives(contract);
  const chronology = {
    startDate: bounds.start,
    endDate: bounds.end,
    windowStart,
    windowEnd,
    dayWidth,
    axisStrategy: contract.layout?.layout_meta.axis_strategy ?? null,
    ticks: chronologyTicksForLayout(
      windowStart,
      windowEnd,
      dayWidth,
      SCENE_LEFT_PAD,
      contract.layout?.layout_meta.axis_strategy,
    ),
    minimapSegments: (contract.layout?.layout_meta.minimap_segments ?? []).map((segment) => ({
      ...segment,
      x1: pointForDate(segment.start_date, bounds.start, dayWidth, SCENE_LEFT_PAD),
      x2: pointForDate(segment.end_date, bounds.start, dayWidth, SCENE_LEFT_PAD),
      anchorX: pointForDate(segment.anchor_date, bounds.start, dayWidth, SCENE_LEFT_PAD),
      active: dateRangesOverlap(segment.start_date, segment.end_date, windowStart, windowEnd),
      linkedChapterIds: [...(linkedChapterIdsByMinimapSegment.get(segment.segment_id) ?? [])],
    })),
  };
  const minimapSegmentById = new Map(chronology.minimapSegments.map((segment) => [segment.segment_id, segment]));
  const chapters = orderedSceneChapters(contract).map((chapter) => ({
    ...chapter,
    anchorX: chapter.minimapAnchorId ? minimapSegmentById.get(chapter.minimapAnchorId)?.anchorX ?? null : null,
    windowX1: pointForDate(clampIsoDate(chapter.windowStart, bounds.start, bounds.end), bounds.start, dayWidth, SCENE_LEFT_PAD),
    windowX2: pointForDate(clampIsoDate(chapter.windowEnd, bounds.start, bounds.end), bounds.start, dayWidth, SCENE_LEFT_PAD),
    active: chapter.story_chapter_id === state.selectedChapterId,
  }));
  const activeFocus = chapters.find((chapter) => chapter.active) ?? null;

  return {
    leftPad: SCENE_LEFT_PAD,
    rightPad: SCENE_RIGHT_PAD,
    bands,
    chronology,
    chapters,
    activeFocus,
  };
}

function pointForDate(date: string, start: string, dayWidth: number, leftPad: number): number {
  return leftPad + daysBetween(start, date) * dayWidth;
}

function edgePath(x1: number, y1: number, x2: number, y2: number): string {
  const midX = x1 + (x2 - x1) / 2;
  return `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${midX.toFixed(1)} ${y1.toFixed(1)}, ${midX.toFixed(1)} ${y2.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`;
}

function strokeWidthForEdge(edge: TimelineContractEdge, segment: TimelineLayoutLaneSegment | undefined): number {
  if (segment?.lane_group === "future_picks" || edge.edge_type === "pick_line") {
    return 6;
  }
  if (segment?.lane_group === "two_way") {
    return 8;
  }
  return 10;
}

function rowYForSlot(
  laneRowByKey: Map<string, TimelineLaneLayout>,
  laneGroup: string,
  slot: number,
  fallbackY: number,
): number {
  return laneRowByKey.get(`${laneGroup}:${slot}`)?.y ?? fallbackY;
}

function sameDayOffset(clusterOrder: number, totalClustersOnDate: number): number {
  if (totalClustersOnDate <= 1) {
    return 0;
  }
  return (clusterOrder - (totalClustersOnDate + 1) / 2) * 18;
}

function average(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function buildJunctionLayouts(
  contract: TimelineContract,
  scene: TimelineScenePrimitives,
  laneRowByKey: Map<string, TimelineLaneLayout>,
  segmentById: Map<string, TimelineLayoutLaneSegment>,
  edgeById: Map<string, TimelineEdgeLayout>,
): TimelineJunctionLayout[] {
  const clusters = contract.layout?.event_layout ?? [];
  const clustersByDate = new Map<string, TimelineLayoutEvent[]>();

  for (const cluster of clusters) {
    const rows = clustersByDate.get(cluster.cluster_date) ?? [];
    rows.push(cluster);
    clustersByDate.set(cluster.cluster_date, rows);
  }

  return clusters.map((cluster) => {
    const x = pointForDate(
      cluster.cluster_date,
      scene.chronology.windowStart,
      scene.chronology.dayWidth,
      scene.leftPad,
    );
    const totalClustersOnDate = clustersByDate.get(cluster.cluster_date)?.length ?? 1;
    const visibleOnDate = isDateVisible(cluster.cluster_date, scene.chronology.windowStart, scene.chronology.windowEnd);

    const incomingStems = Object.entries(cluster.incoming_slots).flatMap(([segmentId, slot]) => {
      const segment = segmentById.get(segmentId);
      if (!segment || !edgeById.has(segmentId)) {
        return [];
      }
      const segmentY = rowYForSlot(laneRowByKey, segment.lane_group, slot, SCENE_ROW_START_Y);
      return [{
        stem_id: `${cluster.cluster_id}:incoming:${segmentId}`,
        segment_id: segmentId,
        lane_group: segment.lane_group,
        direction: "incoming" as const,
        x1: x - JUNCTION_INSET_X,
        y1: segmentY,
        x2: x,
        y2: segmentY,
        d: "",
      }];
    });

    const outgoingStems = Object.entries(cluster.outgoing_slots).flatMap(([segmentId, slot]) => {
      const segment = segmentById.get(segmentId);
      if (!segment || !edgeById.has(segmentId)) {
        return [];
      }
      const segmentY = rowYForSlot(laneRowByKey, segment.lane_group, slot, SCENE_ROW_START_Y);
      return [{
        stem_id: `${cluster.cluster_id}:outgoing:${segmentId}`,
        segment_id: segmentId,
        lane_group: segment.lane_group,
        direction: "outgoing" as const,
        x1: x,
        y1: segmentY,
        x2: x + JUNCTION_INSET_X,
        y2: segmentY,
        d: "",
      }];
    });

    const transitionSeed = cluster.transition_links.flatMap((link) => {
      const sourceSegment = segmentById.get(link.source_segment_id);
      const targetSegment = segmentById.get(link.target_segment_id);
      if (!sourceSegment || !targetSegment) {
        return [];
      }

      const sourceY = rowYForSlot(
        laneRowByKey,
        sourceSegment.lane_group,
        sourceSegment.exit_slot,
        SCENE_ROW_START_Y,
      );
      const targetY = rowYForSlot(
        laneRowByKey,
        targetSegment.lane_group,
        targetSegment.entry_slot,
        SCENE_ROW_START_Y,
      );

      return [{
        transition_link_id: link.transition_link_id,
        cluster_id: cluster.cluster_id,
        lane_group: targetSegment.lane_group,
        link_type: link.link_type,
        source_segment_id: link.source_segment_id,
        target_segment_id: link.target_segment_id,
        x1: x - JUNCTION_INSET_X,
        y1: sourceY,
        x2: x + JUNCTION_INSET_X,
        y2: targetY,
        d: "",
        visible: visibleOnDate,
      }];
    });

    const yCandidates = [
      ...incomingStems.map((stem) => stem.y1),
      ...outgoingStems.map((stem) => stem.y1),
      ...transitionSeed.flatMap((transition) => [transition.y1, transition.y2]),
    ];
    const baseY = yCandidates.length > 0 ? average(yCandidates) : SCENE_EVENT_RAIL_Y;
    const y = baseY + sameDayOffset(cluster.cluster_order, totalClustersOnDate);
    const spineY1 = yCandidates.length > 0 ? Math.min(y, ...yCandidates) : y;
    const spineY2 = yCandidates.length > 0 ? Math.max(y, ...yCandidates) : y;

    const stems = [...incomingStems, ...outgoingStems].map((stem) => ({
      ...stem,
      y2: y,
      d: stem.direction === "incoming"
        ? edgePath(stem.x1, stem.y1, stem.x2, y)
        : edgePath(stem.x1, y, stem.x2, stem.y1),
    }));

    const transitions = transitionSeed.map((transition) => ({
      ...transition,
      d: edgePath(transition.x1, transition.y1, transition.x2, transition.y2),
      visible: transition.visible
        && edgeById.has(transition.source_segment_id)
        && edgeById.has(transition.target_segment_id),
    }));

    return {
      junction_id: `junction:${cluster.cluster_id}`,
      event_id: cluster.event_id,
      cluster_id: cluster.cluster_id,
      cluster_date: cluster.cluster_date,
      cluster_order: cluster.cluster_order,
      junction_type: cluster.junction_type,
      x,
      y,
      spineY1,
      spineY2,
      visible: visibleOnDate,
      memberEventIds: [...cluster.member_event_ids],
      connectedAssetIds: [...cluster.connected_asset_ids],
      stems,
      transitions,
    };
  }).filter((junction) => junction.visible);
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

function estimateTextWidth(text: string, fontSize = 12): number {
  return Math.max(fontSize * 3, Math.round(text.length * fontSize * 0.58));
}

function resolveSegmentLabel(segment: TimelineLayoutLaneSegment, edge: TimelineContractEdge): string {
  return segment.identity_marker.label_text
    || String(edge.payload.player_name ?? edge.payload.label ?? edge.asset_id);
}

function normalizeStaticAssetPath(path: string | null): string | null {
  if (!path) {
    return null;
  }
  return path.startsWith("/") ? path : `/${path}`;
}

function buildLabelAndIdentityLayouts(
  contract: TimelineContract,
  edges: TimelineEdgeLayout[],
  segmentById: Map<string, TimelineLayoutLaneSegment>,
): {
  inlineLabels: TimelineInlineLabelLayout[];
  identityMarkers: TimelineIdentityMarkerLayout[];
} {
  const labelBySegmentId = new Map(contract.layout?.label_layout.map((row) => [row.segment_id, row]) ?? []);
  const inlineLabels: TimelineInlineLabelLayout[] = [];
  const identityMarkers: TimelineIdentityMarkerLayout[] = [];

  for (const edge of edges) {
    const segment = segmentById.get(edge.edge_id);
    const labelHint = labelBySegmentId.get(edge.edge_id);
    if (!segment || !labelHint) {
      continue;
    }

    const label = resolveSegmentLabel(segment, edge);
    const availableWidth = Math.max(0, edge.x2 - edge.x1);
    const labelWidth = estimateTextWidth(label) + INLINE_LABEL_HORIZONTAL_PADDING * 2;
    const inlineVisible = labelHint.inline_label_allowed
      && availableWidth >= labelWidth + INLINE_LABEL_MIN_CLEARANCE;
    const labelY = edge.y1 + (edge.y2 - edge.y1) / 2;

    inlineLabels.push({
      segment_id: segment.segment_id,
      asset_id: segment.asset_id,
      lane_group: segment.lane_group,
      label,
      priority: labelHint.label_priority,
      x: edge.x1 + availableWidth / 2,
      y: labelY,
      width: labelWidth,
      height: INLINE_LABEL_HEIGHT,
      visible: inlineVisible,
    });

    const markerVisible = labelHint.marker_side === "left"
      && (labelHint.fallback_marker_required || !inlineVisible);
    const imagePath = normalizeStaticAssetPath(segment.identity_marker.image_path);
    const usesHeadshot = segment.identity_marker.marker_variant === "headshot_text" && Boolean(imagePath);
    const markerTextWidth = estimateTextWidth(label);
    const markerWidth = usesHeadshot
      ? IDENTITY_MARKER_HEADSHOT_SIZE + markerTextWidth + IDENTITY_MARKER_HORIZONTAL_PADDING * 3
      : markerTextWidth + IDENTITY_MARKER_HORIZONTAL_PADDING * 2;

    identityMarkers.push({
      segment_id: segment.segment_id,
      asset_id: segment.asset_id,
      lane_group: segment.lane_group,
      label,
      priority: labelHint.label_priority,
      x: edge.x1 + IDENTITY_MARKER_X_OFFSET,
      y: edge.y1,
      width: markerWidth,
      height: IDENTITY_MARKER_HEIGHT,
      markerSide: labelHint.marker_side,
      markerVariant: usesHeadshot ? "headshot_text" : "text_only",
      imagePath: usesHeadshot ? imagePath : null,
      usesHeadshot,
      visible: markerVisible,
    });
  }

  inlineLabels.sort((left, right) => left.priority - right.priority);
  identityMarkers.sort((left, right) => left.priority - right.priority);

  return { inlineLabels, identityMarkers };
}

export function buildTimelineLayout(contract: TimelineContract, state: TimelineUiState): TimelineLayout {
  const normalizedState = normalizeTimelineUiState(contract, state);
  const scene = buildTimelineScenePrimitives(contract, normalizedState);
  const focus = scene.activeFocus ? timelineFocusFromSceneChapter(scene.activeFocus) : null;
  const viewport = getTimelineViewportMetrics(contract, normalizedState);
  const dayWidth = scene.chronology.dayWidth;
  const leftPad = scene.leftPad;
  const laneRows = scene.bands.flatMap((band) => band.rows);
  const laneRowByKey = new Map(laneRows.map((row) => [`${row.lane_group}:${row.lane_index}`, row] as const));
  const segmentById = new Map(contract.layout?.lane_layout.map((row) => [row.segment_id, row]) ?? []);
  const windowStart = scene.chronology.windowStart;
  const windowEnd = scene.chronology.windowEnd;
  const width = viewport.viewportWidth;

  const visibleEdges = contract.edges
    .filter((edge) => dateRangesOverlap(edge.start_date, edge.end_date, windowStart, windowEnd))
    .filter((edge) => {
      const kind = assetKindForEdge(edge);
      return kind ? normalizedState.assetKinds.includes(kind) : true;
    });

  const edgeById = new Map<string, TimelineEdgeLayout>();
  const edgeLayouts = visibleEdges.map((edge) => {
    const segment = segmentById.get(edge.edge_id);
    const laneGroup = segment?.lane_group ?? edge.lane_group;
    const laneIndex = segment?.band_slot ?? edge.lane_index;
    const y1 = rowYForSlot(laneRowByKey, laneGroup, segment?.entry_slot ?? laneIndex, SCENE_ROW_START_Y);
    const y2 = rowYForSlot(laneRowByKey, laneGroup, segment?.exit_slot ?? laneIndex, y1);
    const clippedStart = clampIsoDate(edge.start_date, windowStart, windowEnd);
    const clippedEnd = clampIsoDate(edge.end_date, windowStart, windowEnd);
    const x1 = pointForDate(clippedStart, windowStart, dayWidth, leftPad);
    const x2 = pointForDate(clippedEnd, windowStart, dayWidth, leftPad);
    const layout: TimelineEdgeLayout = {
      ...edge,
      x1,
      y1,
      x2,
      y2,
      d: edgePath(x1, y1, x2, y2),
      strokeWidth: strokeWidthForEdge(edge, segment),
      continuityAnchor: segment?.continuity_anchor ?? null,
      visible: true,
      focused: buildEdgeFocusState(edge, focus),
    };
    edgeById.set(edge.edge_id, layout);
    return layout;
  });

  const junctions = buildJunctionLayouts(
    contract,
    scene,
    laneRowByKey,
    segmentById,
    edgeById,
  );
  const junctionByEventId = new Map(junctions.map((junction) => [junction.event_id, junction]));

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
    const linkedJunction = node.event_id ? junctionByEventId.get(node.event_id) : null;
    const x = linkedJunction?.x ?? pointForDate(node.event_date, windowStart, dayWidth, leftPad);
    const connectedEdges = (edgesByNode.get(node.node_id) ?? [])
      .map((edgeId) => edgeById.get(edgeId))
      .filter((value): value is TimelineEdgeLayout => Boolean(value));
    const centeredY = linkedJunction
      ? linkedJunction.y
      : connectedEdges.length > 0
      ? connectedEdges.reduce((sum, edge) => sum + (edge.y1 + edge.y2) / 2, 0) / connectedEdges.length
      : laneRows[0]?.y ?? SCENE_EVENT_RAIL_Y;
    return {
      ...node,
      x,
      y: centeredY,
      visible: linkedJunction?.visible ?? isDateVisible(node.event_date, windowStart, windowEnd),
      focused: buildNodeFocusState(node, focus, connectedEdges),
      connectedEdgeIds: connectedEdges.map((edge) => edge.edge_id),
    };
  }).filter((node) => node.visible);

  const markers = (contract.editorial?.calendar_markers ?? []).map((marker) => ({
    id: String(marker.calendar_marker_id ?? marker.label),
    x: pointForDate(String(marker.marker_date), windowStart, dayWidth, leftPad),
    label: String(marker.label ?? marker.marker_type),
    date: String(marker.marker_date),
    visible: isDateVisible(String(marker.marker_date), windowStart, windowEnd),
    payload: marker.payload as Record<string, unknown>,
  }));
  const { inlineLabels, identityMarkers } = buildLabelAndIdentityLayouts(contract, edgeLayouts, segmentById);

  return {
    width,
    height: Math.max(860, (laneRows[laneRows.length - 1]?.y ?? 120) + 180),
    dayWidth,
    scene,
    laneRows,
    axisTicks: scene.chronology.ticks,
    markers,
    inlineLabels,
    identityMarkers,
    nodes: nodeLayouts,
    edges: edgeLayouts,
    junctions,
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

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

export function renderTimelineScene(layout: TimelineLayout): string {
  const bands = layout.scene.bands
    .map(
      (band) => `
        <g class="${cssClass(["timeline-band", `timeline-band--${band.lane_group}`, !band.visible && "is-muted"])}">
          <rect
            x="0"
            y="${band.startY - 28}"
            width="${layout.width}"
            height="${Math.max(SCENE_ROW_HEIGHT, band.endY - band.startY + SCENE_ROW_HEIGHT) + 24}"
            class="timeline-band__fill"
          ></rect>
          <line x1="0" y1="${band.startY - 28}" x2="${layout.width}" y2="${band.startY - 28}" class="timeline-band__boundary"></line>
          <line x1="0" y1="${band.endY + 20}" x2="${layout.width}" y2="${band.endY + 20}" class="timeline-band__boundary"></line>
          <text x="24" y="${band.startY - 42}" class="timeline-band__label">${band.label}</text>
        </g>
      `,
    )
    .join("");

  const laneLines = layout.laneRows
    .map(
      (lane) => `
        <line x1="0" y1="${lane.y}" x2="${layout.width}" y2="${lane.y}" class="timeline-grid__lane"></line>
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
    .filter((marker) => marker.visible)
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
            "timeline-strand",
            `timeline-strand--${edge.lane_group}`,
            `timeline-strand--${edge.edge_type}`,
            edge.focused && "is-focused",
            !edge.visible && "is-hidden",
          ])}"
          style="stroke-width: ${edge.strokeWidth}px"
          data-edge-id="${edge.edge_id}"
          data-asset-id="${edge.asset_id}"
          data-asset-kind="${String(edge.payload.asset_kind ?? "")}"
          data-kind="edge"
          data-inspectable="true"
          tabindex="0"
        ></path>
      `,
    )
    .join("");

  const inlineLabels = layout.inlineLabels
    .filter((label) => label.visible)
    .map(
      (label) => `
        <g
          class="${cssClass([
            "timeline-inline-label",
            `timeline-inline-label--${label.lane_group}`,
            !label.visible && "is-hidden",
          ])}"
          transform="translate(${label.x} ${label.y})"
        >
          <rect
            x="${-(label.width / 2)}"
            y="${-(label.height / 2)}"
            width="${label.width}"
            height="${label.height}"
            rx="${label.height / 2}"
            ry="${label.height / 2}"
            class="timeline-inline-label__pill"
          ></rect>
          <text x="0" y="4" class="timeline-inline-label__text">${escapeHtml(label.label)}</text>
        </g>
      `,
    )
    .join("");

  const identityMarkers = layout.identityMarkers
    .filter((marker) => marker.visible)
    .map((marker) => {
      const markerClipId = `timeline-marker-clip-${marker.segment_id.replaceAll(/[^a-zA-Z0-9_-]/g, "_")}`;
      const pillX = marker.usesHeadshot ? IDENTITY_MARKER_HEADSHOT_SIZE - 10 : 0;
      const pillWidth = Math.max(0, marker.width - pillX);
      const textX = marker.usesHeadshot ? pillX + 14 : IDENTITY_MARKER_HORIZONTAL_PADDING;
      const avatar = marker.usesHeadshot && marker.imagePath
        ? `
            <defs>
              <clipPath id="${markerClipId}">
                <circle cx="${IDENTITY_MARKER_HEADSHOT_SIZE / 2}" cy="${IDENTITY_MARKER_HEADSHOT_SIZE / 2}" r="${IDENTITY_MARKER_HEADSHOT_SIZE / 2 - 1}"></circle>
              </clipPath>
            </defs>
            <circle
              cx="${IDENTITY_MARKER_HEADSHOT_SIZE / 2}"
              cy="${IDENTITY_MARKER_HEADSHOT_SIZE / 2}"
              r="${IDENTITY_MARKER_HEADSHOT_SIZE / 2 - 1}"
              class="timeline-identity-marker__avatar-frame"
            ></circle>
            <image
              href="${escapeHtml(marker.imagePath)}"
              x="0"
              y="0"
              width="${IDENTITY_MARKER_HEADSHOT_SIZE}"
              height="${IDENTITY_MARKER_HEADSHOT_SIZE}"
              preserveAspectRatio="xMidYMid slice"
              clip-path="url(#${markerClipId})"
            ></image>
          `
        : "";

      return `
        <g
          class="${cssClass([
            "timeline-identity-marker",
            `timeline-identity-marker--${marker.markerVariant}`,
            `timeline-identity-marker--${marker.lane_group}`,
            !marker.visible && "is-hidden",
          ])}"
          transform="translate(${marker.x} ${marker.y - marker.height / 2})"
        >
          ${avatar}
          <rect
            x="${pillX}"
            y="0"
            width="${pillWidth}"
            height="${marker.height}"
            rx="${marker.height / 2}"
            ry="${marker.height / 2}"
            class="timeline-identity-marker__pill"
          ></rect>
          <text x="${textX}" y="${marker.height / 2 + 4}" class="timeline-identity-marker__text">${escapeHtml(marker.label)}</text>
        </g>
      `;
    })
    .join("");

  const junctions = layout.junctions
    .filter((junction) => junction.visible)
    .map((junction) => {
      const stems = junction.stems
        .map(
          (stem) => `
            <path
              d="${stem.d}"
              class="${cssClass(["timeline-junction__stem", `timeline-junction__stem--${stem.lane_group}`])}"
            ></path>
          `,
        )
        .join("");

      const transitions = junction.transitions
        .map(
          (transition) => `
            <path
              d="${transition.d}"
              class="${cssClass([
                "timeline-transition",
                `timeline-transition--${transition.link_type}`,
                `timeline-transition--${transition.lane_group}`,
                !transition.visible && "is-hidden",
              ])}"
            ></path>
          `,
        )
        .join("");

      return `
        <g class="${cssClass(["timeline-junction", `timeline-junction--${junction.junction_type}`, !junction.visible && "is-hidden"])}">
          <line
            x1="${junction.x}"
            y1="${junction.spineY1}"
            x2="${junction.x}"
            y2="${junction.spineY2}"
            class="timeline-junction__spine"
          ></line>
          ${stems}
          ${transitions}
        </g>
      `;
    })
    .join("");

  const nodes = layout.nodes
    .filter((node) => node.visible)
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
          <circle r="${node.event_order > 1 ? 4 : 5.5}" class="timeline-node__dot"></circle>
          <circle r="${node.event_order > 1 ? 9 : 11}" class="timeline-node__ring"></circle>
        </g>
      `,
    )
    .join("");

  return `
    <g class="timeline-bands">
      ${bands}
    </g>
    <g class="timeline-grid">
      ${laneLines}
    </g>
    <g class="timeline-axis">
      ${axis}
    </g>
    <g class="timeline-markers">
      ${markers}
    </g>
    <g class="timeline-junctions">
      ${junctions}
    </g>
    <g class="timeline-edges">
      ${edges}
    </g>
    <g class="timeline-inline-labels">
      ${inlineLabels}
    </g>
    <g class="timeline-identity-markers">
      ${identityMarkers}
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
