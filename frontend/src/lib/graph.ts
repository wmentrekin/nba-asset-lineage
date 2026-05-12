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

export interface TimelineDateTick {
  date: string;
  x: number;
  dayOffset: number;
}

export interface TimelineSegment {
  assetId: string;
  label: string;
  kind: "player" | "pick";
  x1: number;
  x2: number;
  y: number;
  laneType: "home" | "trade-local";
  stageSide?: "outbound" | "inbound";
  homeRowIndex?: number | null;
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
  laneType: "home" | "trade-local";
  stageSide?: "outbound" | "inbound";
  fromRowIndex?: number | null;
  toRowIndex?: number | null;
}

export interface TimelineLayout {
  width: number;
  height: number;
  rows: TimelineRow[];
  eventPoints: TimelineEventPoint[];
  segments: TimelineSegment[];
  connectors: TimelineConnector[];
  dateTicks: TimelineDateTick[];
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
  fromY?: number | null;
  toY?: number | null;
  x?: number;
  x1?: number;
  x2?: number;
  laneType: "home" | "trade-local";
  stageSide?: "outbound" | "inbound";
}

interface SegmentSeed {
  assetId: string;
  label: string;
  kind: "player" | "pick";
  x1: number;
  x2: number;
  rowIndex?: number | null;
  y?: number;
  laneType: "home" | "trade-local";
  stageSide?: "outbound" | "inbound";
}

interface EventLayoutSeed {
  anchorY: number;
  participantYs: number[];
}

const PLAYER_SLOT_COUNT = 18;
const LEFT_GUTTER = 84;
const TOP_GUTTER = 86;
const PLAYER_ROW_HEIGHT = 34;
const PICK_ROW_HEIGHT = 26;
const BAND_GAP = 28;
const DAY_SPACING = 6;
const SAME_DAY_EVENT_OFFSET = 14;
const RIGHT_GUTTER = 80;
const BOTTOM_GUTTER = 56;
const HEADER_SPINE_Y = 46;
const EVENT_ARC_OFFSET = 28;
const TRADE_STAGE_WIDTH = 18;
const TRADE_STAGE_ROW_GAP = 18;
const TRADE_STAGE_GROUP_GAP = 16;

export function buildTimelineLayout(graph: GraphExport): TimelineLayout {
  const assetMetaById = buildAssetMetaById(graph);
  const transitionsByEventId = buildTransitionsByEventId(graph.transitions);
  const dateAxis = buildDateAxis(graph.events, graph.span_start, graph.span_end);
  const baseEventPoints = graph.events.map((event) => {
    const x = dateAxis.eventXById.get(event.event_id) ?? dateAxis.startX;
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
    y: segment.y ?? getRowY(segment.rowIndex ?? 0),
    homeRowIndex: segment.rowIndex ?? null,
  }));

  const eventPoints = baseEventPoints.map((event) => {
    const eventLayout = laneResult.eventLayoutById.get(event.eventId);
    const participantYs = eventLayout?.participantYs ?? [];
    const minY = participantYs.length ? Math.min(...participantYs) : HEADER_SPINE_Y;
    const maxY = participantYs.length ? Math.max(...participantYs) : HEADER_SPINE_Y;
    return {
      ...event,
      minY,
      maxY,
      anchorY: eventLayout?.anchorY ?? (participantYs.length ? (minY + maxY) / 2 : HEADER_SPINE_Y),
    };
  });

  const eventById = new Map(eventPoints.map((event) => [event.eventId, event]));

  const connectors = laneResult.connectorSeeds.map((connector) => {
    const event = eventById.get(connector.eventId);
    const x = connector.x ?? event?.x ?? LEFT_GUTTER;
    const y1 =
      connector.fromY ??
      (connector.fromRowIndex !== null ? (rowYByIndex.get(connector.fromRowIndex) ?? HEADER_SPINE_Y) : event?.anchorY ?? HEADER_SPINE_Y);
    const y2 =
      connector.toY ??
      (connector.toRowIndex !== null ? (rowYByIndex.get(connector.toRowIndex) ?? HEADER_SPINE_Y) : event?.anchorY ?? HEADER_SPINE_Y);
    const x1 = connector.x1 ?? (connector.direction === "out" || connector.direction === "move" ? x - EVENT_ARC_OFFSET : x);
    const x2 = connector.x2 ?? (connector.direction === "in" || connector.direction === "move" ? x + EVENT_ARC_OFFSET : x);
    return {
      ...connector,
      x,
      y1,
      y2,
      x1,
      x2,
    };
  });

  const width = Math.max(1400, dateAxis.endX + RIGHT_GUTTER);
  const height = rows.at(-1)?.y ? rows.at(-1)!.y + BOTTOM_GUTTER : TOP_GUTTER + BOTTOM_GUTTER;
  const playerBandEndY = rowYByIndex.get(PLAYER_SLOT_COUNT - 1) ?? TOP_GUTTER;

  return {
    width,
    height,
    rows,
    eventPoints,
    segments,
    connectors,
    dateTicks: dateAxis.ticks,
    playerRowCount: PLAYER_SLOT_COUNT,
    pickRowCount: laneResult.pickLaneCount,
    playerBandEndY,
  };
}

