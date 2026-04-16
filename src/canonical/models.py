from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class CanonicalBuild:
    canonical_build_id: str
    built_at: datetime
    builder_version: str
    evidence_build_id: str | None
    override_snapshot_hash: str | None
    notes: str | None

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str
    event_type: str
    event_date: date
    event_order: int
    event_label: str
    description: str | None
    transaction_group_key: str | None
    is_compound: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class EventProvenance:
    event_provenance_id: str
    event_id: str
    source_record_id: str | None
    claim_id: str | None
    override_id: str | None
    provenance_role: str
    fallback_reason: str | None
    created_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalEventBuildResult:
    build: CanonicalBuild
    events: list[CanonicalEvent]
    provenance_rows: list[EventProvenance]

    def counts(self) -> JsonDict:
        return {
            "canonical_build_id": self.build.canonical_build_id,
            "event_count": len(self.events),
            "event_provenance_count": len(self.provenance_rows),
        }
