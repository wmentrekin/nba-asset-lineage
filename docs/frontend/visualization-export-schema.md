# Visualization Export Schema

## Purpose

This document defines the first concrete schema for the derived visualization
export described in
[`visualization-model.md`](visualization-model.md).

This export is the contract between:

- server-side lineage/visualization derivation
- the Astro frontend renderer

The frontend should consume this export directly rather than recomputing slot
logic, event staging, or lane truth from raw foundation surfaces.

## Status

This is the first locked schema draft for implementation planning.

It is intended to support:

- a base Memphis-only lineage graph
- fixed slot behavior
- grouped transaction nodes
- player/pick continuity strands
- additive pick context without forcing immediate visual use

## Design Rules

### Server-Side Responsibilities

This export should precompute:

- lane definitions
- lane occupancy truth
- transaction grouping
- strand segmentation
- connector intent
- adaptive lead / settle windows

### Frontend Responsibilities

The frontend should compute only:

- pixel coordinates
- viewport scaling
- hover/focus state
- animation of already-known shapes

## Top-Level Schema

```ts
interface VisualizationExportV1 {
  schema_version: "visualization_export_v1";
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
```

## Metadata

```ts
interface VisualizationTimeModel {
  unit: "day";
  scale: "linear";
  compact_spacing: "tight";
}

interface VisualizationBandConfig {
  main_roster_slot_count: 15;
  two_way_slot_count: 3;
  has_temporary_overflow_band: true;
  has_pick_band: true;
}
```

Notes:

- `source_span_*` reflects the foundation export span
- `render_span_*` allows the visualization layer to intentionally crop or pad
  the base source span later if needed
- the first version should usually keep source span and render span equal

## Lanes

Lanes are slot-owned, not asset-owned.

```ts
type VisualizationLaneBand =
  | "main_roster"
  | "two_way"
  | "temporary_overflow"
  | "pick";

interface VisualizationLane {
  lane_id: string;
  band: VisualizationLaneBand;
  slot_index: number;
  visual_order: number;
  is_dynamic: boolean;
  label: string;
}
```

Rules:

- `main_roster` lanes are slots `1-15`
- `two_way` lanes are slots `16-18`
- `temporary_overflow` lanes are dynamic and appear below `18`
- `pick` lanes are dynamic and appear below all player-related lanes
- `visual_order` is the canonical top-to-bottom order the renderer should use

## Assets

Assets are renderable identities, not occupancy truth.

```ts
type VisualizationAssetKind = "player" | "pick";

interface VisualizationPlayerMarker {
  marker_type: "player";
  display_name: string;
  headshot_url: string | null;
}

interface VisualizationPickMarker {
  marker_type: "pick";
  chip_label: string;
}

type VisualizationAssetMarker =
  | VisualizationPlayerMarker
  | VisualizationPickMarker;

interface VisualizationAsset {
  asset_id: string;
  asset_kind: VisualizationAssetKind;
  marker: VisualizationAssetMarker;
  display_label: string;
  foundation_asset_id: string;
  player_id?: string | null;
  pick_id?: string | null;
}
```

Notes:

- player markers are headshot + name
- pick markers are compact chip labels
- `foundation_asset_id` preserves direct traceability back to foundation truth

## Occupancy Intervals

Occupancy intervals are the primary lane-truth surface.

```ts
type VisualizationOccupancyKind =
  | "main_roster"
  | "two_way"
  | "temporary_overflow"
  | "pick_owned"
  | "pick_owed_out"
  | "pick_swap_right"
  | "pick_encumbered"
  | "pick_conditional";

interface VisualizationOccupancyInterval {
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
```

Rules:

- player occupancy should derive primarily from `daily_roster_state`
- pick occupancy should derive from snapshot / obligation truth
- this surface should be enough to explain why an asset is in a lane on a given
  day

## Event Nodes

Event nodes are grouped visual transaction anchors.

```ts
type VisualizationEventType = "trade" | "draft" | "waiver" | "signing";

interface VisualizationEventSummary {
  sent_asset_ids: string[];
  received_asset_ids: string[];
  sent_label: string | null;
  received_label: string | null;
}

interface VisualizationEventNode {
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
```

Rules:

- same-day grouped actions should resolve to one node where appropriate
- trade nodes should explicitly preserve `sent` and `received`
- hover/focus can expand beyond the compact label, but the base graph should
  not need the frontend to infer trade directions