function buildDateAxis(
  events: GraphEvent[],
  spanStart: string,
  spanEnd: string,
): {
  startX: number;
  endX: number;
  ticks: TimelineDateTick[];
  eventXById: Map<string, number>;
} {
  const startDate = parseIsoDate(spanStart);
  const endDate = parseIsoDate(spanEnd);
  const fallbackStartDate = events[0] ? parseIsoDate(events[0].event_date) : startDate;
  const fallbackEndDate = events.at(-1) ? parseIsoDate(events.at(-1)!.event_date) : endDate;
  const axisStart = startDate.getTime() <= fallbackStartDate.getTime() ? startDate : fallbackStartDate;
  const axisEnd = endDate.getTime() >= fallbackEndDate.getTime() ? endDate : fallbackEndDate;
  const totalDays = Math.max(0, diffDays(axisStart, axisEnd));
  const startX = LEFT_GUTTER + 36;

  const ticks: TimelineDateTick[] = [];
  for (let dayOffset = 0; dayOffset <= totalDays; dayOffset += 1) {
    const date = addDays(axisStart, dayOffset);
    ticks.push({
      date: formatIsoDate(date),
      x: startX + dayOffset * DAY_SPACING,
      dayOffset,
    });
  }

  const eventsByDate = new Map<string, GraphEvent[]>();
  for (const event of events) {
    const groupedEvents = eventsByDate.get(event.event_date) ?? [];
    groupedEvents.push(event);
    eventsByDate.set(event.event_date, groupedEvents);
  }

  const eventXById = new Map<string, number>();
  for (const [date, groupedEvents] of eventsByDate.entries()) {
    const dayOffset = diffDays(axisStart, parseIsoDate(date));
    const baseX = startX + dayOffset * DAY_SPACING;
    const clusterOffset = ((groupedEvents.length - 1) * SAME_DAY_EVENT_OFFSET) / 2;
    groupedEvents.forEach((event, index) => {
      eventXById.set(event.event_id, baseX + index * SAME_DAY_EVENT_OFFSET - clusterOffset);
    });
  }

  const lastClusterX = events.length
    ? Math.max(...events.map((event) => eventXById.get(event.event_id) ?? startX))
    : startX + totalDays * DAY_SPACING;

  return {
    startX,
    endX: Math.max(startX + totalDays * DAY_SPACING + 36, lastClusterX + 36),
    ticks,
    eventXById,
  };
}

function parseIsoDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function formatIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function addDays(date: Date, dayCount: number): Date {
  return new Date(date.getTime() + dayCount * 24 * 60 * 60 * 1000);
}

