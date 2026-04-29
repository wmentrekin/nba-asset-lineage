from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from canonical.models import CanonicalEvent
from presentation.contract import _expected_transition_link_specs
from editorial.models import EditorialOverlayBuildResult
from presentation.models import (
    AssetLane,
    LayoutContractBuildResult,
    PresentationContractBuildResult,
    TimelineEdge,
    TimelineNode,
)


@dataclass(frozen=True)
class PresentationContractValidationReport:
    node_count: int
    edge_count: int
    lane_count: int
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class LayoutContractValidationReport:
    lane_layout_count: int
    event_layout_count: int
    label_layout_count: int
    chapter_layout_count: int
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_presentation_contract(
    *,
    nodes: Iterable[TimelineNode],
    edges: Iterable[TimelineEdge],
    lanes: Iterable[AssetLane],
    canonical_events: Iterable[CanonicalEvent] = (),
) -> PresentationContractValidationReport:
    nodes_list = list(nodes)
    edges_list = list(edges)
    lanes_list = list(lanes)
    canonical_events_list = list(canonical_events)

    errors: list[str] = []
    warnings: list[str] = []

    duplicate_node_ids = [node_id for node_id, count in Counter(row.node_id for row in nodes_list).items() if count > 1]
    if duplicate_node_ids:
        errors.append(f"duplicate node_ids: {', '.join(sorted(duplicate_node_ids))}")

    duplicate_edge_ids = [edge_id for edge_id, count in Counter(row.edge_id for row in edges_list).items() if count > 1]
    if duplicate_edge_ids:
        errors.append(f"duplicate edge_ids: {', '.join(sorted(duplicate_edge_ids))}")

    duplicate_lane_ids = [lane_id for lane_id, count in Counter(row.asset_lane_id for row in lanes_list).items() if count > 1]
    if duplicate_lane_ids:
        errors.append(f"duplicate asset_lane_ids: {', '.join(sorted(duplicate_lane_ids))}")

    node_ids = {row.node_id for row in nodes_list}
    for edge in edges_list:
        if edge.source_node_id not in node_ids:
            errors.append(f"edge references unknown source_node_id: {edge.edge_id}/{edge.source_node_id}")
        if edge.target_node_id not in node_ids:
            errors.append(f"edge references unknown target_node_id: {edge.edge_id}/{edge.target_node_id}")
        if edge.end_date < edge.start_date:
            errors.append(f"edge end_date before start_date: {edge.edge_id}")
        if edge.lane_index < 0:
            errors.append(f"edge has negative lane_index: {edge.edge_id}")
        if edge.edge_type not in {"player_line", "pick_line", "transition_line"}:
            errors.append(f"invalid edge_type for {edge.edge_id}: {edge.edge_type}")
        if edge.lane_group not in {"main_roster", "two_way", "future_picks"}:
            errors.append(f"invalid lane_group for {edge.edge_id}: {edge.lane_group}")

    lane_keys = {
        (row.asset_id, row.lane_group, row.lane_index, row.effective_start_date, row.effective_end_date)
        for row in lanes_list
    }
    for edge in edges_list:
        key = (edge.asset_id, edge.lane_group, edge.lane_index, edge.start_date, edge.end_date)
        if key not in lane_keys:
            errors.append(f"edge has no matching asset lane assignment: {edge.edge_id}")

    lanes_by_index: dict[tuple[str, int], list[AssetLane]] = defaultdict(list)
    for lane in lanes_list:
        lanes_by_index[(lane.lane_group, lane.lane_index)].append(lane)
        if lane.effective_end_date < lane.effective_start_date:
            errors.append(f"lane end before start: {lane.asset_lane_id}")
        if lane.lane_index < 0:
            errors.append(f"lane has negative lane_index: {lane.asset_lane_id}")
        if lane.assignment_method != "deterministic_first_available_interval_v1":
            warnings.append(f"unexpected lane assignment method for {lane.asset_lane_id}: {lane.assignment_method}")

    for (lane_group, lane_index), grouped_lanes in lanes_by_index.items():
        ordered = sorted(grouped_lanes, key=lambda row: (row.effective_start_date, row.effective_end_date, row.asset_id, row.asset_lane_id))
        for left, right in zip(ordered, ordered[1:]):
            if left.effective_end_date > right.effective_start_date:
                errors.append(
                    f"overlapping lane usage for {lane_group}/{lane_index}: {left.asset_lane_id} overlaps {right.asset_lane_id}"
                )

    event_nodes = [row for row in nodes_list if row.event_id is not None]
    ordered_event_nodes = sorted(event_nodes, key=lambda row: (row.event_date, row.event_order, row.event_id or "", row.node_id))
    if event_nodes != ordered_event_nodes:
        errors.append("timeline event nodes are not stored in canonical order")

    if canonical_events_list:
        expected_event_order = [(row.event_id, row.event_date, row.event_order) for row in sorted(canonical_events_list, key=lambda row: (row.event_date, row.event_order, row.event_id))]
        actual_event_order = [(row.event_id, row.event_date, row.event_order) for row in ordered_event_nodes]
        if actual_event_order != expected_event_order:
            errors.append("timeline event node order does not match canonical event order")

    edges_by_asset: dict[str, list[TimelineEdge]] = defaultdict(list)
    for edge in edges_list:
        edges_by_asset[edge.asset_id].append(edge)

    for asset_id, asset_edges in edges_by_asset.items():
        ordered = sorted(asset_edges, key=lambda row: (row.start_date, row.end_date, row.edge_type, row.edge_id))
        for left, right in zip(ordered, ordered[1:]):
            if left.end_date > right.start_date and left.lane_group == right.lane_group:
                errors.append(f"same-asset overlap in lane group for {asset_id}: {left.edge_id} overlaps {right.edge_id}")
        transition_edges = [row for row in ordered if row.edge_type == "transition_line"]
        if transition_edges:
            if not any(row.edge_type == "pick_line" for row in ordered):
                errors.append(f"transition asset has no preceding pick line: {asset_id}")
            for edge in transition_edges:
                if edge.lane_group not in {"main_roster", "two_way"}:
                    errors.append(f"transition edge must use a roster lane group: {edge.edge_id}")
                if not edge.payload.get("drafted_player_id"):
                    errors.append(f"transition edge missing drafted_player_id: {edge.edge_id}")

    return PresentationContractValidationReport(
        node_count=len(nodes_list),
        edge_count=len(edges_list),
        lane_count=len(lanes_list),
        errors=errors,
        warnings=warnings,
    )


