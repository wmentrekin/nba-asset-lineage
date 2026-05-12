from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AssetKind = Literal["player", "pick"]
EventType = Literal[
    "trade",
    "draft",
    "waiver",
    "signing",
]
TransitionType = Literal["continuity", "pick_to_player", "acquired", "departed"]


class PlayerAsset(BaseModel):
    asset_id: str
    player_id: str
    display_name: str
    years_experience: int | None = None
    baseline_order: int | None = None
    kind: Literal["player"] = "player"


class PickAsset(BaseModel):
    asset_id: str
    original_team: str
    draft_year: int
    round_number: int
    protections: str | None = None
    swap_detail: str | None = None
    kind: Literal["pick"] = "pick"


class TransactionEvent(BaseModel):
    event_id: str
    event_type: EventType
    event_date: str
    label: str
    sequence: int = 0
    source_group_id: str | None = None


class AssetTransition(BaseModel):
    transition_id: str
    event_id: str
    asset_id: str
    transition_type: TransitionType
    from_state: str | None = None
    to_state: str | None = None
    notes: str | None = None


class RosterSnapshot(BaseModel):
    snapshot_id: str
    as_of_date: str
    roster_asset_ids: list[str] = Field(default_factory=list)
    two_way_asset_ids: list[str] = Field(default_factory=list)
    future_pick_asset_ids: list[str] = Field(default_factory=list)


class BaseGraphExport(BaseModel):
    franchise: str
    span_start: str
    span_end: str
    events: list[TransactionEvent] = Field(default_factory=list)
    player_assets: list[PlayerAsset] = Field(default_factory=list)
    pick_assets: list[PickAsset] = Field(default_factory=list)
    transitions: list[AssetTransition] = Field(default_factory=list)
    roster_snapshots: list[RosterSnapshot] = Field(default_factory=list)