function diffDays(startDate: Date, endDate: Date): number {
  return Math.round((endDate.getTime() - startDate.getTime()) / (24 * 60 * 60 * 1000));
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
      y: getRowY(i),
      band: "player",
      label: `${i + 1}`,
    });
  }

  for (let i = 0; i < pickLaneCount; i += 1) {
    rows.push({
      index: PLAYER_SLOT_COUNT + i,
      y: getRowY(PLAYER_SLOT_COUNT + i),
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
  segmentSeeds: SegmentSeed[];
  connectorSeeds: ConnectorSeed[];
  eventLayoutById: Map<string, EventLayoutSeed>;
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

  let playerSlots = seedPlayerSlots(activePlayers, assetMetaById);
  let activeRowByAsset = buildRowMap({
    playerSlots,
    activePicks,
    assetMetaById,
  });
  const openSegmentStartByAsset = new Map<string, number>();
  const segmentSeeds: SegmentSeed[] = [];
  const connectorSeeds: ConnectorSeed[] = [];
  const eventLayoutById = new Map<string, EventLayoutSeed>();
  const startX = LEFT_GUTTER + 18;
  const endX = Math.max(startX, eventPoints.at(-1)?.x ?? startX) + 36;

  for (const assetId of activeRowByAsset.keys()) {
    openSegmentStartByAsset.set(assetId, startX);
  }

  let pickLaneCount = Math.max(
    1,
    [...activeRowByAsset.values()].filter((rowIndex) => rowIndex >= PLAYER_SLOT_COUNT).length,
  );

  for (const [eventIndex, event] of eventPoints.entries()) {
    const previousRowByAsset = new Map(activeRowByAsset);
    const tradeStage = isTradeEvent(event)
      ? buildTradeStageGeometry(eventPoints, eventIndex, event)
      : null;

    const outboundAssetIds = [...event.outboundAssetIds].sort((a, b) => compareAssetIds(a, b, assetMetaById));
    for (const assetId of outboundAssetIds) {
      const meta = assetMetaById.get(assetId);
      const rowIndex = previousRowByAsset.get(assetId);
      if (!meta || rowIndex === undefined) continue;
      const segmentExitX =
        tradeStage !== null ? computeSegmentExitX(openSegmentStartByAsset.get(assetId) ?? startX, tradeStage.outboundStageStartX) : computeSegmentExitX(openSegmentStartByAsset.get(assetId) ?? startX, event.x);
      segmentSeeds.push({
        assetId,
        label: meta.label,
        kind: meta.kind,
        x1: openSegmentStartByAsset.get(assetId) ?? startX,
        x2: segmentExitX,
        rowIndex,
        laneType: "home",
      });
      openSegmentStartByAsset.delete(assetId);
      if (meta.kind === "player") {
        activePlayers.delete(assetId);
        releasePlayerSlot(playerSlots, assetId);
      } else {
        activePicks.delete(assetId);
      }
    }

    playerSlots = compactPlayerSlots(playerSlots);

    const inboundAssetIds = [...event.inboundAssetIds].sort((a, b) => compareAssetIds(a, b, assetMetaById));
    for (const assetId of inboundAssetIds) {
      const meta = assetMetaById.get(assetId);
      if (!meta) continue;
      if (meta.kind === "player") {
        activePlayers.add(assetId);
        claimLowestOpenPlayerSlot(playerSlots, assetId);
      } else {
        activePicks.add(assetId);
      }
    }

    const nextRowByAsset = buildRowMap({
      playerSlots,
      activePicks,
      assetMetaById,
    });
    pickLaneCount = Math.max(
      pickLaneCount,
      [...nextRowByAsset.values()].filter((rowIndex) => rowIndex >= PLAYER_SLOT_COUNT).length,
    );

    const eventParticipantYs: number[] = [];
    if (tradeStage !== null) {
      const tradeStageRows = buildTradeStageRows({
        outboundAssetIds,
        inboundAssetIds,
        previousRowByAsset,
        nextRowByAsset,
      });

      for (const assetId of outboundAssetIds) {
        const meta = assetMetaById.get(assetId);
        const homeRowIndex = previousRowByAsset.get(assetId);
        const stageY = tradeStageRows.outboundYByAsset.get(assetId);
        if (!meta || homeRowIndex === undefined || stageY === undefined) continue;
        segmentSeeds.push({
          assetId,
          label: meta.label,
          kind: meta.kind,
          x1: tradeStage.outboundStageStartX,
          x2: tradeStage.outboundStageEndX,
          y: stageY,
          laneType: "trade-local",
          stageSide: "outbound",
        });
        connectorSeeds.push({
          assetId,
          label: meta.label,
          direction: "move",
          eventId: event.eventId,
          fromRowIndex: homeRowIndex,
          toRowIndex: null,
          toY: stageY,
          x: (tradeStage.outboundStageStartX + tradeStage.outboundStageEndX) / 2,
          x1: tradeStage.outboundStageStartX,
          x2: tradeStage.outboundStageEndX,
          laneType: "trade-local",
          stageSide: "outbound",
        });
        connectorSeeds.push({
          assetId,
          label: meta.label,
          direction: "out",
          eventId: event.eventId,
          fromRowIndex: null,
          toRowIndex: null,
          fromY: stageY,
          x: event.x,
          x1: tradeStage.outboundStageEndX,
          x2: event.x,
          laneType: "trade-local",
          stageSide: "outbound",
        });
      }

      for (const assetId of inboundAssetIds) {
        const meta = assetMetaById.get(assetId);
        const homeRowIndex = nextRowByAsset.get(assetId);
        const stageY = tradeStageRows.inboundYByAsset.get(assetId);
        if (!meta || homeRowIndex === undefined || stageY === undefined) continue;
        connectorSeeds.push({
          assetId,
          label: meta.label,
          direction: "in",
          eventId: event.eventId,
          fromRowIndex: null,
          toRowIndex: null,
          toY: stageY,
          x: event.x,
          x1: event.x,
          x2: tradeStage.inboundStageStartX,
          laneType: "trade-local",
          stageSide: "inbound",
        });
        segmentSeeds.push({
          assetId,
          label: meta.label,
          kind: meta.kind,
          x1: tradeStage.inboundStageStartX,
          x2: tradeStage.inboundStageEndX,
          y: stageY,
          laneType: "trade-local",
          stageSide: "inbound",
        });
        connectorSeeds.push({
          assetId,
          label: meta.label,
          direction: "move",
          eventId: event.eventId,
          fromRowIndex: null,
          toRowIndex: homeRowIndex,
          fromY: stageY,
          x: (tradeStage.inboundStageStartX + tradeStage.inboundStageEndX) / 2,
          x1: tradeStage.inboundStageStartX,
          x2: tradeStage.inboundStageEndX,
          laneType: "trade-local",
          stageSide: "inbound",
        });
        openSegmentStartByAsset.set(assetId, tradeStage.inboundStageEndX);
      }

      eventLayoutById.set(event.eventId, {
        anchorY: tradeStageRows.anchorY,
        participantYs: tradeStageRows.participantYs,
      });
    } else {
      for (const assetId of outboundAssetIds) {
        const meta = assetMetaById.get(assetId);
        const rowIndex = previousRowByAsset.get(assetId);
        if (!meta || rowIndex === undefined) continue;
        connectorSeeds.push({
          assetId,
          label: meta.label,
          direction: "out",
          eventId: event.eventId,
          fromRowIndex: rowIndex,
          toRowIndex: null,
          laneType: "home",
        });
        eventParticipantYs.push(getRowY(rowIndex));
      }

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
          laneType: "home",
        });
        openSegmentStartByAsset.set(assetId, event.x + EVENT_ARC_OFFSET);
        eventParticipantYs.push(getRowY(rowIndex));
      }
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
        laneType: "home",
      });
      connectorSeeds.push({
        assetId,
        label: meta.label,
        direction: "move",
        eventId: event.eventId,
        fromRowIndex: oldRowIndex,
        toRowIndex: newRowIndex,
        laneType: "home",
      });
      openSegmentStartByAsset.set(assetId, event.x + EVENT_ARC_OFFSET);
      if (tradeStage === null) {
        eventParticipantYs.push(getRowY(oldRowIndex), getRowY(newRowIndex));
      }
    }

    if (!eventLayoutById.has(event.eventId)) {
      const uniqueParticipantYs = [...new Set(eventParticipantYs)];
      const minY = uniqueParticipantYs.length ? Math.min(...uniqueParticipantYs) : HEADER_SPINE_Y;
      const maxY = uniqueParticipantYs.length ? Math.max(...uniqueParticipantYs) : HEADER_SPINE_Y;
      eventLayoutById.set(event.eventId, {
        anchorY: uniqueParticipantYs.length ? (minY + maxY) / 2 : HEADER_SPINE_Y,
        participantYs: uniqueParticipantYs,
      });
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
      laneType: "home",
    });
  }

  return {
    segmentSeeds: segmentSeeds.filter((segment) => segment.x2 > segment.x1),
    connectorSeeds,
    eventLayoutById,
    pickLaneCount,
  };
}

