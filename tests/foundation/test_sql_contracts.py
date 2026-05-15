from pathlib import Path

from foundation.sources import (
    ALLOWED_CONFLICT_STATUSES,
    ALLOWED_CORROBORATION_STATUSES,
    ALLOWED_EVIDENCE_STATES,
    CORROBORATION_REPORT_EVENT_FIELDS,
    CORROBORATION_REPORT_OUTPUT_KEY,
    FIRST_PASS_FACT_TYPES,
    PLANNED_VS_LOADED_RULE,
    PROVIDER_ROLES,
    RECOGNIZED_SOURCE_SYSTEMS,
    SOURCE_POLICY,
)


def test_source_policy_defines_first_pass_fact_taxonomy_and_roles() -> None:
    assert set(FIRST_PASS_FACT_TYPES) == {
        "transaction_chronology",
        "player_movement",
        "roster_snapshot",
        "pick_right_detail",
        "player_identity",
    }
    assert set(PROVIDER_ROLES) >= {
        "chronology_spine",
        "structured_player_movement",
        "official_confirmation",
        "roster_snapshot",
        "secondary_pick_detail",
        "identity_roster",
    }
    assert set(RECOGNIZED_SOURCE_SYSTEMS) >= {
        "basketball_reference",
        "nba_player_movement",
        "nba_official",
        "team_official",
        "realgm",
        "nba_stats",
    }

    policy_by_fact_type = {row.fact_type: row for row in SOURCE_POLICY.first_pass_fact_types}
    assert policy_by_fact_type["transaction_chronology"].minimum_required_roles == ["chronology_spine"]
    assert policy_by_fact_type["player_movement"].target_roles == [
        "structured_player_movement",
        "official_confirmation",
    ]
    assert policy_by_fact_type["pick_right_detail"].minimum_required_roles == ["secondary_pick_detail"]
    assert "conditional_pick_branch_resolution" in SOURCE_POLICY.deferred_fact_types


def test_source_policy_distinguishes_planned_providers_from_loaded_evidence() -> None:
    assert set(ALLOWED_EVIDENCE_STATES) == {
        "recognized_provider",
        "loaded_evidence",
        "supports_event",
        "conflicts_event",
        "missing_required_evidence",
    }
    assert set(ALLOWED_CORROBORATION_STATUSES) == {
        "meets_minimum",
        "bref_only",
        "missing_required_evidence",
        "recognized_provider_not_loaded",
        "out_of_scope",
    }
    assert set(ALLOWED_CONFLICT_STATUSES) == {
        "not_evaluated",
        "no_conflict_detected",
        "conflict_suspected",
    }
    assert "must never count as loaded evidence" in PLANNED_VS_LOADED_RULE
    assert SOURCE_POLICY.planned_vs_loaded_rule == PLANNED_VS_LOADED_RULE

    provider_state_by_role = {row.role: row.initial_evidence_state for row in SOURCE_POLICY.provider_roles}
    assert provider_state_by_role["chronology_spine"] == "loaded_evidence"
    assert provider_state_by_role["structured_player_movement"] == "recognized_provider"
    assert provider_state_by_role["official_confirmation"] == "recognized_provider"


def test_source_policy_defines_corroboration_report_contract_without_schema() -> None:
    assert CORROBORATION_REPORT_OUTPUT_KEY == "source_corroboration_report"
    assert set(CORROBORATION_REPORT_EVENT_FIELDS) == {
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
    }

    sql_text = "\n".join(path.read_text(encoding="utf-8") for path in Path("sql").glob("*.sql"))
    assert "foundation.source_corroboration" not in sql_text
    assert "source_corroboration_report" not in sql_text
    assert "corroboration_status" not in sql_text


def test_draft_pick_resolution_bootstrap_sql_defines_guarded_resolution_table() -> None:
    sql_text = Path("sql/0005_foundation_draft_pick_resolution_bootstrap.sql").read_text(encoding="utf-8")
    assert "create table if not exists foundation.draft_pick_resolution" in sql_text
    assert "references foundation.draft_selection" in sql_text
    assert "references foundation.pick" in sql_text
    assert "references foundation.asset" in sql_text
    assert "resolution_status in ('slot_verified')" in sql_text
    assert "draft_pick_resolution_selection_idx" in sql_text


def test_context_bootstrap_sql_defines_draft_lottery_result_contract() -> None:
    sql_text = Path("sql/0004_foundation_context_bootstrap.sql").read_text(encoding="utf-8")
    assert "create table if not exists foundation.draft_lottery_result" in sql_text
    assert "lottery_result_id text primary key" in sql_text
    assert "draft_year integer not null" in sql_text
    assert "lottery_date date null" in sql_text
    assert "team_code text not null" in sql_text
    assert "owner_team_code text null" in sql_text
    assert "original_team_code text null" in sql_text
    assert "lottery_position integer null" in sql_text
    assert "result_pick_slot integer not null" in sql_text
    assert "pre_lottery_odds text null" in sql_text
    assert "draft_lottery_result_year_team_idx" in sql_text
    assert "on foundation.draft_lottery_result (draft_year, team_code)" in sql_text
    assert "draft_lottery_result_year_owner_idx" in sql_text
    assert "on foundation.draft_lottery_result (draft_year, owner_team_code)" in sql_text
    assert "draft_lottery_result_year_original_idx" in sql_text
    assert "on foundation.draft_lottery_result (draft_year, original_team_code)" in sql_text


