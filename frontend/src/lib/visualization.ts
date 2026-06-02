export const VISUALIZATION_EXPORT_SCHEMA_VERSION = "visualization_export_v1" as const;

export const VISUALIZATION_LANE_BANDS = ["main_roster", "two_way", "temporary_overflow", "pick"] as const;
export type VisualizationLaneBand = (typeof VISUALIZATION_LANE_BANDS)[number];

export const VISUALIZATION_ASSET_KINDS = ["player", "pick"] as const;
export type VisualizationAssetKind = (typeof VISUALIZATION_ASSET_KINDS)[number];

export const VISUALIZATION_OCCUPANCY_KINDS = [
  "main_roster",
  "two_way",
  "temporary_overflow",
  "pick_owned",
  "pick_owed_out",
  "pick_swap_right",
  "pick_encumbered",
  "pick_conditional",
] as const;
export type VisualizationOccupancyKind = (typeof VISUALIZATION_OCCUPANCY_KINDS)[number];

export const VISUALIZATION_EVENT_TYPES = ["trade", "draft", "waiver", "signing"] as const;
export type VisualizationEventType = (typeof VISUALIZATION_EVENT_TYPES)[number];

export const VISUALIZATION_SEGMENT_KINDS = [
  "resident",
  "event_lead_in",
  "event_settle_in",
  "draft_conversion",
  "termination",
] as const;
export type VisualizationSegmentKind = (typeof VISUALIZATION_SEGMENT_KINDS)[number];

export const VISUALIZATION_CONNECTOR_KINDS = [
  "outgoing",
  "incoming",
  "conversion",
  "termination",
  "lane_shift",
] as const;
export type VisualizationConnectorKind = (typeof VISUALIZATION_CONNECTOR_KINDS)[number];

export const VISUALIZATION_CONDITIONAL_PICK_EXCLUSIVITY_STATUSES = [
  "unresolved",
  "primary_realized",
  "fallback_realized",
] as const;
export type VisualizationConditionalPickExclusivityStatus =
  (typeof VISUALIZATION_CONDITIONAL_PICK_EXCLUSIVITY_STATUSES)[number];

export interface VisualizationTimeModel {
  unit: "day";
  scale: "linear";
  compact_spacing: "tight";
}

export interface VisualizationBandConfig {
  main_roster_slot_count: 15;
  two_way_slot_count: 3;
  has_temporary_overflow_band: true;
  has_pick_band: true;
}

export interface VisualizationLane {
  lane_id: string;
  band: VisualizationLaneBand;
  slot_index: number;
  visual_order: number;
  is_dynamic: boolean;
  label: string;
}

export interface VisualizationPlayerMarker {
  marker_type: "player";
  display_name: string;
  headshot_url: string | null;
}

export interface VisualizationPickMarker {
  marker_type: "pick";
  chip_label: string;
}

export type VisualizationAssetMarker = VisualizationPlayerMarker | VisualizationPickMarker;

interface VisualizationAssetBase {
  asset_id: string;
  display_label: string;
  foundation_asset_id: string;
}

export interface VisualizationPlayerAsset extends VisualizationAssetBase {
  asset_kind: "player";
  marker: VisualizationPlayerMarker;
  player_id: string | null;
  pick_id?: null;
}

export interface VisualizationPickAsset extends VisualizationAssetBase {
  asset_kind: "pick";
  marker: VisualizationPickMarker;
  pick_id: string | null;
  player_id?: null;
}

export type VisualizationAsset = VisualizationPlayerAsset | VisualizationPickAsset;

export interface VisualizationOccupancyInterval {
  interval_id: string;
  asset_id: string;
  lane_id: string;
  start_date: string;
  end_date: string;
  occupancy_kind: VisualizationOccupancyKind;
  source_state_id?: string | null;
  source_snapshot_id?: string | null;
  source_obligation_id?: string | null;
}

export interface VisualizationEventSummary {
  sent_asset_ids: string[];
  received_asset_ids: string[];
  sent_label: string | null;
  received_label: string | null;
}

export interface VisualizationEventNode {
  node_id: string;
  canonical_event_id: string;
  source_group_id: string | null;
  event_type: VisualizationEventType;
  event_date: string;
  sequence: number;
  compact_label: string;
  detail_label: string | null;
  summary: VisualizationEventSummary | null;
  inbound_asset_ids: string[];
  outbound_asset_ids: string[];
}

export interface VisualizationStrandSegment {
  segment_id: string;
  asset_id: string;
  lane_id: string;
  segment_kind: VisualizationSegmentKind;
  start_date: string;
  end_date: string;
  start_node_id?: string | null;
  end_node_id?: string | null;
}

export interface VisualizationEventConnector {
  connector_id: string;
  node_id: string;
  asset_id: string;
  connector_kind: VisualizationConnectorKind;
  from_lane_id: string | null;
  to_lane_id: string | null;
  lead_window_days: number;
  settle_window_days: number;
}

export interface VisualizationConditionalPickBranch {
  branch_id: string;
  original_team_code: string;
  round_number: number;
  trigger_kind: string;
  projectable: false;
  notes: string | null;
}

export interface VisualizationConditionalPickFamily {
  family_id: string;
  family_kind: string;
  selection_rule: string;
  exclusivity_status: VisualizationConditionalPickExclusivityStatus;
  primary_pick_id: string;
  primary_asset_id: string;
  fallback_branches: VisualizationConditionalPickBranch[];
}

export interface VisualizationDraftLotteryContext {
  lottery_result_id: string;
  draft_year: number;
  lottery_date: string | null;
  original_team_code: string | null;
  owner_team_code: string | null;
  result_pick_slot: number;
  pick_id: string | null;
  pick_asset_id: string | null;
  draft_selection_id: string | null;
}

export interface VisualizationAdditiveContext {
  conditional_pick_families: VisualizationConditionalPickFamily[];
  draft_lottery_results: VisualizationDraftLotteryContext[];
}

export interface VisualizationExportV1 {
  schema_version: typeof VISUALIZATION_EXPORT_SCHEMA_VERSION;
  franchise: "MEM";
  generated_at: string;
  source_span_start: string;
  source_span_end: string;
  render_span_start: string;
  render_span_end: string;
  time_model: VisualizationTimeModel;
  band_config: VisualizationBandConfig;
  lanes: VisualizationLane[];
  assets: VisualizationAsset[];
  occupancy_intervals: VisualizationOccupancyInterval[];
  event_nodes: VisualizationEventNode[];
  strand_segments: VisualizationStrandSegment[];
  event_connectors: VisualizationEventConnector[];
  additive_context: VisualizationAdditiveContext;
}

export function isVisualizationPlayerAsset(asset: VisualizationAsset): asset is VisualizationPlayerAsset {
  return asset.asset_kind === "player";
}

export function isVisualizationPickAsset(asset: VisualizationAsset): asset is VisualizationPickAsset {
  return asset.asset_kind === "pick";
}

export function getVisualizationAssetMarkerLabel(asset: VisualizationAsset): string {
  return isVisualizationPlayerAsset(asset) ? asset.marker.display_name : asset.marker.chip_label;
}
