export interface GraphEvent {
  event_id: string;
  event_type: "trade" | "draft" | "waiver" | "signing";
  event_date: string;
  label: string;
  sequence: number;
  source_group_id: string | null;
}

export interface GraphPlayerAsset {
  asset_id: string;
  player_id: string;
  display_name: string;
  years_experience?: number | null;
  baseline_order?: number | null;
  kind: "player";
}

export interface GraphPickAsset {
  asset_id: string;
  original_team: string;
  draft_year: number;
  round_number: number;
  protections: string | null;
  swap_detail: string | null;
  kind: "pick";
}

export interface GraphTransition {
  transition_id: string;
  event_id: string;
  asset_id: string;
  transition_type: "continuity" | "pick_to_player" | "acquired" | "departed";
  from_state?: string | null;
  to_state?: string | null;
  notes?: string | null;
}

export interface GraphExport {
  franchise: string;
  span_start: string;
  span_end: string;
  events: GraphEvent[];
  player_assets: GraphPlayerAsset[];
  pick_assets: GraphPickAsset[];
  transitions: GraphTransition[];
  roster_snapshots: unknown[];
}

export interface TimelineRow {
  index: number;
  y: number;
  band: "player" | "pick";
  label: string;
}

export interface TimelineEventPoint {
  eventId: string;
  label: string;
  eventType: GraphEvent["event_type"];
  date: string;
  x: number;
  inboundAssetIds: string[];
  outboundAssetIds: string[];
  minY: number;
  maxY: number;
  anchorY: number;
}

export interface TimelineSegment {
  assetId: string;
  label: string;
  kind: "player" | "pick";
  x1: number;
  x2: number;
  y: number;
}

export interface TimelineConnector {
  assetId: string;
  eventId: string;
  label: string;
  direction: "in" | "out" | "move";
  x: number;
  y1: number;
  y2: number;
  x1: number;
  x2: number;
}

export interface TimelineLayout {
  width: number;
  height: number;
  rows: TimelineRow[];
  eventPoints: TimelineEventPoint[];
  segments: TimelineSegment[];
  connectors: TimelineConnector[];
  playerRowCount: number;
  pickRowCount: number;
  playerBandEndY: number;
}

interface AssetMeta {
  assetId: string;
  label: string;
  kind: "player" | "pick";
  firstAppearanceIndex: number;
  eventTouchCount: number;
  yearsExperience: number | null;
  baselineOrder: number | null;
  draftYear: number | null;
  roundNumber: number | null;
}

interface ConnectorSeed {
  assetId: string;
  label: string;
  direction: "in" | "out" | "move";
  eventId: string;
  fromRowIndex: number | null;
  toRowIndex: number | null;
}

const PLAYER_SLOT_COUNT = 18;
const LEFT_GUTTER = 84;
const TOP_GUTTER = 86;
const PLAYER_ROW_HEIGHT = 34;
const PICK_ROW_HEIGHT = 26;
const BAND_GAP = 28;
const EVENT_SPACING = 142;
const RIGHT_GUTTER = 80;
const BOTTOM_GUTTER = 56;
const HEADER_SPINE_Y = 46;
const EVENT_ARC_OFFSET = 28;