function getRowY(rowIndex: number): number {
  if (rowIndex < PLAYER_SLOT_COUNT) {
    return TOP_GUTTER + rowIndex * PLAYER_ROW_HEIGHT;
  }
  const pickBandStartY = TOP_GUTTER + PLAYER_SLOT_COUNT * PLAYER_ROW_HEIGHT + BAND_GAP;
  return pickBandStartY + (rowIndex - PLAYER_SLOT_COUNT) * PICK_ROW_HEIGHT;
}

function isTradeEvent(event: TimelineEventPoint): boolean {
  return event.eventType === "trade" && (event.outboundAssetIds.length > 0 || event.inboundAssetIds.length > 0);
}

function buildTradeStageGeometry(
  _eventPoints: TimelineEventPoint[],
  _eventIndex: number,
  event: TimelineEventPoint,
): {
  outboundStageStartX: number;
  outboundStageEndX: number;
  inboundStageStartX: number;
  inboundStageEndX: number;
} {
  return {
    outboundStageStartX: event.x - EVENT_ARC_OFFSET - TRADE_STAGE_WIDTH,
    outboundStageEndX: event.x - EVENT_ARC_OFFSET,
    inboundStageStartX: event.x + EVENT_ARC_OFFSET,
    inboundStageEndX: event.x + EVENT_ARC_OFFSET + TRADE_STAGE_WIDTH,
  };
}

