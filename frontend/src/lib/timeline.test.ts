import { describe, expect, it } from "vitest";
import contract from "../data/stage8-sample-contract.json";
import {
  buildTimelineLayout,
  chapterFocus,
  getContractBounds,
  getDefaultUiState,
  nodeIdForEventId,
  serializeTimelineSelection,
  type TimelineContract,
} from "./timeline";

const sampleContract = contract as TimelineContract;

describe("timeline utilities", () => {
  it("derives the full contract bounds from nodes and edges", () => {
    const bounds = getContractBounds(sampleContract);

    expect(bounds.start).toBe("2023-10-01");
    expect(bounds.end).toBe("2024-12-31");
  });

  it("uses chapter focus payload to seed the initial ui state", () => {
    const chapter = sampleContract.editorial?.story_chapters?.[1];
    expect(chapter).toBeDefined();

    const focus = chapterFocus(chapter!, { start: "2023-10-01", end: "2024-12-31" });

    expect(focus.windowStart).toBe("2024-02-08");
    expect(focus.windowEnd).toBe("2024-10-12");
    expect(focus.zoom).toBe(1.3);
    expect(focus.laneGroups).toEqual(["future_picks", "main_roster"]);
  });

  it("builds a timeline layout that preserves same-day ordering and filterable asset kinds", () => {
    const state = getDefaultUiState(sampleContract, null);
    const layout = buildTimelineLayout(sampleContract, state);

    const waiveNode = layout.nodes.find((row) => row.event_id === "event_guard_waive");
    const signNode = layout.nodes.find((row) => row.event_id === "event_guard_sign");
    expect(waiveNode).toBeDefined();
    expect(signNode).toBeDefined();
    expect(waiveNode?.x).toBe(signNode?.x);
    expect((waiveNode?.y ?? 0)).toBeLessThan(signNode?.y ?? 0);

    const pickEdge = layout.edges.find((row) => row.edge_id === "timeline_edge_future_pick");
    const transitionEdge = layout.edges.find((row) => row.edge_id === "timeline_edge_pick_to_player");
    expect(pickEdge?.visible).toBe(true);
    expect(transitionEdge?.visible).toBe(true);

    const playerOnlyLayout = buildTimelineLayout(sampleContract, { ...state, assetKinds: ["player_tenure"] });
    const pickOnlyLayout = buildTimelineLayout(sampleContract, { ...state, assetKinds: ["pick_continuity"] });
    expect(playerOnlyLayout.edges.some((row) => row.edge_type === "pick_line")).toBe(false);
    expect(pickOnlyLayout.edges.some((row) => row.edge_type === "pick_line")).toBe(true);
  });

  it("keeps and clips segments that span the selected date window", () => {
    const state = getDefaultUiState(sampleContract, null);
    const layout = buildTimelineLayout(sampleContract, {
      ...state,
      windowStart: "2023-12-01",
      windowEnd: "2023-12-31",
    });

    const spanningEdge = layout.edges.find((row) => row.edge_id === "timeline_edge_veteran_wing_line");

    expect(spanningEdge).toBeDefined();
    expect(spanningEdge?.visible).toBe(true);
    expect(spanningEdge?.x1).toBeLessThan(spanningEdge?.x2 ?? 0);
  });

  it("resolves chapter focus targets from contract event references", () => {
    expect(nodeIdForEventId(sampleContract, "event_trade_pick")).toBe("timeline_node_event_trade_pick");
    expect(nodeIdForEventId(sampleContract, "event_missing")).toBeNull();
  });

  it("serializes a selection payload for the inspector panel", () => {
    const payload = serializeTimelineSelection({ label: "Guard A", player_id: "player_guard_a" });
    expect(payload).toContain("\"Guard A\"");
    expect(payload).toContain("\"player_guard_a\"");
  });
});
