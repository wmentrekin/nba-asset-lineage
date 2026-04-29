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


@dataclass(frozen=True)
class LayoutBuild:
    layout_build_id: str
    built_at: datetime
    builder_version: str
    presentation_build_id: str
    editorial_build_id: str | None
    notes: str | None

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class MinimapSegment:
    segment_id: str
    start_date: date
    end_date: date
    anchor_date: date
    label: str

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class LayoutMeta:
    start_date: date
    end_date: date
    default_window_start: date
    default_window_end: date
    default_day_width: float
    axis_strategy: JsonDict
    minimap_segments: list[MinimapSegment]

    def as_dict(self) -> JsonDict:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "default_window_start": self.default_window_start,
            "default_window_end": self.default_window_end,
            "default_day_width": self.default_day_width,
            "axis_strategy": self.axis_strategy,
            "minimap_segments": [row.as_dict() for row in self.minimap_segments],
        }


@dataclass(frozen=True)
class IdentityMarker:
    label_text: str
    image_path: str | None
    marker_variant: str

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class LaneLayoutRow:
    segment_id: str
    asset_id: str
    lane_group: str
    date_start: date
    date_end: date
    display_rank: int
    band_slot: int
    compaction_group: str | None
    continuity_anchor: str
    entry_slot: int
    exit_slot: int
    identity_marker: IdentityMarker

    def as_dict(self) -> JsonDict:
        payload = asdict(self)
        payload["identity_marker"] = self.identity_marker.as_dict()
        return payload


@dataclass(frozen=True)
class TransitionAnchor:
    segment_id: str
    asset_id: str
    anchor_date: date
    from_slot: int
    to_slot: int

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class TransitionLink:
    transition_link_id: str
    source_segment_id: str
    target_segment_id: str
    source_asset_id: str
    target_asset_id: str
    link_type: str

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class EventLayoutRow:
    event_id: str
    cluster_id: str
    cluster_date: date
    cluster_order: int
    junction_type: str
    member_event_ids: list[str]
    connected_asset_ids: list[str]
    incoming_slots: dict[str, int]
    outgoing_slots: dict[str, int]
    transition_anchors: list[TransitionAnchor]
    transition_links: list[TransitionLink]

    def as_dict(self) -> JsonDict:
        return {
            "event_id": self.event_id,
            "cluster_id": self.cluster_id,
            "cluster_date": self.cluster_date,
            "cluster_order": self.cluster_order,
            "junction_type": self.junction_type,
            "member_event_ids": list(self.member_event_ids),
            "connected_asset_ids": list(self.connected_asset_ids),
            "incoming_slots": dict(self.incoming_slots),
            "outgoing_slots": dict(self.outgoing_slots),
            "transition_anchors": [row.as_dict() for row in self.transition_anchors],
            "transition_links": [row.as_dict() for row in self.transition_links],
        }


@dataclass(frozen=True)
class LabelLayoutRow:
    segment_id: str
    asset_id: str
    date_start: date
    date_end: date
    inline_label_allowed: bool
    label_priority: int
    fallback_marker_required: bool
    marker_side: str

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class ChapterLayoutRow:
    story_chapter_id: str
    window_start: date
    window_end: date
    highlight_asset_ids: list[str]
    highlight_event_ids: list[str]
    minimap_anchor_id: str
    default_zoom: int | None

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class LayoutContractBuildResult:
    build: LayoutBuild
    layout_meta: LayoutMeta
    lane_layout: list[LaneLayoutRow]
    event_layout: list[EventLayoutRow]
    label_layout: list[LabelLayoutRow]
    chapter_layout: list[ChapterLayoutRow]

    def counts(self) -> JsonDict:
        return {
            "layout_build_id": self.build.layout_build_id,
            "lane_layout_count": len(self.lane_layout),
            "event_layout_count": len(self.event_layout),
            "label_layout_count": len(self.label_layout),
            "chapter_layout_count": len(self.chapter_layout),
        }

    def as_contract(self) -> JsonDict:
        return {
            "layout_meta": self.layout_meta.as_dict(),
            "lane_layout": [row.as_dict() for row in self.lane_layout],
            "event_layout": [row.as_dict() for row in self.event_layout],
            "label_layout": [row.as_dict() for row in self.label_layout],
            "chapter_layout": [row.as_dict() for row in self.chapter_layout],
        }
