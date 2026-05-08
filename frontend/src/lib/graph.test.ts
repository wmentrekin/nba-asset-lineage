import { describe, expect, it } from "vitest";

import { buildTimelineLayout, type GraphExport } from "./graph";

const SAMPLE_EXPORT: GraphExport = {
  franchise: "memphis-grizzlies",
  span_start: "2024-01-01",
  span_end: "2024-02-01",
  events: [
    {
      event_id: "evt-1",
      event_type: "trade",
      event_date: "2024-02-08",
      label: "Memphis trade",
      sequence: 1,
      source_group_id: "evt-1",
    },
  ],
  player_assets: [
    {
      asset_id: "asset:player:b",
      player_id: "player:b",
      display_name: "Player B",
      years_experience: 6,
      baseline_order: 1,
      kind: "player",
    },
    {
      asset_id: "asset:player:c",
      player_id: "player:c",
      display_name: "Player C",
      years_experience: 1,
      baseline_order: 3,
      kind: "player",
    },
  ],
  pick_assets: [
    {
      asset_id: "asset:pick:1",
      original_team: "PHX",
      draft_year: 2028,
      round_number: 1,
      protections: null,
      swap_detail: null,
      kind: "pick",
    },
  ],
  transitions: [
    { transition_id: "t1", event_id: "evt-1", asset_id: "asset:player:b", transition_type: "departed" },
    { transition_id: "t2", event_id: "evt-1", asset_id: "asset:pick:1", transition_type: "acquired" },
  ],
  roster_snapshots: [],
};

describe("buildTimelineLayout", () => {
  it("builds rows, event points, connectors, and interval-based segments from export data", () => {
    const layout = buildTimelineLayout(SAMPLE_EXPORT);
    expect(layout.rows.length).toBeGreaterThanOrEqual(18);
    expect(layout.eventPoints).toHaveLength(1);
    expect(layout.connectors).toHaveLength(3);
    expect(layout.segments).toHaveLength(4);
    expect(layout.width).toBeGreaterThan(300);
    expect(layout.height).toBeGreaterThan(100);
    const playerBSegment = layout.segments.find((segment) => segment.assetId === "asset:player:b");
    expect(playerBSegment).toBeTruthy();
    expect(playerBSegment?.x1).toBeLessThan(playerBSegment?.x2 ?? 0);
    expect(layout.playerRowCount).toBe(18);
    const moveConnector = layout.connectors.find((connector) => connector.assetId === "asset:player:c" && connector.direction === "move");
    expect(moveConnector).toBeTruthy();
    expect(moveConnector?.y1).not.toBe(moveConnector?.y2);
    const playerCSegments = layout.segments.filter((segment) => segment.assetId === "asset:player:c");
    expect(playerCSegments).toHaveLength(2);
    expect(playerCSegments[0]?.y).toBeGreaterThan(playerCSegments[1]?.y ?? 0);
  });
});
