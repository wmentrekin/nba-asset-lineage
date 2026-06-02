import { describe, expect, it } from "vitest";

import {
  VISUALIZATION_CONNECTOR_KINDS,
  VISUALIZATION_EVENT_TYPES,
  VISUALIZATION_EXPORT_SCHEMA_VERSION,
  VISUALIZATION_LANE_BANDS,
  VISUALIZATION_OCCUPANCY_KINDS,
  VISUALIZATION_SEGMENT_KINDS,
  getVisualizationAssetMarkerLabel,
  isVisualizationPickAsset,
  isVisualizationPlayerAsset,
  type VisualizationExportV1,
} from "./visualization";

const SAMPLE_VISUALIZATION_EXPORT = {
  schema_version: VISUALIZATION_EXPORT_SCHEMA_VERSION,
  franchise: "MEM",
  generated_at: "2026-06-01T12:00:00Z",
  source_span_start: "2016-01-01",
  source_span_end: "2026-01-01",
  render_span_start: "2016-01-01",
  render_span_end: "2026-01-01",
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
      lane_id: "lane:main:1",
      band: "main_roster",
      slot_index: 1,
      visual_order: 1,
      is_dynamic: false,
      label: "1",
    },
    {
      lane_id: "lane:pick:2028:r1:phx",
      band: "pick",
      slot_index: 1,
      visual_order: 19,
      is_dynamic: true,
      label: "2028 R1 PHX",
    },
  ],
  assets: [
    {
      asset_id: "asset:player:ja-morant",
      asset_kind: "player",
      marker: {
        marker_type: "player",
        display_name: "Ja Morant",
        headshot_url: null,
      },
      display_label: "Ja Morant",
      foundation_asset_id: "foundation:asset:player:ja-morant",
      player_id: "player:ja-morant",
    },
    {
      asset_id: "asset:pick:2028:r1:phx",
      asset_kind: "pick",
      marker: {
        marker_type: "pick",
        chip_label: "2028 R1 PHX",
      },
      display_label: "2028 first-round pick via PHX",
      foundation_asset_id: "foundation:asset:pick:2028:r1:phx",
      pick_id: "pick:2028:r1:phx",
    },
  ],
  occupancy_intervals: [
    {
      interval_id: "interval:player:ja:1",
      asset_id: "asset:player:ja-morant",
      lane_id: "lane:main:1",
      start_date: "2019-06-20",
      end_date: "2026-01-01",
      occupancy_kind: "main_roster",
      source_state_id: "daily-roster-state:2019-06-20",
    },
    {
      interval_id: "interval:pick:phx:1",
      asset_id: "asset:pick:2028:r1:phx",
      lane_id: "lane:pick:2028:r1:phx",
      start_date: "2025-02-06",
      end_date: "2026-01-01",
      occupancy_kind: "pick_owned",
      source_snapshot_id: "snapshot:2025-02-06",
      source_obligation_id: "obligation:incoming:2028:phx",
    },
  ],
  event_nodes: [
    {
      node_id: "node:trade:2025-02-06",
      canonical_event_id: "event:trade:2025-02-06",
      source_group_id: "group:trade:2025-02-06",
      event_type: "trade",
      event_date: "2025-02-06",
      sequence: 1,
      compact_label: "Trade",
      detail_label: "Memphis trade deadline deal",
      summary: {
        sent_asset_ids: ["asset:player:marcus-smart"],
        received_asset_ids: ["asset:pick:2028:r1:phx"],
        sent_label: "Sent Smart",
        received_label: "Received PHX 2028 1st",
      },
      inbound_asset_ids: ["asset:pick:2028:r1:phx"],
      outbound_asset_ids: ["asset:player:marcus-smart"],
    },
  ],
  strand_segments: [
    {
      segment_id: "segment:player:ja:resident",
      asset_id: "asset:player:ja-morant",
      lane_id: "lane:main:1",
      segment_kind: "resident",
      start_date: "2019-06-20",
      end_date: "2025-02-06",
      end_node_id: "node:trade:2025-02-06",
    },
  ],
  event_connectors: [
    {
      connector_id: "connector:pick:incoming",
      node_id: "node:trade:2025-02-06",
      asset_id: "asset:pick:2028:r1:phx",
      connector_kind: "incoming",
      from_lane_id: null,
      to_lane_id: "lane:pick:2028:r1:phx",
      lead_window_days: 4,
      settle_window_days: 8,
    },
  ],
  additive_context: {
    conditional_pick_families: [
      {
        family_id: "family:wsh:2026",
        family_kind: "conditional_pick",
        selection_rule: "One branch resolves at conveyance.",
        exclusivity_status: "unresolved",
        primary_pick_id: "pick:2026:r1:wsh",
        primary_asset_id: "asset:pick:2026:r1:wsh",
        fallback_branches: [
          {
            branch_id: "branch:wsh:2026:r2",
            original_team_code: "WSH",
            round_number: 2,
            trigger_kind: "fallback",
            projectable: false,
            notes: "Fallback branch remains additive only.",
          },
        ],
      },
    ],
    draft_lottery_results: [
      {
        lottery_result_id: "lottery:2025:mem",
        draft_year: 2025,
        lottery_date: "2025-05-12",
        original_team_code: "MEM",
        owner_team_code: "MEM",
        result_pick_slot: 14,
        pick_id: "pick:2025:r1:mem",
        pick_asset_id: "asset:pick:2025:r1:mem",
        draft_selection_id: null,
      },
    ],
  },
} satisfies VisualizationExportV1;

