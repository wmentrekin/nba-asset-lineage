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
  type TimelineContractEdge,
  type TimelineContractNode,
  type TimelineChapterExport,
  type TimelineContract,
  type TimelineGeneratedLayoutContract,
  type TimelineLayoutEvent,
  type TimelineLayoutLabel,
  type TimelineLayoutLaneSegment,
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

function defaultState(contract: TimelineContract = generatedContract) {
  return getDefaultUiState(contract, null);
}

function defaultLayout(contract: TimelineContract = generatedContract) {
  return buildTimelineLayout(contract, defaultState(contract));
}

function makeFixtureEdge({
  edgeId,
  assetId,
  label,
  startDate,
  endDate,
  laneGroup = "main_roster",
  edgeType = "continuity",
  playerId,
  assetKind = laneGroup === "future_picks" ? "pick_continuity" : "player_tenure",
}: {
  edgeId: string;
  assetId: string;
  label: string;
  startDate: string;
  endDate: string;
  laneGroup?: string;
  edgeType?: string;
  playerId?: string;
  assetKind?: string;
}): TimelineContractEdge {
  return {
    edge_id: edgeId,
    asset_id: assetId,
    source_node_id: `${edgeId}:source`,
    target_node_id: `${edgeId}:target`,
    start_date: startDate,
    end_date: endDate,
    edge_type: edgeType,
    lane_group: laneGroup,
    lane_index: 0,
    payload: {
      asset_kind: assetKind,
      label,
      player_id: playerId ?? null,
      player_name: assetKind === "player_tenure" ? label : null,
    },
    created_at: "2026-01-01T00:00:00Z",
  };
}

function makeFixtureSegment({
  segmentId,
  assetId,
  label,
  startDate,
  endDate,
  laneGroup = "main_roster",
  bandSlot = 0,
  markerVariant = "text_only",
}: {
  segmentId: string;
  assetId: string;
  label: string;
  startDate: string;
  endDate: string;
  laneGroup?: string;
  bandSlot?: number;
  markerVariant?: "headshot_text" | "text_only";
}): TimelineLayoutLaneSegment {
  return {
    segment_id: segmentId,
    asset_id: assetId,
    lane_group: laneGroup,
    date_start: startDate,
    date_end: endDate,
    display_rank: bandSlot,
    band_slot: bandSlot,
    compaction_group: null,
    continuity_anchor: `${assetId}:anchor`,
    entry_slot: bandSlot,
    exit_slot: bandSlot,
    identity_marker: {
      image_path: null,
      label_text: label,
      marker_variant: markerVariant,
    },
  };
}

function makeFixtureLabel({
  segmentId,
  assetId,
  startDate,
  endDate,
  inlineLabelAllowed = true,
  fallbackMarkerRequired = false,
  labelPriority = 1,
}: {
  segmentId: string;
  assetId: string;
  startDate: string;
  endDate: string;
  inlineLabelAllowed?: boolean;
  fallbackMarkerRequired?: boolean;
  labelPriority?: number;
}): TimelineLayoutLabel {
  return {
    segment_id: segmentId,
    asset_id: assetId,
    date_start: startDate,
    date_end: endDate,
    inline_label_allowed: inlineLabelAllowed,
    label_priority: labelPriority,
    fallback_marker_required: fallbackMarkerRequired,
    marker_side: "left",
  };
}

function makeFixtureNode(eventId: string, eventDate: string, label = eventId): TimelineContractNode {
  return {
    node_id: `${eventId}:node`,
    event_id: eventId,
    event_date: eventDate,
    event_order: 1,
    node_type: "transaction",
    label,
    payload: {},
    created_at: "2026-01-01T00:00:00Z",
  };
}

