from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


FactType = Literal[
    "transaction_chronology",
    "player_movement",
    "roster_snapshot",
    "pick_right_detail",
    "player_identity",
]

ProviderRole = Literal[
    "chronology_spine",
    "structured_player_movement",
    "official_confirmation",
    "roster_snapshot",
    "secondary_pick_detail",
    "identity_roster",
]

SourceSystem = Literal[
    "basketball_reference",
    "nba_player_movement",
    "nba_official",
    "team_official",
    "realgm",
    "nba_stats",
    "curated_fixture",
]

EvidenceState = Literal[
    "recognized_provider",
    "loaded_evidence",
    "supports_event",
    "conflicts_event",
    "missing_required_evidence",
]

CorroborationStatus = Literal[
    "meets_minimum",
    "bref_only",
    "missing_required_evidence",
    "recognized_provider_not_loaded",
    "out_of_scope",
]

ConflictStatus = Literal[
    "not_evaluated",
    "no_conflict_detected",
    "conflict_suspected",
]


FIRST_PASS_FACT_TYPES: tuple[FactType, ...] = (
    "transaction_chronology",
    "player_movement",
    "roster_snapshot",
    "pick_right_detail",
    "player_identity",
)

DEFERRED_FACT_TYPES: tuple[str, ...] = (
    "contract_terms_beyond_base_status",
    "daily_roster_state",
    "conditional_pick_branch_resolution",
    "narrative/editorial events",
)

PROVIDER_ROLES: tuple[ProviderRole, ...] = (
    "chronology_spine",
    "structured_player_movement",
    "official_confirmation",
    "roster_snapshot",
    "secondary_pick_detail",
    "identity_roster",
)

RECOGNIZED_SOURCE_SYSTEMS: tuple[SourceSystem, ...] = (
    "basketball_reference",
    "nba_player_movement",
    "nba_official",
    "team_official",
    "realgm",
    "nba_stats",
    "curated_fixture",
)

ALLOWED_EVIDENCE_STATES: tuple[EvidenceState, ...] = (
    "recognized_provider",
    "loaded_evidence",
    "supports_event",
    "conflicts_event",
    "missing_required_evidence",
)

ALLOWED_CORROBORATION_STATUSES: tuple[CorroborationStatus, ...] = (
    "meets_minimum",
    "bref_only",
    "missing_required_evidence",
    "recognized_provider_not_loaded",
    "out_of_scope",
)

ALLOWED_CONFLICT_STATUSES: tuple[ConflictStatus, ...] = (
    "not_evaluated",
    "no_conflict_detected",
    "conflict_suspected",
)

PLANNED_VS_LOADED_RULE = (
    "Recognized provider roles must never count as loaded evidence or supporting "
    "evidence unless a matching source_record/source_event exists."
)

CORROBORATION_REPORT_OUTPUT_KEY = "source_corroboration_report"
CORROBORATION_REPORTING_UNIT = "canonical_event"
CORROBORATION_DERIVATION_PATH = (
    "canonical_event -> canonical_event_member -> source_event -> source_record"
)
SOURCE_POLICY_VERSION = "source_policy_v1"


class FactTypePolicy(BaseModel):
    fact_type: FactType
    description: str
    minimum_required_roles: list[ProviderRole] = Field(default_factory=list)
    target_roles: list[ProviderRole] = Field(default_factory=list)


class ProviderRolePolicy(BaseModel):
    role: ProviderRole
    source_systems: list[SourceSystem] = Field(default_factory=list)
    initial_evidence_state: EvidenceState
    notes: str | None = None


class SourcePolicy(BaseModel):
    policy_version: str
    first_pass_fact_types: list[FactTypePolicy] = Field(default_factory=list)
    deferred_fact_types: list[str] = Field(default_factory=list)
    provider_roles: list[ProviderRolePolicy] = Field(default_factory=list)
    allowed_evidence_states: list[EvidenceState] = Field(default_factory=list)
    allowed_corroboration_statuses: list[CorroborationStatus] = Field(default_factory=list)
    allowed_conflict_statuses: list[ConflictStatus] = Field(default_factory=list)
    planned_vs_loaded_rule: str


