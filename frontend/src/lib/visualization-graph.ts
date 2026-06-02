import {
  getVisualizationAssetMarkerLabel,
  isVisualizationPickAsset,
  type VisualizationConnectorKind,
  type VisualizationEventNode,
  type VisualizationExportV1,
  type VisualizationLane,
  type VisualizationLaneBand,
  type VisualizationStrandSegment,
} from "./visualization";

export interface VisualizationTimelineRow {
  laneId: string;
  band: VisualizationLaneBand;
  label: string;
  visualOrder: number;
  y: number;
}

export interface VisualizationTimelineSegment {
  segmentId: string;
  assetId: string;
  assetKind: "player" | "pick";
  label: string;
  laneId: string;
  segmentKind: VisualizationStrandSegment["segment_kind"];
  x1: number;
  x2: number;
  y: number;
  startNodeId: string | null;
  endNodeId: string | null;
}

export interface VisualizationTimelineConnector {
  connectorId: string;
  assetId: string;
  assetKind: "player" | "pick";
  connectorKind: VisualizationConnectorKind;
  nodeId: string;
  x: number;
  x1: number;
  x2: number;
  y1: number;
  y2: number;
}

export interface VisualizationTimelineNode {
  nodeId: string;
  eventType: VisualizationEventNode["event_type"];
  eventDate: string;
  compactLabel: string;
  detailLabel: string | null;
  inboundAssetIds: string[];
  outboundAssetIds: string[];
  x: number;
  y: number;
  minY: number;
  maxY: number;
}

export interface VisualizationDateTick {
  date: string;
  x: number;
}

export interface VisualizationTimelineLayout {
  width: number;
  height: number;
  rows: VisualizationTimelineRow[];
  segments: VisualizationTimelineSegment[];
  connectors: VisualizationTimelineConnector[];
  nodes: VisualizationTimelineNode[];
  dateTicks: VisualizationDateTick[];
  playerBandEndY: number;
}

const LEFT_GUTTER = 188;
const RIGHT_GUTTER = 96;
const TOP_GUTTER = 72;
const BOTTOM_GUTTER = 56;
const DAY_SPACING = 2.25;
const MIN_SEGMENT_WIDTH = 4;
const PLAYER_ROW_HEIGHT = 34;
const PICK_ROW_HEIGHT = 20;
const BAND_GAP = 14;

export function buildVisualizationTimelineLayout(
  graph: VisualizationExportV1,
): VisualizationTimelineLayout {
  const lanes = [...graph.lanes].sort((left, right) => left.visual_order - right.visual_order);
  const rows = buildRows(lanes);
  const rowByLaneId = new Map(rows.map((row) => [row.laneId, row]));
  const assetById = new Map(graph.assets.map((asset) => [asset.asset_id, asset]));

  const axis = buildDateAxis(graph.render_span_start, graph.render_span_end);

  const nodeExtents = new Map<string, number[]>();
  for (const connector of graph.event_connectors) {
    const fromRow = connector.from_lane_id ? rowByLaneId.get(connector.from_lane_id) : undefined;
    const toRow = connector.to_lane_id ? rowByLaneId.get(connector.to_lane_id) : undefined;
    const extents = nodeExtents.get(connector.node_id) ?? [];
    if (fromRow) extents.push(fromRow.y);
    if (toRow) extents.push(toRow.y);
    nodeExtents.set(connector.node_id, extents);
  }

  const nodes = graph.event_nodes.map((node) => buildNode(node, axis, nodeExtents.get(node.node_id) ?? []));
  const nodeById = new Map(nodes.map((node) => [node.nodeId, node]));

  const segments = graph.strand_segments.flatMap((segment) => {
    const row = rowByLaneId.get(segment.lane_id);
    const asset = assetById.get(segment.asset_id);
    if (!row || !asset) return [];
    return [
      {
        segmentId: segment.segment_id,
        assetId: segment.asset_id,
        assetKind: isVisualizationPickAsset(asset) ? "pick" : "player",
        label: getVisualizationAssetMarkerLabel(asset),
        laneId: segment.lane_id,
        segmentKind: segment.segment_kind,
        x1: axis.xForDate(segment.start_date),
        x2: Math.max(axis.xForDate(segment.end_date), axis.xForDate(segment.start_date) + MIN_SEGMENT_WIDTH),
        y: row.y,
        startNodeId: segment.start_node_id ?? null,
        endNodeId: segment.end_node_id ?? null,
      } satisfies VisualizationTimelineSegment,
    ];
  });

  const connectors = graph.event_connectors.flatMap((connector) => {
    const node = nodeById.get(connector.node_id);
    const asset = assetById.get(connector.asset_id);
    if (!node || !asset) return [];

    const fromRow = connector.from_lane_id ? rowByLaneId.get(connector.from_lane_id) : undefined;
    const toRow = connector.to_lane_id ? rowByLaneId.get(connector.to_lane_id) : undefined;
    const leadOffset = connector.lead_window_days * DAY_SPACING;
    const settleOffset = connector.settle_window_days * DAY_SPACING;

    let x1 = node.x;
    let x2 = node.x;
    let y1 = node.y;
    let y2 = node.y;

    if (connector.connector_kind === "incoming") {
      x1 = node.x;
      x2 = node.x + settleOffset;
      y1 = node.y;
      y2 = toRow?.y ?? node.y;
    } else if (connector.connector_kind === "outgoing" || connector.connector_kind === "termination") {
      x1 = node.x - leadOffset;
      x2 = node.x;
      y1 = fromRow?.y ?? node.y;
      y2 = node.y;
    } else if (connector.connector_kind === "conversion") {
      if (fromRow && !toRow) {
        x1 = node.x - leadOffset;
        x2 = node.x;
        y1 = fromRow.y;
        y2 = node.y;
      } else {
        x1 = node.x;
        x2 = node.x + settleOffset;
        y1 = node.y;
        y2 = toRow?.y ?? node.y;
      }
    } else {
      x1 = node.x - 6;
      x2 = node.x + 6;
      y1 = fromRow?.y ?? node.y;
      y2 = toRow?.y ?? node.y;
    }

    return [
      {
        connectorId: connector.connector_id,
        assetId: connector.asset_id,
        assetKind: isVisualizationPickAsset(asset) ? "pick" : "player",
        connectorKind: connector.connector_kind,
        nodeId: connector.node_id,
        x: node.x,
        x1,
        x2,
        y1,
        y2,
      } satisfies VisualizationTimelineConnector,
    ];
  });

  const playerBandRows = rows.filter((row) => row.band !== "pick");
  const playerBandEndY = playerBandRows.at(-1)?.y ?? TOP_GUTTER;
  const width = axis.endX + RIGHT_GUTTER;
  const height = (rows.at(-1)?.y ?? TOP_GUTTER) + BOTTOM_GUTTER;

  return {
    width,
    height,
    rows,
    segments,
    connectors,
    nodes,
    dateTicks: axis.dateTicks,
    playerBandEndY,
  };
}