describe("visualization export contract", () => {
  it("encodes the locked schema constants", () => {
    expect(VISUALIZATION_EXPORT_SCHEMA_VERSION).toBe("visualization_export_v1");
    expect(VISUALIZATION_LANE_BANDS).toEqual(["main_roster", "two_way", "temporary_overflow", "pick"]);
    expect(VISUALIZATION_OCCUPANCY_KINDS).toContain("pick_conditional");
    expect(VISUALIZATION_EVENT_TYPES).toEqual(["trade", "draft", "waiver", "signing"]);
    expect(VISUALIZATION_SEGMENT_KINDS).toContain("draft_conversion");
    expect(VISUALIZATION_CONNECTOR_KINDS).toContain("lane_shift");
  });

  it("supports a render-ready export object without browser-derived truth fields", () => {
    expect(SAMPLE_VISUALIZATION_EXPORT.lanes).toHaveLength(2);
    expect(SAMPLE_VISUALIZATION_EXPORT.assets).toHaveLength(2);
    expect(SAMPLE_VISUALIZATION_EXPORT.occupancy_intervals).toHaveLength(2);
    expect(SAMPLE_VISUALIZATION_EXPORT.event_nodes[0]?.summary?.received_asset_ids).toEqual([
      "asset:pick:2028:r1:phx",
    ]);
    expect(SAMPLE_VISUALIZATION_EXPORT.event_connectors[0]).toMatchObject({
      connector_kind: "incoming",
      to_lane_id: "lane:pick:2028:r1:phx",
      lead_window_days: 4,
      settle_window_days: 8,
    });
  });

  it("narrows player and pick assets for later frontend consumers", () => {
    const playerAsset = SAMPLE_VISUALIZATION_EXPORT.assets[0];
    const pickAsset = SAMPLE_VISUALIZATION_EXPORT.assets[1];

    expect(isVisualizationPlayerAsset(playerAsset)).toBe(true);
    expect(isVisualizationPickAsset(playerAsset)).toBe(false);
    expect(getVisualizationAssetMarkerLabel(playerAsset)).toBe("Ja Morant");

    expect(isVisualizationPickAsset(pickAsset)).toBe(true);
    expect(isVisualizationPlayerAsset(pickAsset)).toBe(false);
    expect(getVisualizationAssetMarkerLabel(pickAsset)).toBe("2028 R1 PHX");
  });
});
