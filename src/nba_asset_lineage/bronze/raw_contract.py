from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RawEventRecord:
    source_system: str
    source_event_ref: str
    event_date_raw: str
    event_type_raw: str
    source_url: str
    source_payload: dict[str, Any]


@dataclass(frozen=True)
class RawAssetRecord:
    source_system: str
    source_asset_ref: str
    asset_type_raw: str
    effective_date_raw: str
    source_payload: dict[str, Any]


@dataclass(frozen=True)
class RawEventAssetLinkRecord:
    source_system: str
    source_event_ref: str
    source_asset_ref: str
    action_raw: str
    direction_raw: str
    effective_date_raw: str
    source_payload: dict[str, Any]
