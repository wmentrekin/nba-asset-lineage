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


DRAFT_DATE_BY_YEAR_ROUND = {
    (2016, 1): "2016-06-23",
    (2016, 2): "2016-06-23",
    (2017, 1): "2017-06-22",
    (2017, 2): "2017-06-22",
    (2018, 1): "2018-06-21",
    (2018, 2): "2018-06-21",
    (2019, 1): "2019-06-20",
    (2019, 2): "2019-06-20",
    (2020, 1): "2020-11-18",
    (2020, 2): "2020-11-18",
    (2021, 1): "2021-07-29",
    (2021, 2): "2021-07-29",
    (2022, 1): "2022-06-23",
    (2022, 2): "2022-06-23",
    (2023, 1): "2023-06-22",
    (2023, 2): "2023-06-22",
    (2024, 1): "2024-06-26",
    (2024, 2): "2024-06-27",
    (2025, 1): "2025-06-25",
    (2025, 2): "2025-06-26",
}


def draft_event_date(draft_year: int, round_number: int) -> str:
    event_date = DRAFT_DATE_BY_YEAR_ROUND.get((draft_year, round_number))
    if event_date is None:
        raise ValueError(f"Missing draft event date for draft_year={draft_year}, round_number={round_number}")
    return event_date


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


class FuturePickSnapshot(BaseModel):
    asset_id: str
    pick_id: str
    holding_status: str
    display_order: int | None = None
    source_obligation_id: str | None = None
    confidence: str | None = None
    notes: str | None = None


class RosterSnapshot(BaseModel):
    snapshot_id: str
    as_of_date: str
    snapshot_kind: str | None = None
    season: str | None = None
    roster_asset_ids: list[str] = Field(default_factory=list)
    two_way_asset_ids: list[str] = Field(default_factory=list)
    future_pick_asset_ids: list[str] = Field(default_factory=list)
    future_picks: list[FuturePickSnapshot] = Field(default_factory=list)


class BaseGraphExport(BaseModel):
    franchise: str
    span_start: str
    span_end: str
    events: list[TransactionEvent] = Field(default_factory=list)
    player_assets: list[PlayerAsset] = Field(default_factory=list)
    pick_assets: list[PickAsset] = Field(default_factory=list)
    transitions: list[AssetTransition] = Field(default_factory=list)
    roster_snapshots: list[RosterSnapshot] = Field(default_factory=list)