function buildRows(lanes: VisualizationLane[]): VisualizationTimelineRow[] {
  const rows: VisualizationTimelineRow[] = [];
  let currentY = TOP_GUTTER;
  let previousBand: VisualizationLaneBand | null = null;

  for (const lane of lanes) {
    const rowHeight = lane.band === "pick" ? PICK_ROW_HEIGHT : PLAYER_ROW_HEIGHT;
    if (previousBand !== null && previousBand !== lane.band) {
      currentY += BAND_GAP;
    }
    rows.push({
      laneId: lane.lane_id,
      band: lane.band,
      label: lane.label,
      visualOrder: lane.visual_order,
      y: currentY,
    });
    currentY += rowHeight;
    previousBand = lane.band;
  }

  return rows;
}

function buildNode(
  node: VisualizationEventNode,
  axis: ReturnType<typeof buildDateAxis>,
  participantYs: number[],
): VisualizationTimelineNode {
  const minY = participantYs.length ? Math.min(...participantYs) : TOP_GUTTER;
  const maxY = participantYs.length ? Math.max(...participantYs) : TOP_GUTTER;
  return {
    nodeId: node.node_id,
    eventType: node.event_type,
    eventDate: node.event_date,
    compactLabel: node.compact_label,
    detailLabel: node.detail_label,
    inboundAssetIds: node.inbound_asset_ids,
    outboundAssetIds: node.outbound_asset_ids,
    x: axis.xForDate(node.event_date),
    y: participantYs.length ? (minY + maxY) / 2 : TOP_GUTTER,
    minY,
    maxY,
  };
}

function buildDateAxis(startDate: string, endDate: string) {
  const start = parseIsoDate(startDate);
  const end = parseIsoDate(endDate);
  const totalDays = Math.max(0, diffDays(start, end));
  const startX = LEFT_GUTTER;
  const endX = startX + totalDays * DAY_SPACING;
  const dateTicks: VisualizationDateTick[] = [];

  for (let offset = 0; offset <= totalDays; offset += 1) {
    const current = addDays(start, offset);
    if (current.getUTCDate() !== 1) continue;
    dateTicks.push({
      date: formatIsoDate(current),
      x: startX + offset * DAY_SPACING,
    });
  }

  return {
    startX,
    endX,
    dateTicks,
    xForDate(dateString: string) {
      return startX + diffDays(start, parseIsoDate(dateString)) * DAY_SPACING;
    },
  };
}

function parseIsoDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function formatIsoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function addDays(date: Date, offset: number): Date {
  return new Date(date.getTime() + offset * 24 * 60 * 60 * 1000);
}

function diffDays(start: Date, end: Date): number {
  return Math.round((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000));
}