export function buildTimelineLayout(graph: GraphExport): TimelineLayout {
  const assetMetaById = buildAssetMetaById(graph);
  const transitionsByEventId = buildTransitionsByEventId(graph.transitions);
  const baseEventPoints = graph.events.map((event, index) => {
    const x = LEFT_GUTTER + 36 + index * EVENT_SPACING;
    const eventTransitions = transitionsByEventId.get(event.event_id) ?? [];
    const inboundAssetIds = eventTransitions
      .filter((transition) => transition.transition_type === "acquired")
      .map((transition) => transition.asset_id);
    const outboundAssetIds = eventTransitions
      .filter((transition) => transition.transition_type === "departed")
      .map((transition) => transition.asset_id);
    return {
      eventId: event.event_id,
      label: event.label,
      eventType: event.event_type,
      date: event.event_date,
      x,
      inboundAssetIds,
      outboundAssetIds,
      minY: HEADER_SPINE_Y,
      maxY: HEADER_SPINE_Y,
      anchorY: HEADER_SPINE_Y,
    };
  });

  const laneResult = assignLanes(assetMetaById, baseEventPoints);
  const rows = buildRows(laneResult.pickLaneCount);
  const rowYByIndex = new Map(rows.map((row) => [row.index, row.y]));

  const segments = laneResult.segmentSeeds.map((segment) => ({
    ...segment,
    y: rowYByIndex.get(segment.rowIndex) ?? TOP_GUTTER,
  }));

  const eventPoints = baseEventPoints.map((event) => {
    const participantRows = laneResult.connectorSeeds.flatMap((connector) => {
      if (connector.eventId !== event.eventId) return [];
      return [connector.fromRowIndex, connector.toRowIndex].filter((value): value is number => value !== null);
    });
    const participantYs = participantRows
      .map((rowIndex) => rowYByIndex.get(rowIndex))
      .filter((value): value is number => typeof value === "number");
    const minY = participantYs.length ? Math.min(...participantYs) : HEADER_SPINE_Y;
    const maxY = participantYs.length ? Math.max(...participantYs) : HEADER_SPINE_Y;
    return {
      ...event,
      minY,
      maxY,
      anchorY: participantYs.length ? (minY + maxY) / 2 : HEADER_SPINE_Y,
    };
  });

  const eventById = new Map(eventPoints.map((event) => [event.eventId, event]));

  const connectors = laneResult.connectorSeeds.map((connector) => {
    const event = eventById.get(connector.eventId);
    const x = event?.x ?? LEFT_GUTTER;
    const y1 =
      connector.fromRowIndex !== null ? (rowYByIndex.get(connector.fromRowIndex) ?? HEADER_SPINE_Y) : event?.anchorY ?? HEADER_SPINE_Y;
    const y2 =
      connector.toRowIndex !== null ? (rowYByIndex.get(connector.toRowIndex) ?? HEADER_SPINE_Y) : event?.anchorY ?? HEADER_SPINE_Y;
    const x1 = connector.direction === "out" || connector.direction === "move" ? x - EVENT_ARC_OFFSET : x;
    const x2 = connector.direction === "in" || connector.direction === "move" ? x + EVENT_ARC_OFFSET : x;
    return {
      ...connector,
      x,
      y1,
      y2,
      x1,
      x2,
    };
  });

  const width = Math.max(1400, LEFT_GUTTER + 72 + graph.events.length * EVENT_SPACING + RIGHT_GUTTER);
  const height = rows.at(-1)?.y ? rows.at(-1)!.y + BOTTOM_GUTTER : TOP_GUTTER + BOTTOM_GUTTER;
  const playerBandEndY = rowYByIndex.get(PLAYER_SLOT_COUNT - 1) ?? TOP_GUTTER;

  return {
    width,
    height,
    rows,
    eventPoints,
    segments,
    connectors,
    playerRowCount: PLAYER_SLOT_COUNT,
    pickRowCount: laneResult.pickLaneCount,
    playerBandEndY,
  };
}

function buildTransitionsByEventId(transitions: GraphTransition[]): Map<string, GraphTransition[]> {
  const map = new Map<string, GraphTransition[]>();
  for (const transition of transitions) {
    const rows = map.get(transition.event_id) ?? [];
    rows.push(transition);
    map.set(transition.event_id, rows);
  }
  return map;
}

