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


@dataclass(frozen=True)
class CanonicalPlayerIdentity:
    player_id: str
    display_name: str
    normalized_name: str
    nba_person_id: str | None
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class PlayerIdentityProvenance:
    player_identity_provenance_id: str
    player_id: str
    source_record_id: str | None
    claim_id: str | None
    override_id: str | None
    provenance_role: str
    fallback_reason: str | None
    created_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalPlayerTenure:
    player_tenure_id: str
    player_id: str
    tenure_start_date: date
    tenure_end_date: date | None
    entry_event_id: str
    exit_event_id: str | None
    tenure_type: str
    roster_path_type: str | None
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalAsset:
    asset_id: str
    asset_kind: str
    player_tenure_id: str | None
    pick_asset_id: str | None
    asset_label: str
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class AssetProvenance:
    asset_provenance_id: str
    asset_id: str
    player_tenure_id: str | None
    pick_asset_id: str | None
    source_record_id: str | None
    claim_id: str | None
    override_id: str | None
    provenance_role: str
    fallback_reason: str | None
    created_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class AssetState:
    asset_state_id: str
    asset_id: str
    state_type: str
    effective_start_date: date
    effective_end_date: date | None
    state_payload: JsonDict
    source_event_id: str | None
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class AssetStateProvenance:
    asset_state_provenance_id: str
    asset_state_id: str
    source_record_id: str | None
    claim_id: str | None
    override_id: str | None
    provenance_role: str
    fallback_reason: str | None
    created_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalPlayerTenureBuildResult:
    build: CanonicalBuild
    player_identities: list[CanonicalPlayerIdentity]
    player_identity_provenance_rows: list[PlayerIdentityProvenance]
    player_tenures: list[CanonicalPlayerTenure]
    assets: list[CanonicalAsset]
    asset_provenance_rows: list[AssetProvenance]
    asset_states: list[AssetState]
    asset_state_provenance_rows: list[AssetStateProvenance]

    def counts(self) -> JsonDict:
        return {
            "canonical_build_id": self.build.canonical_build_id,
            "player_identity_count": len(self.player_identities),
            "player_identity_provenance_count": len(self.player_identity_provenance_rows),
            "player_tenure_count": len(self.player_tenures),
            "asset_count": len(self.assets),
            "asset_provenance_count": len(self.asset_provenance_rows),
            "asset_state_count": len(self.asset_states),
            "asset_state_provenance_count": len(self.asset_state_provenance_rows),
        }