## Strand Segments

Strand segments are renderable continuity pieces.

```ts
type VisualizationSegmentKind =
  | "resident"
  | "event_lead_in"
  | "event_settle_in"
  | "draft_conversion"
  | "termination";

interface VisualizationStrandSegment {
  segment_id: string;
  asset_id: string;
  lane_id: string;
  segment_kind: VisualizationSegmentKind;
  start_date: string;
  end_date: string;
  start_node_id?: string | null;
  end_node_id?: string | null;
}
```

Rules:

- resident segments represent stable occupancy between event windows
- lead-in segments represent outgoing curve preparation
- settle-in segments represent post-event landing behavior
- draft conversion segments should terminate the pick strand at the draft node
  and start the player strand there
- termination segments should end at the terminating node

## Event Connectors

Connectors define strand movement at nodes.

```ts
type VisualizationConnectorKind =
  | "outgoing"
  | "incoming"
  | "conversion"
  | "termination"
  | "lane_shift";

interface VisualizationEventConnector {
  connector_id: string;
  node_id: string;
  asset_id: string;
  connector_kind: VisualizationConnectorKind;
  from_lane_id: string | null;
  to_lane_id: string | null;
  lead_window_days: number;
  settle_window_days: number;
}
```

Rules:

- waivers should use `termination`
- draft pick-to-player handoff should use `conversion`
- trades should typically emit paired incoming/outgoing connectors
- lead and settle windows are precomputed, even if the frontend later converts
  them into curves

## Additive Context

The first version should preserve additive surfaces without requiring them to
drive the base graph.

```ts
interface VisualizationConditionalPickBranch {
  branch_id: string;
  original_team_code: string;
  round_number: number;
  trigger_kind: string;
  projectable: false;
  notes: string | null;
}

interface VisualizationConditionalPickFamily {
  family_id: string;
  family_kind: string;
  selection_rule: string;
  exclusivity_status: "unresolved" | "primary_realized" | "fallback_realized";
  primary_pick_id: string;
  primary_asset_id: string;
  fallback_branches: VisualizationConditionalPickBranch[];
}

interface VisualizationDraftLotteryContext {
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

interface VisualizationAdditiveContext {
  conditional_pick_families: VisualizationConditionalPickFamily[];
  draft_lottery_results: VisualizationDraftLotteryContext[];
}
```

Rules:

- conditional pick families remain bounded additive context
- draft lottery remains additive context
- neither should become graph-state-changing events in v1

## Render-Driving Minimum

The first real graph render should require only these parts of the derived
schema:

- `lanes`
- `assets`
- `occupancy_intervals`
- `event_nodes`
- `strand_segments`
- `event_connectors`

The renderer may ignore `additive_context` initially.

## Derived-From Mapping

The implementation should build the visualization export from foundation truth
using this mapping:

- `events` -> `event_nodes`
- `player_assets` + `pick_assets` -> `assets`
- `daily_roster_state` -> player-side `occupancy_intervals`
- pick snapshot / obligation truth -> pick-side `occupancy_intervals`
- `transitions` + event semantics -> `strand_segments` and `event_connectors`
- `conditional_pick_families` -> additive conditional pick context
- `draft_lottery_results` -> additive lottery context

## Invariants

The visualization export builder should enforce these invariants:

- no player occupies two player lanes on the same day
- no more than `15` main-roster lanes are occupied on the same day
- no more than `3` two-way lanes are occupied on the same day
- temporary-overflow assets do not occupy core slots unless status truly
  changes
- no concrete fallback pick appears simultaneously with its primary branch
- every strand segment is justified by occupancy truth and event truth
- every draft conversion maps exactly one pick continuity into one player start
- same-day grouped events resolve to one node
- waiver terminations end at the event

## Remaining Implementation Decisions

The schema is now defined at the contract level. The remaining implementation
questions are numeric or algorithmic:

- exact lead-in clamp values
- exact settle-in clamp values
- exact overflow-entry rules for 10-day / hardship / similar temporary cases
- exact visibility rules for additive conditional pick context in the UI

## Next Step

The next implementation pass should:

1. encode this schema in Python and TypeScript
2. build a server-side export generator
3. add invariant tests
4. migrate the Astro graph page to this export