function buildFixtureContract({
  startDate = "2020-01-01",
  endDate = "2020-12-31",
  defaultDayWidth = 2,
  nodes = [],
  edges,
  laneLayout,
  labelLayout,
  eventLayout = [],
}: {
  startDate?: string;
  endDate?: string;
  defaultDayWidth?: number;
  nodes?: TimelineContractNode[];
  edges: TimelineContractEdge[];
  laneLayout: TimelineLayoutLaneSegment[];
  labelLayout: TimelineLayoutLabel[];
  eventLayout?: TimelineLayoutEvent[];
}): TimelineContract {
  return buildTimelineContract(
    {
      nodes,
      edges,
      lanes: [],
      meta: {},
    },
    {
      layout_meta: {
        start_date: startDate,
        end_date: endDate,
        default_window_start: startDate,
        default_window_end: endDate,
        default_day_width: defaultDayWidth,
        axis_strategy: {
          minor_tick_unit: "month",
          major_tick_unit: "season_boundary",
          season_boundary_rule: "july_1",
        },
        minimap_segments: [],
      },
      lane_layout: laneLayout,
      label_layout: labelLayout,
      event_layout: eventLayout,
      chapter_layout: [],
    },
    [],
  );
}

describe("timeline utilities", () => {
  it("uses full contract bounds for the v2 default scene and compatibility viewport metrics", () => {
    const bounds = getContractBounds(generatedContract);
    const state = normalizeTimelineUiState(generatedContract, defaultState());
    const viewport = getTimelineViewportMetrics(generatedContract, state);
    const scene = buildTimelineScenePrimitives(generatedContract, state);

    expect(bounds).toEqual({
      start: "2016-01-07",
      end: "2026-04-21",
    });
    expect(state.windowStart).toBe(bounds.start);
    expect(state.windowEnd).toBe(bounds.end);
    expect(viewport.defaultWindowStart).toBe(bounds.start);
    expect(viewport.defaultWindowEnd).toBe(bounds.end);
    expect(viewport.windowStart).toBe(bounds.start);
    expect(viewport.windowEnd).toBe(bounds.end);
    expect(viewport.minWindowDays).toBe(viewport.defaultWindowDays);
    expect(viewport.maxWindowDays).toBe(viewport.defaultWindowDays);
    expect(viewport.minZoom).toBe(1);
    expect(viewport.maxZoom).toBe(1);
    expect(scene.chronology.dayWidth).toBeLessThan(
      (generatedContract.layout as TimelineGeneratedLayoutContract).layout_meta.default_day_width,
    );
    expect(viewport.viewportWidth).toBeLessThan(7000);
  });

  it("builds the same chronology and band surface regardless of compatibility window, zoom, and asset-kind state", () => {
    const baselineScene = buildTimelineScenePrimitives(generatedContract, defaultState());
    const variedScene = buildTimelineScenePrimitives(generatedContract, {
      ...defaultState(),
      windowStart: "2024-02-08",
      windowEnd: "2024-02-20",
      zoom: 6,
      assetKinds: ["player_tenure"],
      selectedChapterId: "chapter_deadline_reset",
    });

    expect(variedScene.chronology.windowStart).toBe(baselineScene.chronology.windowStart);
    expect(variedScene.chronology.windowEnd).toBe(baselineScene.chronology.windowEnd);
    expect(variedScene.chronology.axisStrategy).toEqual(baselineScene.chronology.axisStrategy);
    expect(variedScene.chronology.ticks).toHaveLength(baselineScene.chronology.ticks.length);
    expect(variedScene.bands.map((band) => [band.lane_group, band.visible])).toEqual(
      baselineScene.bands.map((band) => [band.lane_group, band.visible]),
    );
    expect(variedScene.activeFocus?.story_chapter_id).toBe("chapter_deadline_reset");
  });

  it("keeps editorial chapter title, body, and dates additive instead of sourcing scene windows from chapter_layout", () => {
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
    const scene = buildTimelineScenePrimitives(contract, defaultState(contract));

    expect(scene.chapters[0]).toMatchObject({
      title: "Visible chapter title",
      body: "Visible chapter body.",
      windowStart: "1999-01-01",
      windowEnd: "1999-12-31",
      minimapAnchorId: "layout_minimap_segment_cd9fbb9b2c49718691e39207",
    });
  });

  it("tolerates missing chapter minimap anchors as compatibility residue while still building the scene", () => {
    const layout = cloneJson(layoutContract) as unknown as TimelineGeneratedLayoutContract;
    layout.chapter_layout[0]!.minimap_anchor_id = "missing-anchor";

    const contract = buildTimelineContract(
      cloneJson(presentationContract) as unknown as TimelinePresentationContract,
      layout,
      cloneJson(editorialChapters) as unknown as TimelineChapterExport[],
    );
    const scene = buildTimelineScenePrimitives(
      contract,
      activateTimelineChapter(contract, defaultState(contract), "chapter_deadline_reset"),
    );

    expect(scene.activeFocus).toMatchObject({
      story_chapter_id: "chapter_deadline_reset",
      minimapAnchorId: "missing-anchor",
      anchorX: null,
    });
    expect(scene.chronology.windowStart).toBe(getContractBounds(contract).start);
    expect(scene.chronology.windowEnd).toBe(getContractBounds(contract).end);
  });

  it("keeps chapter and minimap helpers as selection-only compatibility paths that do not change chronology", () => {
    const bounds = getContractBounds(generatedContract);
    const chapterState = activateTimelineChapter(generatedContract, defaultState(), "chapter_deadline_reset");
    const chapterScene = buildTimelineScenePrimitives(generatedContract, chapterState);
    const linkedJump = jumpTimelineToMinimapSegment(
      generatedContract,
      defaultState(),
      "layout_minimap_segment_cd9fbb9b2c49718691e39207",
    );
    const linkedScene = buildTimelineScenePrimitives(generatedContract, linkedJump);
    const missingJump = jumpTimelineToMinimapSegment(generatedContract, linkedJump, "missing-segment");

    expect(chapterState.windowStart).toBe(bounds.start);
    expect(chapterState.windowEnd).toBe(bounds.end);
    expect(chapterScene.activeFocus?.story_chapter_id).toBe("chapter_deadline_reset");
    expect(linkedScene.activeFocus?.story_chapter_id).toBe("chapter_deadline_reset");
    expect(
      linkedScene.chronology.minimapSegments.find(
        (segment) => segment.segment_id === "layout_minimap_segment_cd9fbb9b2c49718691e39207",
      ),
    ).toMatchObject({ active: true });
    expect(missingJump.selectedChapterId).toBeNull();
    expect(missingJump.windowStart).toBe(bounds.start);
    expect(missingJump.windowEnd).toBe(bounds.end);
  });

  it("treats viewport window, zoom, and shift helpers as no-op compatibility shims for the v2 render path", () => {
    const baselineState = normalizeTimelineUiState(generatedContract, defaultState());
    const windowedState = setTimelineViewportWindow(generatedContract, baselineState, "2017-05-15", "2017-08-15");
    const zoomedState = setTimelineZoomLevel(generatedContract, windowedState, 6);
    const shiftedState = shiftTimelineViewport(generatedContract, zoomedState, 45);
    const baselineLayout = buildTimelineLayout(generatedContract, baselineState);
    const shiftedLayout = buildTimelineLayout(generatedContract, shiftedState);

    expect(windowedState.windowStart).toBe(baselineState.windowStart);
    expect(windowedState.windowEnd).toBe(baselineState.windowEnd);
    expect(zoomedState.zoom).toBe(1);
    expect(shiftedState.windowStart).toBe(baselineState.windowStart);
    expect(shiftedState.windowEnd).toBe(baselineState.windowEnd);
    expect(shiftedLayout.width).toBe(baselineLayout.width);
    expect(shiftedLayout.edges).toHaveLength(baselineLayout.edges.length);
    expect(shiftedLayout.nodes).toHaveLength(baselineLayout.nodes.length);
    expect(shiftedLayout.junctions).toHaveLength(baselineLayout.junctions.length);
  });

  it("loads the generated artifacts without missing asset, event, or chapter references", () => {
    expect(generatedContract.nodes.length).toBeGreaterThan(0);
    expect(generatedContract.edges.length).toBeGreaterThan(0);
    expect(generatedContract.layout?.lane_layout.length).toBe(generatedContract.edges.length);
    expect(generatedContract.layout?.chapter_layout).toHaveLength(editorialChapters.length);
  });

  it("consumes only story_chapters from the editorial export in this phase", () => {
    const layout = defaultLayout();

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

  it("exposes all layout bands even when compatibility asset-kind state narrows", () => {
    const fullScene = buildTimelineScenePrimitives(generatedContract, defaultState());
    const playerOnlyScene = buildTimelineScenePrimitives(generatedContract, {
      ...defaultState(),
      assetKinds: ["player_tenure"],
    });

    expect(fullScene.bands.map((band) => band.lane_group)).toEqual(["main_roster", "future_picks"]);
    expect(fullScene.bands.find((band) => band.lane_group === "main_roster")?.visible).toBe(true);
    expect(fullScene.bands.find((band) => band.lane_group === "future_picks")?.visible).toBe(true);
    expect(playerOnlyScene.bands.find((band) => band.lane_group === "future_picks")?.visible).toBe(true);
  });

  it("builds chronology ticks and minimap residue from the full timeline bounds", () => {
    const scene = buildTimelineScenePrimitives(generatedContract, defaultState());
    const firstSegment = scene.chronology.minimapSegments[0];

    expect(scene.chronology.windowStart).toBe("2016-01-07");
    expect(scene.chronology.windowEnd).toBe("2026-04-21");
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
    expect(scene.chronology.minimapSegments).toHaveLength(
      (layoutContract as unknown as TimelineGeneratedLayoutContract).layout_meta.minimap_segments.length,
    );
    expect(firstSegment).toMatchObject({
      segment_id: "layout_minimap_segment_a8ce946856fff0e8b4904396",
      start_date: "2016-01-07",
      end_date: "2016-07-05",
      label: "Jan 2016 - Jul 2016",
      active: false,
    });
    expect(firstSegment.x1).toBe(160);
    expect(firstSegment.anchorX).toBeGreaterThan(firstSegment.x1);
    expect(firstSegment.x2).toBeGreaterThan(firstSegment.anchorX);
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
    const fullLayout = buildTimelineLayout(contract, defaultState(contract));
    const firstLayout = fullLayout.edges.find((row) => row.edge_id === firstEdge.edge_id);
    const secondLayout = fullLayout.edges.find((row) => row.edge_id === secondEdge.edge_id);

    expect(firstLayout?.asset_id).toBe(firstEdge.asset_id);
    expect(secondLayout?.asset_id).toBe(secondEdge.asset_id);
    expect(firstLayout?.asset_id).not.toBe(secondLayout?.asset_id);
    expect(firstLayout?.y1).not.toBe(secondLayout?.y1);
  });

  it("renders Memphis draft continuity links and pick-to-player conversion from layout transition links", () => {
    const draftCluster = generatedContract.layout?.event_layout.find((row) =>
      row.junction_type === "draft_transition" &&
      row.transition_links.some((link) => link.link_type === "same_asset") &&
      row.transition_links.some((link) => link.link_type === "pick_to_player")
    );

    expect(draftCluster).toBeDefined();

    const layout = defaultLayout();
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

    const layout = defaultLayout();
    const junction = layout.junctions.find((row) => row.cluster_id === tradeCluster!.cluster_id);

    expect(junction).toBeDefined();
    expect(junction?.stems.filter((row) => row.direction === "outgoing")).toHaveLength(4);
    expect(junction?.spineY2).toBeGreaterThan(junction?.spineY1 ?? 0);
    expect(new Set(junction?.stems.map((row) => row.segment_id)).size).toBe(4);
  });

  it("renders the full chronology instead of clipping nodes and junctions to a bounded viewport", () => {
    const layout = defaultLayout();
    const markup = renderTimelineScene(layout);
    const renderedNodeCount = (markup.match(/data-node-id=/g) ?? []).length;
    const renderedJunctionCount = (markup.match(/timeline-junction--/g) ?? []).length;

    expect(layout.nodes).toHaveLength(generatedContract.nodes.length);
    expect(layout.junctions).toHaveLength(generatedContract.layout?.event_layout.length ?? 0);
    expect(renderedNodeCount).toBe(layout.nodes.length);
    expect(renderedJunctionCount).toBe(layout.junctions.length);
    expect(markup).not.toContain("is-hidden");
  });

  it("keeps same-day grouped Memphis events separate while sharing one chronology position", () => {
    const groupedDate = "2016-03-12";
    const layout = defaultLayout();
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

    const layout = buildTimelineLayout(contract, defaultState(contract));
    const markup = renderTimelineScene(layout);

    expect(layout.scene.bands.map((row) => row.lane_group)).toEqual(["main_roster", "two_way", "future_picks"]);
    expect(markup).toContain("timeline-band--main_roster");
    expect(markup).toContain("timeline-band--two_way");
    expect(markup).toContain("timeline-band--future_picks");
  });

  it("renders inline strand labels when the layout hint allows them and the full visible span is long enough", () => {
    const layout = defaultLayout();
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

  it("preserves the left identity marker when a segment can fit the marker but not the full inline label", () => {
    const edge = makeFixtureEdge({
      edgeId: "segment_marker_only",
      assetId: "asset_marker_only",
      label: "Marker Return Player",
      startDate: "2020-01-01",
      endDate: "2020-03-31",
      playerId: "player_marker_only",
    });
    const contract = buildFixtureContract({
      edges: [edge],
      laneLayout: [
        makeFixtureSegment({
          segmentId: edge.edge_id,
          assetId: edge.asset_id,
          label: "Marker Return Player",
          startDate: edge.start_date,
          endDate: edge.end_date,
        }),
      ],
      labelLayout: [
        makeFixtureLabel({
          segmentId: edge.edge_id,
          assetId: edge.asset_id,
          startDate: edge.start_date,
          endDate: edge.end_date,
          inlineLabelAllowed: true,
          fallbackMarkerRequired: true,
        }),
      ],
    });

    const layout = buildTimelineLayout(contract, defaultState(contract));
    const inlineLabel = layout.inlineLabels.find((row) => row.segment_id === edge.edge_id);
    const identityMarker = layout.identityMarkers.find((row) => row.segment_id === edge.edge_id);
    const edgeLayout = layout.edges.find((row) => row.edge_id === edge.edge_id);

    expect(inlineLabel).toMatchObject({ visible: false });
    expect(identityMarker).toMatchObject({ visible: true, markerSide: "left" });
    expect((identityMarker?.x ?? 0) + (identityMarker?.width ?? 0)).toBeLessThanOrEqual(edgeLayout?.x2 ?? 0);
  });

  it("keeps leave-and-return chapters asset-scoped instead of inventing false cross-gap continuity", () => {
    const firstEdge = makeFixtureEdge({
      edgeId: "segment_leave",
      assetId: "asset_leave",
      label: "Reggie Return",
      startDate: "2020-01-01",
      endDate: "2020-04-30",
      playerId: "player_reggie",
    });
    const secondEdge = makeFixtureEdge({
      edgeId: "segment_return",
      assetId: "asset_return",
      label: "Reggie Return",
      startDate: "2020-08-01",
      endDate: "2020-12-31",
      playerId: "player_reggie",
    });
    const contract = buildFixtureContract({
      edges: [firstEdge, secondEdge],
      laneLayout: [
        makeFixtureSegment({
          segmentId: firstEdge.edge_id,
          assetId: firstEdge.asset_id,
          label: "Reggie Return",
          startDate: firstEdge.start_date,
          endDate: firstEdge.end_date,
          bandSlot: 0,
        }),
        makeFixtureSegment({
          segmentId: secondEdge.edge_id,
          assetId: secondEdge.asset_id,
          label: "Reggie Return",
          startDate: secondEdge.start_date,
          endDate: secondEdge.end_date,
          bandSlot: 1,
        }),
      ],
      labelLayout: [
        makeFixtureLabel({
          segmentId: firstEdge.edge_id,
          assetId: firstEdge.asset_id,
          startDate: firstEdge.start_date,
          endDate: firstEdge.end_date,
        }),
        makeFixtureLabel({
          segmentId: secondEdge.edge_id,
          assetId: secondEdge.asset_id,
          startDate: secondEdge.start_date,
          endDate: secondEdge.end_date,
          labelPriority: 2,
        }),
      ],
    });

    const layout = buildTimelineLayout(contract, defaultState(contract));
    const visibleLabels = layout.inlineLabels.filter((row) => row.visible && row.label === "Reggie Return");
    const [leaveLabel, returnLabel] = visibleLabels;

    expect(visibleLabels).toHaveLength(2);
    expect(leaveLabel?.asset_id).toBe("asset_leave");
    expect(returnLabel?.asset_id).toBe("asset_return");
    expect(leaveLabel?.asset_id).not.toBe(returnLabel?.asset_id);
    expect((leaveLabel?.x ?? 0) + (leaveLabel?.width ?? 0) / 2).toBeLessThan(
      (returnLabel?.x ?? 0) - (returnLabel?.width ?? 0) / 2,
    );
    expect(layout.identityMarkers.filter((row) => row.visible)).toHaveLength(0);
  });

  it("hides reacquired-player labels and markers when the visible treatment would extend beyond the reacquired segment", () => {
    const initialEdge = makeFixtureEdge({
      edgeId: "segment_initial_tenure",
      assetId: "asset_initial_tenure",
      label: "Marcus Return",
      startDate: "2020-01-01",
      endDate: "2020-06-30",
      playerId: "player_marcus",
    });
    const reacquiredEdge = makeFixtureEdge({
      edgeId: "segment_reacquired_tenure",
      assetId: "asset_reacquired_tenure",
      label: "Marcus Return Marker",
      startDate: "2020-09-01",
      endDate: "2020-09-20",
      playerId: "player_marcus",
    });
    const contract = buildFixtureContract({
      edges: [initialEdge, reacquiredEdge],
      laneLayout: [
        makeFixtureSegment({
          segmentId: initialEdge.edge_id,
          assetId: initialEdge.asset_id,
          label: "Marcus Return",
          startDate: initialEdge.start_date,
          endDate: initialEdge.end_date,
          bandSlot: 0,
        }),
        makeFixtureSegment({
          segmentId: reacquiredEdge.edge_id,
          assetId: reacquiredEdge.asset_id,
          label: "Marcus Return Marker",
          startDate: reacquiredEdge.start_date,
          endDate: reacquiredEdge.end_date,
          bandSlot: 1,
        }),
      ],
      labelLayout: [
        makeFixtureLabel({
          segmentId: initialEdge.edge_id,
          assetId: initialEdge.asset_id,
          startDate: initialEdge.start_date,
          endDate: initialEdge.end_date,
        }),
        makeFixtureLabel({
          segmentId: reacquiredEdge.edge_id,
          assetId: reacquiredEdge.asset_id,
          startDate: reacquiredEdge.start_date,
          endDate: reacquiredEdge.end_date,
          fallbackMarkerRequired: true,
          labelPriority: 2,
        }),
      ],
    });

    const layout = buildTimelineLayout(contract, defaultState(contract));
    const initialLabel = layout.inlineLabels.find((row) => row.segment_id === initialEdge.edge_id);
    const reacquiredLabel = layout.inlineLabels.find((row) => row.segment_id === reacquiredEdge.edge_id);
    const reacquiredMarker = layout.identityMarkers.find((row) => row.segment_id === reacquiredEdge.edge_id);
    const reacquiredEdgeLayout = layout.edges.find((row) => row.edge_id === reacquiredEdge.edge_id);

    expect(initialLabel).toMatchObject({ visible: true });
    expect(reacquiredLabel).toMatchObject({ visible: false, asset_id: "asset_reacquired_tenure" });
    expect(reacquiredMarker).toMatchObject({ visible: false, asset_id: "asset_reacquired_tenure" });
    expect((reacquiredMarker?.x ?? 0) + (reacquiredMarker?.width ?? 0)).toBeGreaterThan(reacquiredEdgeLayout?.x2 ?? 0);
  });

  it("shifts pick-to-player identity treatment only at the generated transition boundary", () => {
    const pickEdge = makeFixtureEdge({
      edgeId: "segment_pick_asset",
      assetId: "asset_pick_asset",
      label: "2024 MEM 1st",
      startDate: "2020-01-01",
      endDate: "2020-06-20",
      laneGroup: "future_picks",
      edgeType: "pick_line",
      assetKind: "pick_continuity",
    });
    const playerEdge = makeFixtureEdge({
      edgeId: "segment_player_asset",
      assetId: "asset_player_asset",
      label: "Rookie Example",
      startDate: "2020-06-21",
      endDate: "2020-12-31",
      laneGroup: "main_roster",
      playerId: "player_rookie",
    });
    const draftEventId = "event_draft_transition";
    const contract = buildFixtureContract({
      nodes: [makeFixtureNode(draftEventId, "2020-06-21", "Draft night")],
      edges: [pickEdge, playerEdge],
      laneLayout: [
        makeFixtureSegment({
          segmentId: pickEdge.edge_id,
          assetId: pickEdge.asset_id,
          label: "2024 MEM 1st",
          startDate: pickEdge.start_date,
          endDate: pickEdge.end_date,
          laneGroup: "future_picks",
          bandSlot: 0,
        }),
        makeFixtureSegment({
          segmentId: playerEdge.edge_id,
          assetId: playerEdge.asset_id,
          label: "Rookie Example",
          startDate: playerEdge.start_date,
          endDate: playerEdge.end_date,
          laneGroup: "main_roster",
          bandSlot: 0,
        }),
      ],
      labelLayout: [
        makeFixtureLabel({
          segmentId: pickEdge.edge_id,
          assetId: pickEdge.asset_id,
          startDate: pickEdge.start_date,
          endDate: pickEdge.end_date,
        }),
        makeFixtureLabel({
          segmentId: playerEdge.edge_id,
          assetId: playerEdge.asset_id,
          startDate: playerEdge.start_date,
          endDate: playerEdge.end_date,
          labelPriority: 2,
        }),
      ],
      eventLayout: [
        {
          event_id: draftEventId,
          cluster_id: "cluster_draft_transition",
          cluster_date: "2020-06-21",
          cluster_order: 1,
          junction_type: "draft_transition",
          member_event_ids: [draftEventId],
          connected_asset_ids: [pickEdge.asset_id, playerEdge.asset_id],
          incoming_slots: {
            [pickEdge.edge_id]: 0,
          },
          outgoing_slots: {
            [playerEdge.edge_id]: 0,
          },
          transition_anchors: [],
          transition_links: [
            {
              transition_link_id: "transition_pick_to_player",
              source_segment_id: pickEdge.edge_id,
              target_segment_id: playerEdge.edge_id,
              source_asset_id: pickEdge.asset_id,
              target_asset_id: playerEdge.asset_id,
              link_type: "pick_to_player",
            },
          ],
        },
      ],
    });

    const layout = buildTimelineLayout(contract, defaultState(contract));
    const pickLabel = layout.inlineLabels.find((row) => row.segment_id === pickEdge.edge_id);
    const playerLabel = layout.inlineLabels.find((row) => row.segment_id === playerEdge.edge_id);
    const pickEdgeLayout = layout.edges.find((row) => row.edge_id === pickEdge.edge_id);
    const playerEdgeLayout = layout.edges.find((row) => row.edge_id === playerEdge.edge_id);
    const transition = layout.junctions[0]?.transitions.find((row) => row.link_type === "pick_to_player");

    expect(pickLabel).toMatchObject({ visible: true, asset_id: "asset_pick_asset", label: "2024 MEM 1st" });
    expect(playerLabel).toMatchObject({ visible: true, asset_id: "asset_player_asset", label: "Rookie Example" });
    expect((pickLabel?.x ?? 0) + (pickLabel?.width ?? 0) / 2).toBeLessThanOrEqual(pickEdgeLayout?.x2 ?? 0);
    expect((playerLabel?.x ?? 0) - (playerLabel?.width ?? 0) / 2).toBeGreaterThanOrEqual(playerEdgeLayout?.x1 ?? 0);
    expect(pickEdgeLayout?.x2).toBeLessThan(playerEdgeLayout?.x1 ?? 0);
    expect(transition).toMatchObject({ visible: true, source_segment_id: pickEdge.edge_id, target_segment_id: playerEdge.edge_id });
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
    const headshotEdge = contract.edges.find((row) => row.edge_id === headshotCandidate?.segment_id);
    const textOnlyEdge = contract.edges.find((row) => row.edge_id === textOnlyCandidate?.segment_id);

    expect(headshotSegment).toBeDefined();
    expect(textOnlySegment).toBeDefined();
    expect(headshotEdge).toBeDefined();
    expect(textOnlyEdge).toBeDefined();

    if (headshotSegment) {
      headshotSegment.identity_marker.image_path = "headshots/placeholder-headshot.svg";
      headshotSegment.identity_marker.marker_variant = "headshot_text";
      headshotSegment.date_end = "2026-04-21";
    }

    if (textOnlySegment) {
      textOnlySegment.identity_marker.image_path = null;
      textOnlySegment.identity_marker.marker_variant = "headshot_text";
      textOnlySegment.date_end = "2026-04-21";
    }

    if (headshotEdge) {
      headshotEdge.end_date = "2026-04-21";
    }

    if (textOnlyEdge) {
      textOnlyEdge.end_date = "2026-04-21";
    }

    const layout = buildTimelineLayout(contract, defaultState(contract));
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