function buildTradeStageRows({
  outboundAssetIds,
  inboundAssetIds,
  previousRowByAsset,
  nextRowByAsset,
}: {
  outboundAssetIds: string[];
  inboundAssetIds: string[];
  previousRowByAsset: Map<string, number>;
  nextRowByAsset: Map<string, number>;
}): {
  anchorY: number;
  participantYs: number[];
  outboundYByAsset: Map<string, number>;
  inboundYByAsset: Map<string, number>;
} {
  const homeYs = [
    ...outboundAssetIds
      .map((assetId) => previousRowByAsset.get(assetId))
      .filter((rowIndex): rowIndex is number => rowIndex !== undefined)
      .map((rowIndex) => getRowY(rowIndex)),
    ...inboundAssetIds
      .map((assetId) => nextRowByAsset.get(assetId))
      .filter((rowIndex): rowIndex is number => rowIndex !== undefined)
      .map((rowIndex) => getRowY(rowIndex)),
  ];
  const baseY = homeYs.length ? homeYs.reduce((sum, y) => sum + y, 0) / homeYs.length : HEADER_SPINE_Y;
  const outboundYByAsset = new Map<string, number>();
  const inboundYByAsset = new Map<string, number>();

  if (outboundAssetIds.length > 0 && inboundAssetIds.length > 0) {
    const outboundHeight = (outboundAssetIds.length - 1) * TRADE_STAGE_ROW_GAP;
    const inboundHeight = (inboundAssetIds.length - 1) * TRADE_STAGE_ROW_GAP;
    const totalHeight = outboundHeight + TRADE_STAGE_GROUP_GAP + inboundHeight;
    const topY = baseY - totalHeight / 2;
    outboundAssetIds.forEach((assetId, index) => {
      outboundYByAsset.set(assetId, topY + index * TRADE_STAGE_ROW_GAP);
    });
    const inboundStartY = topY + outboundHeight + TRADE_STAGE_GROUP_GAP;
    inboundAssetIds.forEach((assetId, index) => {
      inboundYByAsset.set(assetId, inboundStartY + index * TRADE_STAGE_ROW_GAP);
    });
  } else {
    const stagedAssetIds = outboundAssetIds.length > 0 ? outboundAssetIds : inboundAssetIds;
    const startY = baseY - ((stagedAssetIds.length - 1) * TRADE_STAGE_ROW_GAP) / 2;
    stagedAssetIds.forEach((assetId, index) => {
      const y = startY + index * TRADE_STAGE_ROW_GAP;
      if (outboundAssetIds.length > 0) {
        outboundYByAsset.set(assetId, y);
      } else {
        inboundYByAsset.set(assetId, y);
      }
    });
  }

  const participantYs = [...outboundYByAsset.values(), ...inboundYByAsset.values()];
  const minY = participantYs.length ? Math.min(...participantYs) : HEADER_SPINE_Y;
  const maxY = participantYs.length ? Math.max(...participantYs) : HEADER_SPINE_Y;

  return {
    anchorY: participantYs.length ? (minY + maxY) / 2 : HEADER_SPINE_Y,
    participantYs,
    outboundYByAsset,
    inboundYByAsset,
  };
}