def test_context_bootstrap_sql_defines_snapshot_pick_projection_contract() -> None:
    sql_text = Path("sql/0004_foundation_context_bootstrap.sql").read_text(encoding="utf-8")
    assert "create table if not exists foundation.roster_snapshot_pick" in sql_text
    assert "source_obligation_id text null" in sql_text
    assert "confidence text not null default 'derived'" in sql_text
    assert "notes text null" in sql_text
    assert "roster_snapshot_pick_holding_status_check" in sql_text
    assert "holding_status in ('owned', 'owed_out', 'swap_right', 'encumbered', 'conditional')" in sql_text
    assert "roster_snapshot_pick_confidence_check" in sql_text
    assert "confidence in ('derived', 'curated', 'validated', 'uncertain')" in sql_text


def test_pick_inventory_bootstrap_sql_defines_obligation_ledger_contract() -> None:
    sql_text = Path("sql/0006_foundation_pick_inventory_bootstrap.sql").read_text(encoding="utf-8")
    assert "create table if not exists foundation.pick_inventory_obligation" in sql_text
    assert "obligation_id text primary key" in sql_text
    assert "effective_date date not null" in sql_text
    assert "perspective_team_code text not null" in sql_text
    assert "owner_team_code text not null" in sql_text
    assert "original_team_code text not null" in sql_text
    assert "draft_year integer not null" in sql_text
    assert "round_number integer not null" in sql_text
    assert "direction text not null" in sql_text
    assert "holding_status text not null" in sql_text
    assert "obligation_type text not null" in sql_text
    assert "confidence text not null" in sql_text
    assert "source_urls text[] not null default '{}'::text[]" in sql_text
    assert "source_labels text[] not null default '{}'::text[]" in sql_text
    assert "retrieved_at timestamptz not null" in sql_text
    assert "source_event_id text null" in sql_text
    assert "canonical_event_id text null" in sql_text
    assert "protection_text text null" in sql_text
    assert "swap_text text null" in sql_text
    assert "condition_text text null" in sql_text
    assert "notes text null" in sql_text
    assert "loadable boolean not null default true" in sql_text
    assert "references foundation.source_event(source_event_id)" in sql_text
    assert "references foundation.canonical_event(canonical_event_id)" in sql_text
    assert "direction in ('incoming', 'outgoing', 'own', 'swap_right', 'swap_obligation')" in sql_text
    assert "holding_status in ('owned', 'owed_out', 'swap_right', 'encumbered', 'conditional')" in sql_text
    assert "obligation_type in ('own_pick', 'traded_pick', 'swap', 'conditional_fallback')" in sql_text
    assert "confidence in ('derived', 'curated', 'validated', 'uncertain')" in sql_text
    assert "cardinality(source_urls) = cardinality(source_labels)" in sql_text
    assert "pick_inventory_obligation_effective_idx" in sql_text
    assert "pick_inventory_obligation_slot_idx" in sql_text
    assert "pick_inventory_obligation_owner_idx" in sql_text


def test_pick_inventory_bootstrap_sql_adds_projection_context_idempotently() -> None:
    sql_text = Path("sql/0006_foundation_pick_inventory_bootstrap.sql").read_text(encoding="utf-8")
    assert "alter table foundation.roster_snapshot_pick" in sql_text
    assert "add column if not exists source_obligation_id text null" in sql_text
    assert "add column if not exists confidence text null" in sql_text
    assert "alter column confidence set default 'derived'" in sql_text
    assert "add column if not exists notes text null" in sql_text
    assert "roster_snapshot_pick_source_obligation_fk" in sql_text
    assert "references foundation.pick_inventory_obligation(obligation_id)" in sql_text
    assert "roster_snapshot_pick_holding_status_check" in sql_text
    assert "roster_snapshot_pick_confidence_check" in sql_text
    assert "roster_snapshot_pick_source_obligation_idx" in sql_text


def test_pick_inventory_bootstrap_sql_adds_lottery_and_pick_context_idempotently() -> None:
    sql_text = Path("sql/0006_foundation_pick_inventory_bootstrap.sql").read_text(encoding="utf-8")
    assert "alter table foundation.draft_lottery_result" in sql_text
    assert "add column if not exists owner_team_code text null" in sql_text
    assert "add column if not exists original_team_code text null" in sql_text
    assert "draft_lottery_result_year_owner_idx" in sql_text
    assert "draft_lottery_result_year_original_idx" in sql_text
    assert "alter table foundation.pick" in sql_text
    assert "add column if not exists pick_overall integer null" in sql_text
    assert "pick_pick_overall_check" in sql_text
    assert "check (pick_overall is null or pick_overall > 0)" in sql_text
    assert "pick_year_pick_overall_idx" in sql_text
