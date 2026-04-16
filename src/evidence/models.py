from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class SourceRecord:
    source_record_id: str
    source_system: str
    source_type: str
    source_locator: str
    source_url: str | None
    captured_at: datetime
    raw_payload: JsonDict
    payload_hash: str
    parser_version: str
    created_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedClaim:
    claim_id: str
    source_record_id: str
    claim_type: str
    claim_subject_type: str
    claim_subject_key: str
    claim_group_hint: str | None
    claim_date: date | None
    source_sequence: int | None
    claim_payload: JsonDict
    confidence_flag: str
    normalizer_version: str
    created_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class OverrideRecord:
    override_id: str
    override_type: str
    target_type: str
    target_key: str
    payload: JsonDict
    reason: str
    authored_by: str
    authored_at: datetime
    is_active: bool

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class OverrideLink:
    override_link_id: str
    override_id: str
    source_record_id: str | None
    claim_id: str | None

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class OverrideBundle:
    overrides: list[OverrideRecord]
    override_links: list[OverrideLink]

    def counts(self) -> JsonDict:
        return {
            "override_count": len(self.overrides),
            "override_link_count": len(self.override_links),
        }