function computeSegmentExitX(segmentStartX: number, eventX: number): number {
  return Math.max(segmentStartX + 6, eventX - EVENT_ARC_OFFSET);
}

function buildRowMap({
  playerSlots,
  activePicks,
  assetMetaById,
}: {
  playerSlots: Array<string | null>;
  activePicks: Set<string>;
  assetMetaById: Map<string, AssetMeta>;
}): Map<string, number> {
  const rowByAsset = new Map<string, number>();
  playerSlots.forEach((assetId, index) => {
    if (assetId) rowByAsset.set(assetId, index);
  });

  const orderedPicks = [...activePicks].sort((a, b) => comparePickPriority(a, b, assetMetaById));
  orderedPicks.forEach((assetId, index) => rowByAsset.set(assetId, PLAYER_SLOT_COUNT + index));
  return rowByAsset;
}

function seedPlayerSlots(activePlayers: Set<string>, assetMetaById: Map<string, AssetMeta>): Array<string | null> {
  const slots = Array<string | null>(PLAYER_SLOT_COUNT).fill(null);
  [...activePlayers]
    .sort((a, b) => comparePlayerPriority(a, b, assetMetaById))
    .slice(0, PLAYER_SLOT_COUNT)
    .forEach((assetId, index) => {
      slots[index] = assetId;
    });
  return slots;
}

function releasePlayerSlot(playerSlots: Array<string | null>, assetId: string): void {
  const slotIndex = playerSlots.indexOf(assetId);
  if (slotIndex >= 0) {
    playerSlots[slotIndex] = null;
  }
}

function compactPlayerSlots(playerSlots: Array<string | null>): Array<string | null> {
  const compacted = playerSlots.filter((assetId): assetId is string => assetId !== null);
  return [...compacted, ...Array<string | null>(PLAYER_SLOT_COUNT - compacted.length).fill(null)];
}

function claimLowestOpenPlayerSlot(playerSlots: Array<string | null>, assetId: string): void {
  const openSlotIndex = playerSlots.findIndex((slotAssetId) => slotAssetId === null);
  if (openSlotIndex >= 0) {
    playerSlots[openSlotIndex] = assetId;
  }
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