def validate_layout_contract(
    *,
    result: LayoutContractBuildResult,
    presentation_result: PresentationContractBuildResult,
    editorial_overlays: EditorialOverlayBuildResult | None = None,
    frontend_public_root: Path | str = Path("frontend/public"),
) -> LayoutContractValidationReport:
    lane_layout = list(result.lane_layout)
    event_layout = list(result.event_layout)
    label_layout = list(result.label_layout)
    chapter_layout = list(result.chapter_layout)
    presentation_edges = list(presentation_result.edges)
    presentation_nodes = [row for row in presentation_result.nodes if row.event_id is not None]
    frontend_public_root_path = Path(frontend_public_root)

    errors: list[str] = []
    warnings: list[str] = []

    if result.layout_meta.default_window_start != result.layout_meta.start_date:
        errors.append("layout_meta.default_window_start must equal layout_meta.start_date")
    if result.layout_meta.default_window_end < result.layout_meta.default_window_start:
        errors.append("layout_meta.default_window_end must be on or after layout_meta.default_window_start")
    if result.layout_meta.default_window_end > result.layout_meta.end_date:
        errors.append("layout_meta.default_window_end must be on or before layout_meta.end_date")
    if result.layout_meta.axis_strategy != {
        "minor_tick_unit": "month",
        "major_tick_unit": "season_boundary",
        "season_boundary_rule": "july_1",
    }:
        errors.append("layout_meta.axis_strategy does not match the frozen contract")
    if not result.layout_meta.minimap_segments:
        errors.append("layout_meta.minimap_segments must not be empty")
    else:
        if result.layout_meta.minimap_segments[0].start_date != result.layout_meta.start_date:
            errors.append("first minimap segment must start at layout_meta.start_date")
        if result.layout_meta.minimap_segments[-1].end_date != result.layout_meta.end_date:
            errors.append("last minimap segment must end at layout_meta.end_date")

    duplicate_segment_ids = [segment_id for segment_id, count in Counter(row.segment_id for row in lane_layout).items() if count > 1]
    if duplicate_segment_ids:
        errors.append(f"duplicate lane_layout segment_ids: {', '.join(sorted(duplicate_segment_ids))}")

    presentation_edge_by_id = {row.edge_id: row for row in presentation_edges}
    lane_by_segment_id = {row.segment_id: row for row in lane_layout}
    for row in lane_layout:
        edge = presentation_edge_by_id.get(row.segment_id)
        if edge is None:
            errors.append(f"lane_layout segment_id is missing from presentation edges: {row.segment_id}")
            continue
        if row.asset_id != edge.asset_id:
            errors.append(f"lane_layout asset_id mismatch for {row.segment_id}")
        if row.lane_group != edge.lane_group:
            errors.append(f"lane_layout lane_group mismatch for {row.segment_id}")
        if row.date_start != edge.start_date or row.date_end != edge.end_date:
            errors.append(f"lane_layout date range mismatch for {row.segment_id}")
        if row.band_slot != edge.lane_index:
            errors.append(f"lane_layout band_slot mismatch for {row.segment_id}")
        if row.entry_slot < 0 or row.exit_slot < 0:
            errors.append(f"lane_layout slot values must be non-negative: {row.segment_id}")
        if row.identity_marker.marker_variant == "headshot_text":
            if row.identity_marker.image_path is None:
                errors.append(f"headshot_text marker requires image_path: {row.segment_id}")
            elif not (frontend_public_root_path / row.identity_marker.image_path).exists():
                errors.append(f"identity_marker.image_path does not exist locally: {row.segment_id}")
        if row.identity_marker.marker_variant == "text_only" and row.identity_marker.image_path is not None:
            errors.append(f"text_only marker must not export image_path: {row.segment_id}")

    expected_segment_ids = {row.edge_id for row in presentation_edges}
    if set(lane_by_segment_id) != expected_segment_ids:
        errors.append("lane_layout segment coverage does not match presentation edges")

    duplicate_label_segments = [segment_id for segment_id, count in Counter(row.segment_id for row in label_layout).items() if count > 1]
    if duplicate_label_segments:
        errors.append(f"duplicate label_layout segment_ids: {', '.join(sorted(duplicate_label_segments))}")
    if {row.segment_id for row in label_layout} != set(lane_by_segment_id):
        errors.append("label_layout segment coverage does not match lane_layout")
    for row in label_layout:
        lane = lane_by_segment_id.get(row.segment_id)
        if lane is None:
            continue
        if row.asset_id != lane.asset_id:
            errors.append(f"label_layout asset_id mismatch for {row.segment_id}")
        if row.marker_side != "left":
            errors.append(f"label_layout marker_side must be left: {row.segment_id}")
        if row.fallback_marker_required == row.inline_label_allowed:
            errors.append(f"label_layout fallback semantics invalid for {row.segment_id}")

    presentation_event_ids = {row.event_id for row in presentation_nodes if row.event_id is not None}
    duplicate_cluster_ids = [cluster_id for cluster_id, count in Counter(row.cluster_id for row in event_layout).items() if count > 1]
    if duplicate_cluster_ids:
        errors.append(f"duplicate event_layout cluster_ids: {', '.join(sorted(duplicate_cluster_ids))}")
    for row in event_layout:
        if row.event_id not in presentation_event_ids:
            errors.append(f"event_layout event_id is missing from presentation contract: {row.event_id}")
        if row.cluster_order <= 0:
            errors.append(f"event_layout cluster_order must be positive: {row.cluster_id}")
        if row.junction_type not in {"transaction", "draft_transition", "state_boundary"}:
            errors.append(f"invalid event_layout junction_type for {row.cluster_id}: {row.junction_type}")
        if not row.member_event_ids:
            errors.append(f"event_layout member_event_ids must not be empty: {row.cluster_id}")
        for event_id in row.member_event_ids:
            if event_id not in presentation_event_ids:
                errors.append(f"event_layout member_event_id missing from presentation contract: {row.cluster_id}/{event_id}")
        for segment_id, slot in row.incoming_slots.items():
            lane = lane_by_segment_id.get(segment_id)
            if lane is None:
                errors.append(f"event_layout incoming slot references missing segment: {row.cluster_id}/{segment_id}")
            elif slot != lane.exit_slot:
                errors.append(f"event_layout incoming slot mismatch for {row.cluster_id}/{segment_id}")
        for segment_id, slot in row.outgoing_slots.items():
            lane = lane_by_segment_id.get(segment_id)
            if lane is None:
                errors.append(f"event_layout outgoing slot references missing segment: {row.cluster_id}/{segment_id}")
            elif slot != lane.entry_slot:
                errors.append(f"event_layout outgoing slot mismatch for {row.cluster_id}/{segment_id}")
        for anchor in row.transition_anchors:
            lane = lane_by_segment_id.get(anchor.segment_id)
            if lane is None:
                errors.append(f"transition_anchor references missing segment: {row.cluster_id}/{anchor.segment_id}")
                continue
            if anchor.asset_id != lane.asset_id:
                errors.append(f"transition_anchor asset mismatch for {row.cluster_id}/{anchor.segment_id}")
            if anchor.anchor_date != row.cluster_date:
                errors.append(f"transition_anchor date mismatch for {row.cluster_id}/{anchor.segment_id}")
        if row.transition_links:
            cluster_source_segments = set(row.incoming_slots)
            cluster_target_segments = set(row.outgoing_slots)
            for link in row.transition_links:
                source_lane = lane_by_segment_id.get(link.source_segment_id)
                target_lane = lane_by_segment_id.get(link.target_segment_id)
                if source_lane is None or target_lane is None:
                    errors.append(f"transition_link references missing segment: {row.cluster_id}/{link.transition_link_id}")
                    continue
                if link.source_asset_id != source_lane.asset_id:
                    errors.append(f"transition_link source asset mismatch: {row.cluster_id}/{link.transition_link_id}")
                if link.target_asset_id != target_lane.asset_id:
                    errors.append(f"transition_link target asset mismatch: {row.cluster_id}/{link.transition_link_id}")
                if link.source_segment_id not in cluster_source_segments:
                    errors.append(f"transition_link source is not incoming to cluster: {row.cluster_id}/{link.transition_link_id}")
                if link.target_segment_id not in cluster_target_segments:
                    errors.append(f"transition_link target is not outgoing from cluster: {row.cluster_id}/{link.transition_link_id}")
                if link.link_type == "same_asset" and link.source_asset_id != link.target_asset_id:
                    errors.append(f"same_asset transition_link must keep asset identity: {row.cluster_id}/{link.transition_link_id}")
                if link.link_type == "pick_to_player" and row.junction_type != "draft_transition":
                    errors.append(f"pick_to_player transition_link requires draft_transition junction: {row.cluster_id}/{link.transition_link_id}")

            expected_links = {
                (source_segment_id, target_segment_id, link_type)
                for source_segment_id, target_segment_id, _, _, link_type in _expected_transition_link_specs(
                    cluster={"junction_type": row.junction_type},
                    incoming_rows=sorted(
                        (lane_by_segment_id[segment_id] for segment_id in row.incoming_slots),
                        key=lambda lane: (lane.band_slot, lane.segment_id),
                    ),
                    outgoing_rows=sorted(
                        (lane_by_segment_id[segment_id] for segment_id in row.outgoing_slots),
                        key=lambda lane: (lane.band_slot, lane.segment_id),
                    ),
                    incoming_edges={
                        segment_id: presentation_edge_by_id[segment_id]
                        for segment_id in row.incoming_slots
                    },
                    outgoing_edges={
                        segment_id: presentation_edge_by_id[segment_id]
                        for segment_id in row.outgoing_slots
                    },
                )
            }
            actual_links = {
                (link.source_segment_id, link.target_segment_id, link.link_type)
                for link in row.transition_links
            }
            missing_links = expected_links - actual_links
            unexpected_links = actual_links - expected_links
            if missing_links:
                errors.append(f"missing transition_link coverage for cluster {row.cluster_id}")
            if unexpected_links:
                errors.append(f"unexpected transition_link coverage for cluster {row.cluster_id}")

    duplicate_chapter_ids = [chapter_id for chapter_id, count in Counter(row.story_chapter_id for row in chapter_layout).items() if count > 1]
    if duplicate_chapter_ids:
        errors.append(f"duplicate chapter_layout story_chapter_ids: {', '.join(sorted(duplicate_chapter_ids))}")
    minimap_segment_ids = {row.segment_id for row in result.layout_meta.minimap_segments}
    for row in chapter_layout:
        if row.window_end < row.window_start:
            errors.append(f"chapter_layout window_end before window_start: {row.story_chapter_id}")
        if row.window_start < result.layout_meta.start_date or row.window_end > result.layout_meta.end_date:
            errors.append(f"chapter_layout window is outside layout bounds: {row.story_chapter_id}")
        if row.minimap_anchor_id not in minimap_segment_ids:
            errors.append(f"chapter_layout minimap_anchor_id is unknown: {row.story_chapter_id}")
        if row.default_zoom is not None and not (30 <= row.default_zoom <= 180):
            errors.append(f"chapter_layout default_zoom must be between 30 and 180 days: {row.story_chapter_id}")
        if any(asset_id not in {lane.asset_id for lane in lane_layout} for asset_id in row.highlight_asset_ids):
            errors.append(f"chapter_layout highlight_asset_ids reference unknown assets: {row.story_chapter_id}")
        if any(event_id not in presentation_event_ids for event_id in row.highlight_event_ids):
            errors.append(f"chapter_layout highlight_event_ids reference unknown events: {row.story_chapter_id}")

    if editorial_overlays is not None:
        expected_chapter_ids = {row.story_chapter_id for row in editorial_overlays.story_chapters}
        if {row.story_chapter_id for row in chapter_layout} != expected_chapter_ids:
            errors.append("chapter_layout story_chapter_ids do not match editorial overlays")

    lane_groups_present = {row.lane_group for row in lane_layout}
    presentation_lane_groups = {row.lane_group for row in presentation_edges}
    if lane_groups_present != presentation_lane_groups:
        errors.append("layout lane_group coverage does not match presentation edges")

    return LayoutContractValidationReport(
        lane_layout_count=len(lane_layout),
        event_layout_count=len(event_layout),
        label_layout_count=len(label_layout),
        chapter_layout_count=len(chapter_layout),
        errors=errors,
        warnings=warnings,
    )
