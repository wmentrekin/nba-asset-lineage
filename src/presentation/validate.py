from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

from canonical.models import CanonicalEvent
from presentation.models import AssetLane, TimelineEdge, TimelineNode


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
