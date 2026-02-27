from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AssetType(str, Enum):
    PLAYER = "player"
    FULL_ROSTER = "full_roster"
    TWO_WAY = "two_way"
    FUTURE_DRAFT_PICK = "future_draft_pick"


class EventType(str, Enum):
    TRADE = "trade"
    DRAFT_PICK = "draft_pick"
    CONTRACT_SIGNING = "contract_signing"
    EXTENSION = "extension"
    RE_SIGNING = "re_signing"
    CONVERSION = "conversion"
    WAIVER = "waiver"


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    event_key: str
    event_date: str
    event_type: str
    event_label: str
    description: str
    source_id: str
    source_url: str


@dataclass(frozen=True)
class AssetSegment:
    edge_id: str
    asset_id: str
    asset_key: str
    asset_type: str
    subtype: str
    source_node_id: str
    target_node_id: str
    start_date: str
    end_date: str
    is_active_at_end: str
    player_name: str
    contract_expiry_year: str
    average_annual_salary: str
    acquisition_method: str
    original_team: str
    pick_year: str
    pick_number: str
    protections_raw: str
    protections_structured: str
    swap_conditions_raw: str
    swap_conditions_structured: str
    prior_transactions: str


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_name: str
    source_url: str
    retrieved_date: str
    notes: str