function buildAssetMetaById(graph: GraphExport): Map<string, AssetMeta> {
  const firstAppearanceIndexByAsset = new Map<string, number>();
  const eventTouchCountByAsset = new Map<string, number>();
  for (const [index, event] of graph.events.entries()) {
    const touchedAssets = new Set(
      graph.transitions.filter((transition) => transition.event_id === event.event_id).map((transition) => transition.asset_id),
    );
    for (const assetId of touchedAssets) {
      if (!firstAppearanceIndexByAsset.has(assetId)) {
        firstAppearanceIndexByAsset.set(assetId, index);
      }
      eventTouchCountByAsset.set(assetId, (eventTouchCountByAsset.get(assetId) ?? 0) + 1);
    }
  }

  const map = new Map<string, AssetMeta>();
  for (const asset of graph.player_assets) {
    map.set(asset.asset_id, {
      assetId: asset.asset_id,
      label: asset.display_name,
      kind: "player",
      firstAppearanceIndex: firstAppearanceIndexByAsset.get(asset.asset_id) ?? -1,
      eventTouchCount: eventTouchCountByAsset.get(asset.asset_id) ?? 0,
      yearsExperience: asset.years_experience ?? null,
      baselineOrder: asset.baseline_order ?? null,
      draftYear: null,
      roundNumber: null,
    });
  }
  for (const asset of graph.pick_assets) {
    map.set(asset.asset_id, {
      assetId: asset.asset_id,
      label: `${asset.draft_year} R${asset.round_number} ${asset.original_team}`,
      kind: "pick",
      firstAppearanceIndex: firstAppearanceIndexByAsset.get(asset.asset_id) ?? -1,
      eventTouchCount: eventTouchCountByAsset.get(asset.asset_id) ?? 0,
      yearsExperience: null,
      baselineOrder: null,
      draftYear: asset.draft_year,
      roundNumber: asset.round_number,
    });
  }
  return map;
}

function buildRows(pickLaneCount: number): TimelineRow[] {
  const rows: TimelineRow[] = [];
  for (let i = 0; i < PLAYER_SLOT_COUNT; i += 1) {
    rows.push({
      index: i,
      y: TOP_GUTTER + i * PLAYER_ROW_HEIGHT,
      band: "player",
      label: `${i + 1}`,
    });
  }

  const pickBandStartY = TOP_GUTTER + PLAYER_SLOT_COUNT * PLAYER_ROW_HEIGHT + BAND_GAP;
  for (let i = 0; i < pickLaneCount; i += 1) {
    rows.push({
      index: PLAYER_SLOT_COUNT + i,
      y: pickBandStartY + i * PICK_ROW_HEIGHT,
      band: "pick",
      label: `P${i + 1}`,
    });
  }

  return rows;
}

