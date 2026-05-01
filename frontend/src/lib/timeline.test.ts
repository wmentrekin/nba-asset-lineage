import { describe, expect, it } from "vitest";
import presentationContract from "../data/generated/presentation-contract.json";
import layoutContract from "../data/generated/layout-contract.json";
import editorialChapters from "../data/generated/editorial-chapters.json";
import {
  activateTimelineChapter,
  buildTimelineContract,
  buildTimelineLayout,
  buildTimelineScenePrimitives,
  getTimelineViewportMetrics,
  getContractBounds,
  getDefaultUiState,
  jumpTimelineToMinimapSegment,
  normalizeTimelineUiState,
  renderTimelineScene,
  setTimelineViewportWindow,
  setTimelineZoomLevel,
  shiftTimelineViewport,
  type TimelineChapterExport,
  type TimelineContract,
  type TimelineGeneratedLayoutContract,
  type TimelinePresentationContract,
} from "./timeline";

const generatedContract = buildTimelineContract(
  presentationContract as unknown as TimelinePresentationContract,
  layoutContract as unknown as TimelineGeneratedLayoutContract,
  editorialChapters as unknown as TimelineChapterExport[],
);

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function isoPlusDays(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function layoutForWindow(start: string, end: string) {
  return buildTimelineLayout(generatedContract, {
    ...getDefaultUiState(generatedContract, null),
    windowStart: start,
    windowEnd: end,
    assetKinds: ["player_tenure", "pick_continuity"],
  });
}

function layoutForContract(contract: TimelineContract, start: string, end: string) {
  return buildTimelineLayout(contract, {
    ...getDefaultUiState(contract, null),
    windowStart: start,
    windowEnd: end,
    assetKinds: ["player_tenure", "pick_continuity"],
  });
}

describe("timeline utilities", () => {
  it("derives contract bounds and default window from the generated layout artifact", () => {
    const bounds = getContractBounds(generatedContract);
    const state = normalizeTimelineUiState(generatedContract, getDefaultUiState(generatedContract, null));
    const viewport = getTimelineViewportMetrics(generatedContract, state);

    expect(bounds.start).toBe("2016-01-07");
    expect(bounds.end).toBe("2026-04-21");
    expect(state.windowStart).toBe("2016-01-07");
    expect(state.windowEnd).toBe("2016-07-05");
    expect(viewport.defaultWindowDays).toBe(180);
    expect(viewport.minWindowDays).toBe(30);
    expect(viewport.maxWindowDays).toBe(180);
    expect(viewport.minZoom).toBe(1);
    expect(viewport.maxZoom).toBe(6);
  });

  it("builds chapter focus primitives from chapter_layout and preserves minimap linkage", () => {
    const chapter = generatedContract.editorial?.story_chapters?.[0];
    expect(chapter).toBeDefined();

    const scene = buildTimelineScenePrimitives(generatedContract, getDefaultUiState(generatedContract, chapter!));

    expect(scene.activeFocus).toMatchObject({
      story_chapter_id: "chapter_deadline_reset",
      windowStart: "2024-02-08",
      windowEnd: "2025-06-30",
      defaultZoom: null,
      highlightAssetIds: [],
      highlightEventIds: [],
      minimapAnchorId: "layout_minimap_segment_cd9fbb9b2c49718691e39207",
      active: true,
    });
  });

  it("keeps chapter focus windows sourced from chapter_layout even if editorial chapter dates differ", () => {
    const remappedChapters = cloneJson(editorialChapters) as unknown as TimelineChapterExport[];
    remappedChapters[0]!.start_date = "1999-01-01";
    remappedChapters[0]!.end_date = "1999-12-31";

    const contract = buildTimelineContract(
      cloneJson(presentationContract) as unknown as TimelinePresentationContract,
      cloneJson(layoutContract) as unknown as TimelineGeneratedLayoutContract,
      remappedChapters,
    );
    const state = activateTimelineChapter(contract, getDefaultUiState(contract, null), remappedChapters[0]!.story_chapter_id);
    const scene = buildTimelineScenePrimitives(contract, state);

    expect(scene.activeFocus).toMatchObject({
      story_chapter_id: "chapter_deadline_reset",
      windowStart: "2024-02-08",
      windowEnd: "2025-06-30",
      minimapAnchorId: "layout_minimap_segment_cd9fbb9b2c49718691e39207",
      active: true,
    });
  });

  it("keeps editorial chapter title and body additive while layout still owns focus windows and anchors", () => {
    const remappedChapters = cloneJson(editorialChapters) as unknown as TimelineChapterExport[];
    remappedChapters[0]!.title = "Visible chapter title";
    remappedChapters[0]!.body = "Visible chapter body.";
    remappedChapters[0]!.start_date = "1999-01-01";
    remappedChapters[0]!.end_date = "1999-12-31";

    const contract = buildTimelineContract(
      cloneJson(presentationContract) as unknown as TimelinePresentationContract,
      cloneJson(layoutContract) as unknown as TimelineGeneratedLayoutContract,
      remappedChapters,
    );
    const scene = buildTimelineScenePrimitives(contract, getDefaultUiState(contract, null));

    expect(scene.chapters[0]).toMatchObject({
      title: "Visible chapter title",
      body: "Visible chapter body.",
      windowStart: "2024-02-08",
      windowEnd: "2025-06-30",
      minimapAnchorId: "layout_minimap_segment_cd9fbb9b2c49718691e39207",
    });
  });

  it("loads the generated artifacts without missing asset, event, or chapter references", () => {
    expect(generatedContract.nodes.length).toBeGreaterThan(0);
    expect(generatedContract.edges.length).toBeGreaterThan(0);
    expect(generatedContract.layout?.lane_layout.length).toBe(generatedContract.edges.length);
    expect(generatedContract.layout?.chapter_layout).toHaveLength(editorialChapters.length);
  });

  it("consumes only story_chapters from the editorial export in this phase", () => {
    const layout = buildTimelineLayout(generatedContract, getDefaultUiState(generatedContract, null));

    expect(generatedContract.editorial).toEqual({
      story_chapters: expect.any(Array),
    });
    expect(generatedContract.editorial?.story_chapters).toHaveLength(editorialChapters.length);
    expect(generatedContract.editorial?.annotations).toBeUndefined();
    expect(generatedContract.editorial?.calendar_markers).toBeUndefined();
    expect(generatedContract.editorial?.game_overlays).toBeUndefined();
    expect(generatedContract.editorial?.eras).toBeUndefined();
    expect(layout.markers).toEqual([]);
  });

  it("exposes layout-driven band visibility without inventing missing groups", () => {
    const fullScene = buildTimelineScenePrimitives(generatedContract, getDefaultUiState(generatedContract, null));
    const playerOnlyScene = buildTimelineScenePrimitives(generatedContract, {
      ...getDefaultUiState(generatedContract, null),
      assetKinds: ["player_tenure"],
    });

    expect(fullScene.bands.map((band) => band.lane_group)).toEqual(["main_roster", "future_picks"]);
    expect(fullScene.bands.find((band) => band.lane_group === "main_roster")?.visible).toBe(true);
    expect(fullScene.bands.find((band) => band.lane_group === "future_picks")?.visible).toBe(true);
    expect(playerOnlyScene.bands.find((band) => band.lane_group === "future_picks")?.visible).toBe(false);
  });

  it("builds chronology ticks and minimap segments from layout metadata instead of weekly client guesses", () => {
    const scene = buildTimelineScenePrimitives(generatedContract, getDefaultUiState(generatedContract, null));
    const firstSegment = scene.chronology.minimapSegments[0];

    expect(scene.chronology.axisStrategy).toEqual({
      minor_tick_unit: "month",
      major_tick_unit: "season_boundary",
      season_boundary_rule: "july_1",
    });
    expect(scene.chronology.ticks.find((tick) => tick.date === "2016-02-01")).toMatchObject({
      date: "2016-02-01",
      label: "Feb 2016",
      major: false,
      kind: "month",
    });
    expect(scene.chronology.ticks.find((tick) => tick.date === "2016-07-01")).toMatchObject({
      date: "2016-07-01",
      label: "Jul 2016",
      major: true,
      kind: "season_boundary",
    });
    expect(scene.chronology.ticks.some((tick) => tick.date === "2016-01-14")).toBe(false);
    expect(scene.chronology.minimapSegments).toHaveLength(
      (layoutContract as unknown as TimelineGeneratedLayoutContract).layout_meta.minimap_segments.length,
    );
    expect(firstSegment).toMatchObject({
      segment_id: "layout_minimap_segment_a8ce946856fff0e8b4904396",
      start_date: "2016-01-07",
      end_date: "2016-07-05",
      label: "Jan 2016 - Jul 2016",
      active: true,
    });
    expect(firstSegment.x1).toBe(160);
    expect(firstSegment.anchorX).toBeGreaterThan(firstSegment.x1);
    expect(firstSegment.x2).toBeGreaterThan(firstSegment.anchorX);
  });

  it("advances the bounded viewport horizontally without mutating contract truth", () => {
    const baselineState = normalizeTimelineUiState(generatedContract, getDefaultUiState(generatedContract, null));
    const shiftedState = shiftTimelineViewport(generatedContract, baselineState, 45);
    const shiftedViewport = getTimelineViewportMetrics(generatedContract, shiftedState);
    const shiftedLayout = buildTimelineLayout(generatedContract, shiftedState);

    expect(shiftedState.windowStart).toBe(isoPlusDays(baselineState.windowStart, 45));
    expect(shiftedState.windowEnd).toBe(isoPlusDays(baselineState.windowEnd, 45));
    expect(shiftedViewport.windowDays).toBe(180);
    expect(shiftedLayout.width).toBe(1360);
    expect(generatedContract.layout?.layout_meta.default_window_start).toBe("2016-01-07");
    expect(generatedContract.layout?.layout_meta.default_window_end).toBe("2016-07-05");
  });

  it("anchors chapter navigation to the linked minimap segment while preserving the current viewport width when default_zoom is null", () => {
    const baselineState = normalizeTimelineUiState(generatedContract, getDefaultUiState(generatedContract, null));
    const zoomedState = setTimelineZoomLevel(generatedContract, baselineState, 6);
    const chapterState = activateTimelineChapter(generatedContract, zoomedState, "chapter_deadline_reset");
    const viewport = getTimelineViewportMetrics(generatedContract, chapterState);
    const anchorSegment = generatedContract.layout?.layout_meta.minimap_segments.find((segment) =>
      segment.segment_id === "layout_minimap_segment_cd9fbb9b2c49718691e39207"
    );

    expect(anchorSegment).toBeDefined();
    expect(chapterState.selectedChapterId).toBe("chapter_deadline_reset");
    expect(viewport.windowDays).toBe(30);
    expect(chapterState.windowStart).toBe(isoPlusDays(anchorSegment!.anchor_date, -15));
    expect(chapterState.windowEnd).toBe(isoPlusDays(chapterState.windowStart, 30));
  });

  it("uses chapter_layout default_zoom days when a chapter overrides the current viewport width", () => {
    const contract = cloneJson(generatedContract);

    if (contract.layout?.chapter_layout[0]) {
      contract.layout.chapter_layout[0].default_zoom = 60;
    }

    const state = activateTimelineChapter(
      contract,
      setTimelineZoomLevel(contract, getDefaultUiState(contract, null), 6),
      "chapter_deadline_reset",
    );
    const viewport = getTimelineViewportMetrics(contract, state);

    expect(viewport.windowDays).toBe(60);
    expect(state.selectedChapterId).toBe("chapter_deadline_reset");
  });

  it("jumps to minimap segments on the existing viewport model and clears chapter focus when the target segment is not linked", () => {
    const baselineState = setTimelineZoomLevel(generatedContract, getDefaultUiState(generatedContract, null), 6);
    const linkedJump = jumpTimelineToMinimapSegment(
      generatedContract,
      baselineState,
      "layout_minimap_segment_cd9fbb9b2c49718691e39207",
    );
    const linkedViewport = getTimelineViewportMetrics(generatedContract, linkedJump);
    const unlinkedSegment = generatedContract.layout?.layout_meta.minimap_segments.find((segment) =>
      segment.segment_id !== "layout_minimap_segment_cd9fbb9b2c49718691e39207"
    );

    expect(unlinkedSegment).toBeDefined();
    expect(linkedJump.selectedChapterId).toBe("chapter_deadline_reset");
    expect(linkedViewport.windowDays).toBe(30);

    const unlinkedJump = jumpTimelineToMinimapSegment(generatedContract, linkedJump, unlinkedSegment!.segment_id);
    const unlinkedViewport = getTimelineViewportMetrics(generatedContract, unlinkedJump);
    const unlinkedScene = buildTimelineScenePrimitives(generatedContract, unlinkedJump);

    expect(unlinkedJump.selectedChapterId).toBeNull();
    expect(unlinkedViewport.windowDays).toBe(30);
    expect(unlinkedScene.activeFocus).toBeNull();
  });

  it("clamps zoom-driven viewport duration to the frozen 30 to 180 day bounds", () => {
    const baselineState = normalizeTimelineUiState(generatedContract, getDefaultUiState(generatedContract, null));
    const maxZoomState = setTimelineZoomLevel(generatedContract, baselineState, 999);
    const maxZoomViewport = getTimelineViewportMetrics(generatedContract, maxZoomState);
    const maxZoomLayout = buildTimelineLayout(generatedContract, maxZoomState);
    const minZoomState = setTimelineZoomLevel(generatedContract, baselineState, 0.1);
    const minZoomViewport = getTimelineViewportMetrics(generatedContract, minZoomState);

    expect(maxZoomState.zoom).toBe(6);
    expect(maxZoomViewport.windowDays).toBe(30);
    expect(maxZoomState.windowEnd).toBe(isoPlusDays(maxZoomState.windowStart, 30));
    expect(maxZoomLayout.width).toBe(460);
    expect(minZoomState.zoom).toBe(1);
    expect(minZoomViewport.windowDays).toBe(180);
    expect(minZoomState.windowStart).toBe("2016-01-07");
    expect(minZoomState.windowEnd).toBe("2016-07-05");
  });

  it("derives visible monthly and season-boundary ticks from the active layout-driven viewport window", () => {
    const baselineState = normalizeTimelineUiState(generatedContract, getDefaultUiState(generatedContract, null));
    const focusedState = setTimelineViewportWindow(generatedContract, baselineState, "2017-05-15", "2017-08-15");
    const scene = buildTimelineScenePrimitives(generatedContract, focusedState);

    expect(scene.chronology.windowStart).toBe("2017-05-15");
    expect(scene.chronology.windowEnd).toBe("2017-08-15");
    expect(scene.chronology.ticks.map((tick) => tick.date)).toEqual([
      "2017-06-01",
      "2017-07-01",
      "2017-08-01",
    ]);
    expect(scene.chronology.ticks.find((tick) => tick.date === "2017-07-01")).toMatchObject({
      major: true,
      kind: "season_boundary",
      label: "Jul 2017",
    });
    expect(scene.chronology.ticks.find((tick) => tick.date === "2017-06-01")).toMatchObject({
      major: false,
      kind: "month",
      label: "Jun 2017",
    });
  });

  it("preserves asset continuity by asset_id when a player_id appears under multiple assets", () => {
    const presentation = cloneJson(presentationContract) as unknown as TimelinePresentationContract;
    const layout = cloneJson(layoutContract) as unknown as TimelineGeneratedLayoutContract;
    const repeatedEdges = new Map<string, typeof presentation.edges>();

    for (const edge of presentation.edges) {
      const playerId = edge.payload.player_id;
      if (!playerId) {
        continue;
      }
      const rows = repeatedEdges.get(String(playerId)) ?? [];
      rows.push(edge);
      repeatedEdges.set(String(playerId), rows);
    }

    const entry = Array.from(repeatedEdges.values()).find((rows) => {
      const assetIds = new Set(rows.map((row) => row.asset_id));
      return assetIds.size > 1;
    });

    expect(entry).toBeDefined();
    const distinctAssets = Array.from(new Map(entry!.map((row) => [row.asset_id, row])).values()).slice(0, 2);
    expect(distinctAssets).toHaveLength(2);

    const [firstEdge, secondEdge] = distinctAssets;
    const firstLane = layout.lane_layout.find((row) => row.segment_id === firstEdge.edge_id);
    const secondLane = layout.lane_layout.find((row) => row.segment_id === secondEdge.edge_id);

    expect(firstLane).toBeDefined();
    expect(secondLane).toBeDefined();

    firstLane!.band_slot = 1;
    secondLane!.band_slot = 9;

    const contract = buildTimelineContract(
      presentation,
      layout,
      editorialChapters as unknown as TimelineChapterExport[],
    );
    const firstScene = buildTimelineLayout(contract, {
      ...setTimelineViewportWindow(contract, getDefaultUiState(contract, null), firstEdge.start_date, firstEdge.end_date),
      assetKinds: ["player_tenure"],
    });
    const secondScene = buildTimelineLayout(contract, {
      ...setTimelineViewportWindow(contract, getDefaultUiState(contract, null), secondEdge.start_date, secondEdge.end_date),
      assetKinds: ["player_tenure"],
    });

    const firstLayout = firstScene.edges.find((row) => row.edge_id === firstEdge.edge_id);
    const secondLayout = secondScene.edges.find((row) => row.edge_id === secondEdge.edge_id);

    expect(firstLayout?.asset_id).toBe(firstEdge.asset_id);
    expect(secondLayout?.asset_id).toBe(secondEdge.asset_id);
    expect(firstLayout?.asset_id).not.toBe(secondLayout?.asset_id);
    expect(firstLayout?.y1).not.toBe(secondLayout?.y1);
  });

  it("renders Memphis draft continuity links and pick-to-player conversion from layout transition links", () => {
    const bounds = getContractBounds(generatedContract);
    const draftCluster = generatedContract.layout?.event_layout.find((row) =>
      row.junction_type === "draft_transition" &&
      row.transition_links.some((link) => link.link_type === "same_asset") &&
      row.transition_links.some((link) => link.link_type === "pick_to_player")
    );

    expect(draftCluster).toBeDefined();

    const layout = layoutForWindow(bounds.start, bounds.end);
    const junction = layout.junctions.find((row) => row.cluster_id === draftCluster!.cluster_id);

    expect(junction).toBeDefined();
    expect(junction?.visible).toBe(true);

    const sameAsset = junction?.transitions.find((row) => row.link_type === "same_asset");
    const pickToPlayer = junction?.transitions.find((row) => row.link_type === "pick_to_player");

    expect(sameAsset).toBeDefined();
    expect(pickToPlayer).toBeDefined();
    expect(sameAsset?.visible).toBe(true);
    expect(pickToPlayer?.visible).toBe(true);
    expect(pickToPlayer?.y1).not.toBe(pickToPlayer?.y2);
    expect(pickToPlayer?.x1).toBeLessThan(pickToPlayer?.x2 ?? 0);
  });

  it("renders multi-asset same-day Memphis trade clusters as one grouped junction moment", () => {
    const tradeCluster = generatedContract.layout?.event_layout.find((row) =>
      row.junction_type === "transaction" &&
      row.connected_asset_ids.length >= 4 &&
      Object.keys(row.outgoing_slots).length >= 4
    );

    expect(tradeCluster).toBeDefined();

    const state = setTimelineViewportWindow(
      generatedContract,
      getDefaultUiState(generatedContract, null),
      isoPlusDays(tradeCluster!.cluster_date, -15),
      isoPlusDays(tradeCluster!.cluster_date, 45),
    );
    const layout = buildTimelineLayout(generatedContract, state);
    const junction = layout.junctions.find((row) => row.cluster_id === tradeCluster!.cluster_id);

    expect(junction).toBeDefined();
    expect(junction?.stems.filter((row) => row.direction === "outgoing")).toHaveLength(4);
    expect(junction?.spineY2).toBeGreaterThan(junction?.spineY1 ?? 0);
    expect(new Set(junction?.stems.map((row) => row.segment_id)).size).toBe(4);
  });

  it("limits rendered nodes and junctions to the active viewport instead of serializing hidden decade-wide SVG", () => {
    const layout = layoutForWindow("2019-07-01", "2019-08-30");
    const markup = renderTimelineScene(layout);
    const renderedNodeCount = (markup.match(/data-node-id=/g) ?? []).length;
    const renderedJunctionCount = (markup.match(/timeline-junction--/g) ?? []).length;

    expect(layout.nodes.every((row) => row.visible)).toBe(true);
    expect(layout.junctions.every((row) => row.visible)).toBe(true);
    expect(layout.nodes.length).toBeLessThan(generatedContract.nodes.length);
    expect(layout.junctions.length).toBeLessThan(generatedContract.layout?.event_layout.length ?? 0);
    expect(renderedNodeCount).toBe(layout.nodes.length);
    expect(renderedJunctionCount).toBe(layout.junctions.length);
    expect(markup).not.toContain("is-hidden");
  });

  it("keeps same-day grouped Memphis events separate while sharing one chronology position", () => {
    const groupedDate = "2016-03-12";
    const layout = layoutForWindow("2016-03-01", "2016-03-31");
    const junctions = layout.junctions.filter((row) => row.cluster_date === groupedDate);

    expect(junctions).toHaveLength(2);
    expect(junctions[0]?.x).toBe(junctions[1]?.x);
    expect(junctions[0]?.y).not.toBe(junctions[1]?.y);
    expect(junctions.map((row) => row.cluster_order)).toEqual([1, 2]);
  });

  it("renders all three lane-band classes when the layout contract exposes main-roster, two-way, and future-pick rows", () => {
    const contract = cloneJson(generatedContract);
    const playerSegment = contract.layout?.lane_layout.find((row) => row.lane_group === "main_roster");

    expect(playerSegment).toBeDefined();

    if (playerSegment) {
      playerSegment.lane_group = "two_way";
    }

    const layout = buildTimelineLayout(contract, {
      ...getDefaultUiState(contract, null),
      windowStart: "2019-06-01",
      windowEnd: "2019-07-31",
    });
    const markup = renderTimelineScene(layout);

    expect(layout.scene.bands.map((row) => row.lane_group)).toEqual(["main_roster", "two_way", "future_picks"]);
    expect(markup).toContain("timeline-band--main_roster");
    expect(markup).toContain("timeline-band--two_way");
    expect(markup).toContain("timeline-band--future_picks");
  });

  it("renders inline strand labels when the layout hint allows them and the visible span is long enough", () => {
    const bounds = getContractBounds(generatedContract);
    const layout = layoutForWindow(bounds.start, bounds.end);
    const inlineLabel = layout.inlineLabels.find((row) => row.visible);

    expect(inlineLabel).toBeDefined();
    expect(
      generatedContract.layout?.label_layout.find((row) => row.segment_id === inlineLabel?.segment_id),
    ).toMatchObject({
      inline_label_allowed: true,
    });
    expect(
      layout.identityMarkers.find((row) => row.segment_id === inlineLabel?.segment_id && row.visible),
    ).toBeUndefined();
  });

  it("preserves the left identity marker when an inline-capable strand is clipped too tightly to fit its label", () => {
    const contract = cloneJson(generatedContract);
    const candidate = contract.layout?.label_layout.find((row) =>
      row.inline_label_allowed
      && !row.fallback_marker_required
      && row.date_end >= isoPlusDays(row.date_start, 5)
    );

    expect(candidate).toBeDefined();

    if (contract.layout?.layout_meta) {
      contract.layout.layout_meta.default_day_width = 1;
    }

    const zoomedState = setTimelineZoomLevel(
      contract,
      setTimelineViewportWindow(contract, getDefaultUiState(contract, null), candidate!.date_start, candidate!.date_end),
      999,
    );
    const layout = buildTimelineLayout(contract, zoomedState);
    const inlineLabel = layout.inlineLabels.find((row) => row.segment_id === candidate?.segment_id);
    const identityMarker = layout.identityMarkers.find((row) => row.segment_id === candidate?.segment_id);

    expect(inlineLabel).toMatchObject({ visible: false });
    expect(identityMarker).toMatchObject({ visible: true, markerSide: "left" });
  });

  it("supports headshot-plus-text markers when a local image path exists and falls back to text-only otherwise", () => {
    const contract = cloneJson(generatedContract);
    const fallbackLabels = contract.layout?.label_layout.filter((row) => row.fallback_marker_required) ?? [];
    const [headshotCandidate, textOnlyCandidate] = fallbackLabels;

    expect(headshotCandidate).toBeDefined();
    expect(textOnlyCandidate).toBeDefined();
    expect(headshotCandidate?.segment_id).not.toBe(textOnlyCandidate?.segment_id);

    const headshotSegment = contract.layout?.lane_layout.find((row) => row.segment_id === headshotCandidate?.segment_id);
    const textOnlySegment = contract.layout?.lane_layout.find((row) => row.segment_id === textOnlyCandidate?.segment_id);

    expect(headshotSegment).toBeDefined();
    expect(textOnlySegment).toBeDefined();

    if (headshotSegment) {
      headshotSegment.identity_marker.image_path = "headshots/placeholder-headshot.svg";
      headshotSegment.identity_marker.marker_variant = "headshot_text";
    }

    if (textOnlySegment) {
      textOnlySegment.identity_marker.image_path = null;
      textOnlySegment.identity_marker.marker_variant = "headshot_text";
    }

    const bounds = getContractBounds(contract);
    const layout = layoutForContract(contract, bounds.start, bounds.end);
    const markup = renderTimelineScene(layout);
    const headshotMarker = layout.identityMarkers.find((row) => row.segment_id === headshotCandidate?.segment_id);
    const textOnlyMarker = layout.identityMarkers.find((row) => row.segment_id === textOnlyCandidate?.segment_id);

    expect(headshotMarker).toMatchObject({
      visible: true,
      markerVariant: "headshot_text",
      imagePath: "/headshots/placeholder-headshot.svg",
      usesHeadshot: true,
    });
    expect(textOnlyMarker).toMatchObject({
      visible: true,
      markerVariant: "text_only",
      imagePath: null,
      usesHeadshot: false,
    });
    expect(markup).toContain("timeline-identity-marker--headshot_text");
    expect(markup).toContain("timeline-identity-marker--text_only");
    expect(markup).toContain('href="/headshots/placeholder-headshot.svg"');
  });
});
