import { describe, expect, it } from "vitest";

import { buildTimelineLayout, type GraphExport } from "./graph";

function verticalSpan(values: number[]): number {
  if (values.length <= 1) return 0;
  return Math.max(...values) - Math.min(...values);
}

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
    expect(layout.connectors).toHaveLength(5);
    expect(layout.segments).toHaveLength(5);
    expect(layout.dateTicks).toHaveLength(39);
    expect(layout.dateTicks[0]).toMatchObject({ date: "2024-01-01", dayOffset: 0 });
    expect(layout.dateTicks.at(-1)).toMatchObject({ date: "2024-02-08", dayOffset: 38 });
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

  it("keeps incumbent player slots sticky when a higher-priority arrival is acquired", () => {
    const layout = buildTimelineLayout({
      franchise: "memphis-grizzlies",
      span_start: "2024-01-01",
      span_end: "2024-02-01",
      events: [
        {
          event_id: "evt-1",
          event_type: "signing",
          event_date: "2024-02-08",
          label: "Memphis signs Player C",
          sequence: 1,
          source_group_id: "evt-1",
        },
      ],
      player_assets: [
        {
          asset_id: "asset:player:a",
          player_id: "player:a",
          display_name: "Player A",
          years_experience: 10,
          baseline_order: 1,
          kind: "player",
        },
        {
          asset_id: "asset:player:b",
          player_id: "player:b",
          display_name: "Player B",
          years_experience: 2,
          baseline_order: 2,
          kind: "player",
        },
        {
          asset_id: "asset:player:c",
          player_id: "player:c",
          display_name: "Player C",
          years_experience: 12,
          baseline_order: 3,
          kind: "player",
        },
      ],
      pick_assets: [],
      transitions: [{ transition_id: "t1", event_id: "evt-1", asset_id: "asset:player:c", transition_type: "acquired" }],
      roster_snapshots: [],
    });

    const playerASegment = layout.segments.find((segment) => segment.assetId === "asset:player:a");
    const playerBSegment = layout.segments.find((segment) => segment.assetId === "asset:player:b");
    const playerCSegment = layout.segments.find((segment) => segment.assetId === "asset:player:c");

    expect(playerASegment?.y).toBeLessThan(playerBSegment?.y ?? 0);
    expect(playerBSegment?.y).toBeLessThan(playerCSegment?.y ?? 0);
    expect(
      layout.connectors.find((connector) => connector.assetId === "asset:player:b" && connector.direction === "move"),
    ).toBeUndefined();
  });

  it("compacts player slots upward after departures and fills the next open slot for arrivals", () => {
    const layout = buildTimelineLayout({
      franchise: "memphis-grizzlies",
      span_start: "2024-01-01",
      span_end: "2024-03-01",
      events: [
        {
          event_id: "evt-1",
          event_type: "trade",
          event_date: "2024-02-08",
          label: "Memphis trades Player B",
          sequence: 1,
          source_group_id: "evt-1",
        },
        {
          event_id: "evt-2",
          event_type: "signing",
          event_date: "2024-02-10",
          label: "Memphis signs Player D",
          sequence: 2,
          source_group_id: "evt-2",
        },
      ],
      player_assets: [
        {
          asset_id: "asset:player:a",
          player_id: "player:a",
          display_name: "Player A",
          years_experience: 10,
          baseline_order: 1,
          kind: "player",
        },
        {
          asset_id: "asset:player:b",
          player_id: "player:b",
          display_name: "Player B",
          years_experience: 8,
          baseline_order: 2,
          kind: "player",
        },
        {
          asset_id: "asset:player:c",
          player_id: "player:c",
          display_name: "Player C",
          years_experience: 4,
          baseline_order: 3,
          kind: "player",
        },
        {
          asset_id: "asset:player:d",
          player_id: "player:d",
          display_name: "Player D",
          years_experience: 15,
          baseline_order: 4,
          kind: "player",
        },
      ],
      pick_assets: [],
      transitions: [
        { transition_id: "t1", event_id: "evt-1", asset_id: "asset:player:b", transition_type: "departed" },
        { transition_id: "t2", event_id: "evt-2", asset_id: "asset:player:d", transition_type: "acquired" },
      ],
      roster_snapshots: [],
    });

    const playerCMove = layout.connectors.find(
      (connector) => connector.assetId === "asset:player:c" && connector.direction === "move",
    );
    const playerAMove = layout.connectors.find(
      (connector) => connector.assetId === "asset:player:a" && connector.direction === "move",
    );
    const playerASegments = layout.segments.filter((segment) => segment.assetId === "asset:player:a");
    const playerCSegments = layout.segments.filter((segment) => segment.assetId === "asset:player:c");
    const playerDSegment = layout.segments.find((segment) => segment.assetId === "asset:player:d");

    expect(playerCMove).toBeTruthy();
    expect(playerAMove).toBeTruthy();
    expect(playerASegments).toHaveLength(2);
    expect(playerASegments[0]?.y).toBeGreaterThan(playerASegments[1]?.y ?? 0);
    expect(playerCMove?.y1).toBeGreaterThan(playerCMove?.y2 ?? Number.MAX_SAFE_INTEGER);
    expect(playerCSegments).toHaveLength(2);
    expect(playerCSegments[0]?.y).toBeGreaterThan(playerCSegments[1]?.y ?? 0);
    expect(playerASegments[1]?.y).toBeLessThan(playerCSegments[1]?.y ?? 0);
    expect(playerDSegment?.y).toBeGreaterThan(playerCSegments[1]?.y ?? Number.MIN_SAFE_INTEGER);
  });

  it("uses compressed date-based spacing between different event days", () => {
    const layout = buildTimelineLayout({
      franchise: "memphis-grizzlies",
      span_start: "2024-02-01",
      span_end: "2024-02-20",
      events: [
        {
          event_id: "evt-1",
          event_type: "trade",
          event_date: "2024-02-08",
          label: "First trade",
          sequence: 1,
          source_group_id: "evt-1",
        },
        {
          event_id: "evt-2",
          event_type: "trade",
          event_date: "2024-02-10",
          label: "Second trade",
          sequence: 2,
          source_group_id: "evt-2",
        },
      ],
      player_assets: [],
      pick_assets: [],
      transitions: [],
      roster_snapshots: [],
    });

    expect(layout.eventPoints).toHaveLength(2);
    expect(layout.eventPoints[1]!.x - layout.eventPoints[0]!.x).toBe(12);
    expect(layout.dateTicks[0]).toMatchObject({ date: "2024-02-01", dayOffset: 0 });
    expect(layout.dateTicks.at(-1)).toMatchObject({ date: "2024-02-20", dayOffset: 19 });
  });

  it("clusters same-day events around a shared date position instead of giving them full columns", () => {
    const layout = buildTimelineLayout({
      franchise: "memphis-grizzlies",
      span_start: "2024-02-01",
      span_end: "2024-02-20",
      events: [
        {
          event_id: "evt-1",
          event_type: "trade",
          event_date: "2024-02-08",
          label: "Morning trade",
          sequence: 1,
          source_group_id: "evt-1",
        },
        {
          event_id: "evt-2",
          event_type: "waiver",
          event_date: "2024-02-08",
          label: "Afternoon waiver",
          sequence: 2,
          source_group_id: "evt-2",
        },
        {
          event_id: "evt-3",
          event_type: "signing",
          event_date: "2024-02-08",
          label: "Evening signing",
          sequence: 3,
          source_group_id: "evt-3",
        },
      ],
      player_assets: [],
      pick_assets: [],
      transitions: [],
      roster_snapshots: [],
    });

    const xs = layout.eventPoints.map((event) => event.x);
    expect(xs[1]! - xs[0]!).toBe(14);
    expect(xs[2]! - xs[1]!).toBe(14);
    expect(xs[0]! + xs[2]!).toBe(xs[1]! * 2);
    const sharedTick = layout.dateTicks.find((tick) => tick.date === "2024-02-08");
    expect(sharedTick).toBeTruthy();
    expect(sharedTick?.x).toBe(xs[1]);
  });

  it("stages trade participants into compact local clusters near the trade event", () => {
    const layout = buildTimelineLayout({
      franchise: "memphis-grizzlies",
      span_start: "2024-01-01",
      span_end: "2024-03-01",
      events: [
        {
          event_id: "evt-1",
          event_type: "trade",
          event_date: "2024-02-08",
          label: "Memphis consolidates assets",
          sequence: 1,
          source_group_id: "evt-1",
        },
      ],
      player_assets: [
        {
          asset_id: "asset:player:a",
          player_id: "player:a",
          display_name: "Player A",
          years_experience: 11,
          baseline_order: 1,
          kind: "player",
        },
        {
          asset_id: "asset:player:b",
          player_id: "player:b",
          display_name: "Player B",
          years_experience: 10,
          baseline_order: 2,
          kind: "player",
        },
        {
          asset_id: "asset:player:c",
          player_id: "player:c",
          display_name: "Player C",
          years_experience: 9,
          baseline_order: 3,
          kind: "player",
        },
        {
          asset_id: "asset:player:d",
          player_id: "player:d",
          display_name: "Player D",
          years_experience: 8,
          baseline_order: 4,
          kind: "player",
        },
        {
          asset_id: "asset:player:e",
          player_id: "player:e",
          display_name: "Player E",
          years_experience: 7,
          baseline_order: 5,
          kind: "player",
        },
        {
          asset_id: "asset:player:f",
          player_id: "player:f",
          display_name: "Player F",
          years_experience: 6,
          baseline_order: 6,
          kind: "player",
        },
        {
          asset_id: "asset:player:x",
          player_id: "player:x",
          display_name: "Player X",
          years_experience: 3,
          baseline_order: 20,
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
        { transition_id: "t2", event_id: "evt-1", asset_id: "asset:player:f", transition_type: "departed" },
        { transition_id: "t3", event_id: "evt-1", asset_id: "asset:player:x", transition_type: "acquired" },
        { transition_id: "t4", event_id: "evt-1", asset_id: "asset:pick:1", transition_type: "acquired" },
      ],
      roster_snapshots: [],
    });

    const trade = layout.eventPoints[0];
    const outboundIds = ["asset:player:b", "asset:player:f"];
    const inboundIds = ["asset:player:x", "asset:pick:1"];

    const outboundHomeSegments = layout.segments.filter(
      (segment) => outboundIds.includes(segment.assetId) && segment.laneType === "home" && segment.x2 < trade!.x,
    );
    const outboundStageSegments = layout.segments.filter(
      (segment) =>
        outboundIds.includes(segment.assetId) &&
        segment.laneType === "trade-local" &&
        segment.stageSide === "outbound",
    );
    const inboundStageSegments = layout.segments.filter(
      (segment) =>
        inboundIds.includes(segment.assetId) &&
        segment.laneType === "trade-local" &&
        segment.stageSide === "inbound",
    );
    const inboundHomeMoves = layout.connectors.filter(
      (connector) =>
        inboundIds.includes(connector.assetId) &&
        connector.direction === "move" &&
        connector.laneType === "trade-local" &&
        connector.stageSide === "inbound",
    );

    expect(outboundStageSegments).toHaveLength(2);
    expect(inboundStageSegments).toHaveLength(2);
    expect(verticalSpan(outboundStageSegments.map((segment) => segment.y))).toBeLessThan(
      verticalSpan(outboundHomeSegments.map((segment) => segment.y)),
    );
    expect(verticalSpan(inboundStageSegments.map((segment) => segment.y))).toBeLessThan(
      verticalSpan(inboundHomeMoves.map((connector) => connector.y2)),
    );

    const outboundConnectors = layout.connectors.filter(
      (connector) => outboundIds.includes(connector.assetId) && connector.direction === "out",
    );
    const inboundConnectors = layout.connectors.filter(
      (connector) => inboundIds.includes(connector.assetId) && connector.direction === "in",
    );

    expect(
      outboundConnectors.every((connector) =>
        outboundStageSegments.some((segment) => segment.assetId === connector.assetId && segment.y === connector.y1),
      ),
    ).toBe(true);
    expect(
      inboundConnectors.every((connector) =>
        inboundStageSegments.some((segment) => segment.assetId === connector.assetId && segment.y === connector.y2),
      ),
    ).toBe(true);
    expect(
      outboundConnectors.some((connector) =>
        outboundHomeSegments.some((segment) => segment.assetId === connector.assetId && segment.y !== connector.y1),
      ),
    ).toBe(true);
    expect(
      layout.segments.filter((segment) => segment.assetId === "asset:player:a" && segment.laneType === "trade-local"),
    ).toHaveLength(0);
    expect(trade!.maxY - trade!.minY).toBeLessThan(
      verticalSpan([
        ...outboundHomeSegments.map((segment) => segment.y),
        ...inboundHomeMoves.map((connector) => connector.y2),
      ]),
    );
  });
});