function assignLanes(
  assetMetaById: Map<string, AssetMeta>,
  eventPoints: TimelineEventPoint[],
): {
  segmentSeeds: Array<{ assetId: string; label: string; kind: "player" | "pick"; x1: number; x2: number; rowIndex: number }>;
  connectorSeeds: ConnectorSeed[];
  pickLaneCount: number;
} {
  const transitionHistoryByAsset = new Map<string, Array<{ x: number; direction: "in" | "out" }>>();
  for (const event of eventPoints) {
    for (const assetId of event.inboundAssetIds) {
      const history = transitionHistoryByAsset.get(assetId) ?? [];
      history.push({ x: event.x, direction: "in" });
      transitionHistoryByAsset.set(assetId, history);
    }
    for (const assetId of event.outboundAssetIds) {
      const history = transitionHistoryByAsset.get(assetId) ?? [];
      history.push({ x: event.x, direction: "out" });
      transitionHistoryByAsset.set(assetId, history);
    }
  }

  const activePlayers = new Set(
    [...assetMetaById.values()]
      .filter((asset) => asset.kind === "player" && startsActive(asset.assetId, transitionHistoryByAsset))
      .map((asset) => asset.assetId),
  );
  const activePicks = new Set(
    [...assetMetaById.values()]
      .filter((asset) => asset.kind === "pick" && startsActive(asset.assetId, transitionHistoryByAsset))
      .map((asset) => asset.assetId),
  );

  let activeRowByAsset = new Map<string, number>();
  const openSegmentStartByAsset = new Map<string, number>();
  const segmentSeeds: Array<{ assetId: string; label: string; kind: "player" | "pick"; x1: number; x2: number; rowIndex: number }> = [];
  const connectorSeeds: ConnectorSeed[] = [];
  const startX = LEFT_GUTTER + 18;
  const endX = Math.max(startX, eventPoints.at(-1)?.x ?? startX) + 36;

  activeRowByAsset = buildRowMap({
    activePlayers,
    activePicks,
    assetMetaById,
  });
  for (const assetId of activeRowByAsset.keys()) {
    openSegmentStartByAsset.set(assetId, startX);
  }

  let pickLaneCount = Math.max(
    1,
    [...activeRowByAsset.values()].filter((rowIndex) => rowIndex >= PLAYER_SLOT_COUNT).length,
  );

  for (const event of eventPoints) {
    const previousRowByAsset = new Map(activeRowByAsset);

    const outboundAssetIds = [...event.outboundAssetIds].sort((a, b) => compareAssetIds(a, b, assetMetaById));
    for (const assetId of outboundAssetIds) {
      const meta = assetMetaById.get(assetId);
      const rowIndex = previousRowByAsset.get(assetId);
      if (!meta || rowIndex === undefined) continue;
      segmentSeeds.push({
        assetId,
        label: meta.label,
        kind: meta.kind,
        x1: openSegmentStartByAsset.get(assetId) ?? startX,
        x2: computeSegmentExitX(openSegmentStartByAsset.get(assetId) ?? startX, event.x),
        rowIndex,
      });
      connectorSeeds.push({
        assetId,
        label: meta.label,
        direction: "out",
        eventId: event.eventId,
        fromRowIndex: rowIndex,
        toRowIndex: null,
      });
      openSegmentStartByAsset.delete(assetId);
      if (meta.kind === "player") activePlayers.delete(assetId);
      else activePicks.delete(assetId);
    }

    const inboundAssetIds = [...event.inboundAssetIds].sort((a, b) => compareAssetIds(a, b, assetMetaById));
    for (const assetId of inboundAssetIds) {
      const meta = assetMetaById.get(assetId);
      if (!meta) continue;
      if (meta.kind === "player") activePlayers.add(assetId);
      else activePicks.add(assetId);
    }

    const nextRowByAsset = buildRowMap({
      activePlayers,
      activePicks,
      assetMetaById,
    });
    pickLaneCount = Math.max(
      pickLaneCount,
      [...nextRowByAsset.values()].filter((rowIndex) => rowIndex >= PLAYER_SLOT_COUNT).length,
    );

    for (const assetId of inboundAssetIds) {
      const meta = assetMetaById.get(assetId);
      const rowIndex = nextRowByAsset.get(assetId);
      if (!meta || rowIndex === undefined) continue;
      connectorSeeds.push({
        assetId,
        label: meta.label,
        direction: "in",
        eventId: event.eventId,
        fromRowIndex: null,
        toRowIndex: rowIndex,
      });
      openSegmentStartByAsset.set(assetId, event.x + EVENT_ARC_OFFSET);
    }

    for (const [assetId, oldRowIndex] of previousRowByAsset.entries()) {
      if (outboundAssetIds.includes(assetId)) continue;
      const newRowIndex = nextRowByAsset.get(assetId);
      const meta = assetMetaById.get(assetId);
      if (!meta || newRowIndex === undefined || newRowIndex === oldRowIndex) continue;
      segmentSeeds.push({
        assetId,
        label: meta.label,
        kind: meta.kind,
        x1: openSegmentStartByAsset.get(assetId) ?? startX,
        x2: computeSegmentExitX(openSegmentStartByAsset.get(assetId) ?? startX, event.x),
        rowIndex: oldRowIndex,
      });
      connectorSeeds.push({
        assetId,
        label: meta.label,
        direction: "move",
        eventId: event.eventId,
        fromRowIndex: oldRowIndex,
        toRowIndex: newRowIndex,
      });
      openSegmentStartByAsset.set(assetId, event.x + EVENT_ARC_OFFSET);
    }

    activeRowByAsset = nextRowByAsset;
  }

  for (const [assetId, rowIndex] of activeRowByAsset.entries()) {
    const meta = assetMetaById.get(assetId);
    if (!meta) continue;
    segmentSeeds.push({
      assetId,
      label: meta.label,
      kind: meta.kind,
      x1: openSegmentStartByAsset.get(assetId) ?? startX,
      x2: endX,
      rowIndex,
    });
  }

  return {
    segmentSeeds: segmentSeeds.filter((segment) => segment.x2 > segment.x1),
    connectorSeeds,
    pickLaneCount,
  };
}

