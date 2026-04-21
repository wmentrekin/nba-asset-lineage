from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class PresentationBuild:
    presentation_build_id: str
    built_at: datetime
    builder_version: str
    canonical_build_id: str | None
    notes: str | None

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class TimelineNode:
    node_id: str
    event_id: str | None
    event_date: date
    event_order: int
    node_type: str
    label: str
    payload: JsonDict
    created_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class TimelineEdge:
    edge_id: str
    asset_id: str
    source_node_id: str
    target_node_id: str
    start_date: date
    end_date: date
    edge_type: str
    lane_group: str
    lane_index: int
    payload: JsonDict
    created_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class AssetLane:
    asset_lane_id: str
    asset_id: str
    lane_group: str
    lane_index: int
    effective_start_date: date
    effective_end_date: date
    assignment_method: str
    created_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class PresentationContractBuildResult:
    build: PresentationBuild
    nodes: list[TimelineNode]
    edges: list[TimelineEdge]
    lanes: list[AssetLane]

    def counts(self) -> JsonDict:
        return {
            "presentation_build_id": self.build.presentation_build_id,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "lane_count": len(self.lanes),
        }

    def as_contract(self) -> JsonDict:
        return {
            "nodes": [row.as_dict() for row in self.nodes],
            "edges": [row.as_dict() for row in self.edges],
            "lanes": [row.as_dict() for row in self.lanes],
            "meta": {
                **self.build.as_dict(),
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "lane_count": len(self.lanes),
            },
        }
