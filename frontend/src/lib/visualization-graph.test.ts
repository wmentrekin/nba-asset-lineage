import { describe, expect, it } from "vitest";

import { buildVisualizationTimelineLayout } from "./visualization-graph";
import type { VisualizationExportV1 } from "./visualization";

const fixture = {
  schema_version: "visualization_export_v1",
  franchise: "MEM",
  generated_at: "2026-06-01T12:00:00Z",
  source_span_start: "2024-01-01",
  source_span_end: "2024-01-10",
  render_span_start: "2024-01-01",
  render_span_end: "2024-01-10",
  time_model: {
    unit: "day",
    scale: "linear",
    compact_spacing: "tight",
  },
  band_config: {
    main_roster_slot_count: 15,
    two_way_slot_count: 3,
    has_temporary_overflow_band: true,
    has_pick_band: true,
  },
  lanes: [
    {
      lane_id: "lane:main_roster:1",
      band: "main_roster",
      slot_index: 1,
      visual_order: 1,
      is_dynamic: false,
      label: "Main 1",
    },
    {
      lane_id: "lane:pick:1",
      band: "pick",
      slot_index: 1,
      visual_order: 2,
      is_dynamic: true,
      label: "Pick 1",
    },
  ],
  assets: [
    {
      asset_id: "asset:player:fixture",
      asset_kind: "player",
      marker: {
        marker_type: "player",
        display_name: "Fixture Player",
        headshot_url: null,
      },
      display_label: "Fixture Player",
      foundation_asset_id: "asset:player:fixture",
      player_id: "player:fixture",
    },
    {
      asset_id: "asset:pick:fixture",
      asset_kind: "pick",
      marker: {
        marker_type: "pick",
        chip_label: "2028 R1 MEM",
      },
      display_label: "2028 R1 MEM",
      foundation_asset_id: "asset:pick:fixture",
      pick_id: "pick:fixture",
    },
  ],
  occupancy_intervals: [
    {
      interval_id: "interval:fixture-player",
      asset_id: "asset:player:fixture",
      lane_id: "lane:main_roster:1",
      start_date: "2024-01-01",
      end_date: "2024-01-10",
      occupancy_kind: "main_roster",
      source_state_id: "state:fixture",
    },
    {
      interval_id: "interval:fixture-pick",
      asset_id: "asset:pick:fixture",
      lane_id: "lane:pick:1",
      start_date: "2024-01-01",
      end_date: "2024-01-03",
      occupancy_kind: "pick_owned",
    },
  ],
  event_nodes: [
    {
      node_id: "node:fixture",
      canonical_event_id: "canonical:fixture",
      source_group_id: null,
      event_type: "trade",
      event_date: "2024-01-04",
      sequence: 1,
      compact_label: "Fixture trade",
      detail_label: null,
      summary: {
        sent_asset_ids: ["asset:pick:fixture"],
        received_asset_ids: ["asset:player:fixture"],
        sent_label: "2028 R1 MEM",
        received_label: "Fixture Player",
      },
      inbound_asset_ids: ["asset:player:fixture"],
      outbound_asset_ids: ["asset:pick:fixture"],
    },
  ],
  strand_segments: [
    {
      segment_id: "segment:resident-player",
      asset_id: "asset:player:fixture",
      lane_id: "lane:main_roster:1",
      segment_kind: "resident",
      start_date: "2024-01-01",
      end_date: "2024-01-03",
      start_node_id: null,
      end_node_id: null,
    },
    {
      segment_id: "segment:resident-pick",
      asset_id: "asset:pick:fixture",
      lane_id: "lane:pick:1",
      segment_kind: "draft_conversion",
      start_date: "2024-01-03",
      end_date: "2024-01-04",
      start_node_id: null,
      end_node_id: "node:fixture",
    },
  ],
  event_connectors: [
    {
      connector_id: "connector:out",
      node_id: "node:fixture",
      asset_id: "asset:pick:fixture",
      connector_kind: "outgoing",
      from_lane_id: "lane:pick:1",
      to_lane_id: null,
      lead_window_days: 4,
      settle_window_days: 2,
    },
    {
      connector_id: "connector:in",
      node_id: "node:fixture",
      asset_id: "asset:player:fixture",
      connector_kind: "incoming",
      from_lane_id: null,
      to_lane_id: "lane:main_roster:1",
      lead_window_days: 4,
      settle_window_days: 2,
    },
  ],
  additive_context: {
    conditional_pick_families: [],
    draft_lottery_results: [],
  },
} satisfies VisualizationExportV1;

describe("buildVisualizationTimelineLayout", () => {
  it("maps visualization export surfaces into render rows, nodes, segments, and connectors", () => {
    const layout = buildVisualizationTimelineLayout(fixture);

    expect(layout.rows).toHaveLength(2);
    expect(layout.rows[0]?.laneId).toBe("lane:main_roster:1");
    expect(layout.rows[1]?.band).toBe("pick");

    expect(layout.nodes).toHaveLength(1);
    expect(layout.nodes[0]?.nodeId).toBe("node:fixture");

    expect(layout.segments).toHaveLength(2);
    expect(layout.segments[0]?.label).toBe("Fixture Player");
    expect(layout.segments[1]?.assetKind).toBe("pick");

    expect(layout.connectors).toHaveLength(2);
    expect(layout.connectors[0]?.nodeId).toBe("node:fixture");
    expect(layout.connectors[1]?.connectorKind).toBe("incoming");

    expect(layout.dateTicks.some((tick) => tick.date === "2024-01-01")).toBe(true);
    expect(layout.width).toBeGreaterThan(0);
    expect(layout.height).toBeGreaterThan(0);
  });
});