SOURCE_POLICY = SourcePolicy(
    policy_version=SOURCE_POLICY_VERSION,
    first_pass_fact_types=[
        FactTypePolicy(
            fact_type="transaction_chronology",
            description="Whether the event date/type exists in a transaction chronology.",
            minimum_required_roles=["chronology_spine"],
            target_roles=["structured_player_movement", "official_confirmation"],
        ),
        FactTypePolicy(
            fact_type="player_movement",
            description="Whether player movement details are corroborated by structured movement data or official text.",
            minimum_required_roles=["chronology_spine"],
            target_roles=["structured_player_movement", "official_confirmation"],
        ),
        FactTypePolicy(
            fact_type="roster_snapshot",
            description="Whether roster-state assertions are supported by an explicit roster snapshot source.",
            minimum_required_roles=["roster_snapshot"],
            target_roles=["identity_roster"],
        ),
        FactTypePolicy(
            fact_type="pick_right_detail",
            description="Whether pick obligations, protections, and via chains have secondary or official support.",
            minimum_required_roles=["secondary_pick_detail"],
            target_roles=["official_confirmation"],
        ),
        FactTypePolicy(
            fact_type="player_identity",
            description="Whether player/team identifiers can be joined to durable identity data.",
            minimum_required_roles=["identity_roster"],
            target_roles=["structured_player_movement"],
        ),
    ],
    deferred_fact_types=list(DEFERRED_FACT_TYPES),
    provider_roles=[
        ProviderRolePolicy(
            role="chronology_spine",
            source_systems=["basketball_reference"],
            initial_evidence_state="loaded_evidence",
            notes="BRef is the broad chronology spine once records are loaded, not final corroboration by itself.",
        ),
        ProviderRolePolicy(
            role="structured_player_movement",
            source_systems=["nba_player_movement", "nba_official"],
            initial_evidence_state="recognized_provider",
            notes="NBA.com player movement is recognized until matching source records/events are loaded.",
        ),
        ProviderRolePolicy(
            role="official_confirmation",
            source_systems=["nba_official", "team_official"],
            initial_evidence_state="recognized_provider",
            notes="Official league/team releases are authoritative when loaded, but article discovery is incomplete.",
        ),
        ProviderRolePolicy(
            role="roster_snapshot",
            source_systems=["nba_stats", "basketball_reference"],
            initial_evidence_state="recognized_provider",
            notes="Explicit roster snapshot evidence is recognized until matching roster source records are loaded.",
        ),
        ProviderRolePolicy(
            role="secondary_pick_detail",
            source_systems=["realgm", "curated_fixture"],
            initial_evidence_state="recognized_provider",
            notes="RealGM and curated fixtures can document pick detail, but loaded rows must still be explicit.",
        ),
        ProviderRolePolicy(
            role="identity_roster",
            source_systems=["nba_stats", "basketball_reference"],
            initial_evidence_state="recognized_provider",
            notes="NBA Stats and BRef roster references support identity and roster-state corroboration when loaded.",
        ),
    ],
    allowed_evidence_states=list(ALLOWED_EVIDENCE_STATES),
    allowed_corroboration_statuses=list(ALLOWED_CORROBORATION_STATUSES),
    allowed_conflict_statuses=list(ALLOWED_CONFLICT_STATUSES),
    planned_vs_loaded_rule=PLANNED_VS_LOADED_RULE,
)

CORROBORATION_REPORT_EVENT_FIELDS: tuple[str, ...] = (
    "canonical_event_id",
    "event_date",
    "event_type",
    "fact_type",
    "loaded_source_systems",
    "loaded_source_types",
    "recognized_provider_roles",
    "required_source_roles",
    "missing_roles",
    "evidence_states",
    "corroboration_status",
    "conflict_status",
    "notes",
)


class SourceDefinition(BaseModel):
    source_id: str
    purpose: str
    required_fields: list[str] = Field(default_factory=list)
    notes: str | None = None


class SourcePlan(BaseModel):
    franchise: str
    scope_start: str
    source_definitions: list[SourceDefinition] = Field(default_factory=list)


def get_default_source_plan() -> SourcePlan:
    return SourcePlan(
        franchise="memphis-grizzlies",
        scope_start="2016-07-01",
        source_definitions=[
            SourceDefinition(
                source_id="transactions_log",
                purpose="Complete Memphis transaction chronology for graph nodes.",
                required_fields=[
                    "event_date",
                    "event_type",
                    "transaction_label",
                    "inbound_assets",
                    "outbound_assets",
                ],
            ),
            SourceDefinition(
                source_id="player_reference",
                purpose="Stable player identity and display metadata.",
                required_fields=["player_id", "display_name"],
            ),
            SourceDefinition(
                source_id="pick_reference",
                purpose="Pick identity, ownership, protections, swaps, and resolution.",
                required_fields=["draft_year", "round_number", "original_team"],
            ),
            SourceDefinition(
                source_id="roster_state",
                purpose="Post-event roster validation and continuity checks.",
                required_fields=["as_of_date", "roster_asset_ids"],
            ),
        ],
    )