function computeSegmentExitX(segmentStartX: number, eventX: number): number {
  return Math.max(segmentStartX + 6, eventX - EVENT_ARC_OFFSET);
}

function buildRowMap({
  activePlayers,
  activePicks,
  assetMetaById,
}: {
  activePlayers: Set<string>;
  activePicks: Set<string>;
  assetMetaById: Map<string, AssetMeta>;
}): Map<string, number> {
  const rowByAsset = new Map<string, number>();
  const orderedPlayers = [...activePlayers].sort((a, b) => comparePlayerPriority(a, b, assetMetaById)).slice(0, PLAYER_SLOT_COUNT);
  orderedPlayers.forEach((assetId, index) => rowByAsset.set(assetId, index));

  const orderedPicks = [...activePicks].sort((a, b) => comparePickPriority(a, b, assetMetaById));
  orderedPicks.forEach((assetId, index) => rowByAsset.set(assetId, PLAYER_SLOT_COUNT + index));
  return rowByAsset;
}

function startsActive(
  assetId: string,
  transitionHistoryByAsset: Map<string, Array<{ x: number; direction: "in" | "out" }>>,
): boolean {
  const history = (transitionHistoryByAsset.get(assetId) ?? []).sort((a, b) => a.x - b.x);
  return history.length === 0 || history[0]?.direction === "out";
}

function comparePlayerPriority(a: string, b: string, assetMetaById: Map<string, AssetMeta>): number {
  const left = assetMetaById.get(a);
  const right = assetMetaById.get(b);
  if (!left || !right) return a.localeCompare(b);
  const leftAppearance = left.firstAppearanceIndex >= 0 ? left.firstAppearanceIndex : Number.MAX_SAFE_INTEGER;
  const rightAppearance = right.firstAppearanceIndex >= 0 ? right.firstAppearanceIndex : Number.MAX_SAFE_INTEGER;
  if (leftAppearance !== rightAppearance) return leftAppearance - rightAppearance;
  const leftExp = left.yearsExperience ?? -1;
  const rightExp = right.yearsExperience ?? -1;
  if (leftExp !== rightExp) return rightExp - leftExp;
  const leftOrder = left.baselineOrder ?? Number.MAX_SAFE_INTEGER;
  const rightOrder = right.baselineOrder ?? Number.MAX_SAFE_INTEGER;
  if (leftOrder !== rightOrder) return leftOrder - rightOrder;
  if (left.eventTouchCount !== right.eventTouchCount) return right.eventTouchCount - left.eventTouchCount;
  return left.label.localeCompare(right.label);
}

function comparePickPriority(a: string, b: string, assetMetaById: Map<string, AssetMeta>): number {
  const left = assetMetaById.get(a);
  const right = assetMetaById.get(b);
  if (!left || !right) return a.localeCompare(b);
  const leftYear = left.draftYear ?? Number.MAX_SAFE_INTEGER;
  const rightYear = right.draftYear ?? Number.MAX_SAFE_INTEGER;
  if (leftYear !== rightYear) return leftYear - rightYear;
  const leftRound = left.roundNumber ?? Number.MAX_SAFE_INTEGER;
  const rightRound = right.roundNumber ?? Number.MAX_SAFE_INTEGER;
  if (leftRound !== rightRound) return leftRound - rightRound;
  return left.label.localeCompare(right.label);
}

function compareAssetIds(a: string, b: string, assetMetaById: Map<string, AssetMeta>): number {
  const left = assetMetaById.get(a);
  const right = assetMetaById.get(b);
  if (!left || !right) return a.localeCompare(b);
  if (left.kind !== right.kind) return left.kind === "player" ? -1 : 1;
  return left.kind === "player" ? comparePlayerPriority(a, b, assetMetaById) : comparePickPriority(a, b, assetMetaById);
}
