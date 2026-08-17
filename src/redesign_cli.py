from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import psycopg
from psycopg import sql

from db_config import load_database_url
from foundation.audit import audit_foundation_data
from foundation.canonical import (
    bootstrap_foundation_canonical_schema,
    derive_foundation_canonical_bundle_from_database,
    load_foundation_canonical_bundle,
)
from foundation.daily_roster_state import (
    DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH as DEFAULT_DAILY_ROSTER_TWO_WAY_FIXTURE_PATH,
    load_daily_roster_state,
    preview_daily_roster_state,
)
from foundation.draft_resolution import (
    DEFAULT_CURATED_DRAFT_PICK_RESOLUTION_PATH,
    bootstrap_foundation_draft_pick_resolution_schema,
    load_curated_draft_pick_resolution,
    preview_curated_draft_pick_resolution,
    preview_draft_pick_resolution,
)
from foundation.draft_prior_owner import (
    DEFAULT_DRAFT_PRIOR_OWNER_OVERRIDE_PATH,
    load_draft_prior_owner_lineage,
    preview_draft_prior_owner_lineage,
    preview_draft_prior_owner_replay_proof,
)
from foundation.draft_lottery_results import (
    DEFAULT_DRAFT_LOTTERY_RESULTS_FIXTURE_PATH,
    load_draft_lottery_results,
    preview_draft_lottery_results,
)
from foundation.export import build_base_export_from_database, build_empty_base_export
from foundation.ingest import (
    bootstrap_foundation_ingest_schema,
    derive_foundation_entities_from_database,
    load_derived_foundation_entities,
    load_roster_snapshots_from_baselines,
    serialize_foundation_ingest_sample_bundle,
)
from foundation.live_sources import (
    load_curated_draft_pick_detail_sources,
    DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH,
    DEFAULT_OFFICIAL_RELEASE_FRAGMENT_DIR,
    DEFAULT_OFFICIAL_RELEASE_FIXTURE_PATH,
    DEFAULT_OFFICIAL_ROSTER_REFERENCE_FIXTURE_PATH,
    DEFAULT_ROSTER_REFERENCE_ALIAS_FIXTURE_PATH,
    load_bref_draft_results,
    load_bref_draft_results_span,
    load_bref_roster_baseline,
    load_bref_roster_baseline_span,
    load_bref_source_events,
    load_bref_source_events_span,
    load_nba_player_movement,
    load_official_release_sources,
    preflight_locked_source_bundle,
    load_official_roster_reference_fixture,
    load_roster_reference_aliases,
    load_nba_reference,
    load_nba_roster_reference,
    load_nba_roster_reference_span,
    preview_bref_draft_results,
    preview_bref_roster_baseline,
    preview_bref_source_events,
    preview_curated_draft_pick_detail_sources,
    preview_nba_reference,
    preview_nba_roster_reference,
    preview_nba_player_movement,
    preview_official_release_sources,
    preview_official_roster_reference_fixture,
    preview_roster_reference_aliases,
)
from foundation.pick_inventory import (
    DEFAULT_FUTURE_PICK_OBLIGATION_PATH,
    load_pick_inventory_obligations,
    load_pick_inventory_snapshots,
    preview_pick_inventory_obligations,
    preview_pick_inventory_snapshots,
)
from foundation.roster_validation import (
    load_roster_snapshot_validation,
    preview_roster_snapshot_validation,
)
from foundation.sources import get_default_source_plan
from foundation.two_way_status import (
    DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
    load_two_way_status,
    preview_two_way_status,
)
from foundation.visualization_export import build_visualization_export
from foundation.workbench import serialize_sample_workbench

RESETTABLE_PROJECT_SCHEMAS = (
    "bronze",
    "silver",
    "evidence",
    "canonical",
    "presentation",
    "editorial",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset-era Memphis asset lineage CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_locked_bundle_arguments(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("--payload-bundle-path", required=True)
        command_parser.add_argument("--expected-bundle-sha256", required=True)
        command_parser.add_argument("--dry-run", action="store_true", help="Explicit read-only mode; this is also the default unless --execute is supplied.")
        command_parser.add_argument("--execute", action="store_true", help="Write only the reviewed locked bundle after digest validation.")

    subparsers.add_parser("status", help="Show the current reset-era scaffold status.")
    subparsers.add_parser("check-db", help="Run a minimal database connectivity check.")
    subparsers.add_parser("inspect-db-state", help="Inspect current non-system schemas and relation counts before reset.")
    subparsers.add_parser("inspect-foundation-counts", help="Inspect row counts for active foundation tables.")
    audit_parser = subparsers.add_parser("audit-foundation-data", help="Run a read-only audit of loaded foundation data coverage and known gaps.")
    audit_parser.add_argument("--pick-obligation-fixture-path", default=str(DEFAULT_FUTURE_PICK_OBLIGATION_PATH))
    subparsers.add_parser(
        "inspect-contract-semantics",
        help="Read-only summary of structured contract-semantic payload coverage from loaded source events.",
    )
    draft_resolution_parser = subparsers.add_parser("preview-draft-pick-resolution", help="Read-only preview of draft_selection to pick asset resolution candidates.")
    draft_resolution_parser.add_argument("--team-code", default="MEM")
    curated_draft_resolution_parser = subparsers.add_parser("preview-curated-draft-pick-resolution", help="Read-only preview of curated draft slot resolutions against live draft_selection rows.")
    curated_draft_resolution_parser.add_argument("--team-code", default="MEM")
    curated_draft_resolution_parser.add_argument("--fixture-path", default=str(DEFAULT_CURATED_DRAFT_PICK_RESOLUTION_PATH))
    load_curated_draft_resolution_parser = subparsers.add_parser("load-curated-draft-pick-resolution", help="Load curated draft slot resolutions after every preview row is safe.")
    load_curated_draft_resolution_parser.add_argument("--team-code", default="MEM")
    load_curated_draft_resolution_parser.add_argument("--fixture-path", default=str(DEFAULT_CURATED_DRAFT_PICK_RESOLUTION_PATH))
    load_curated_draft_resolution_parser.add_argument("--dry-run", action="store_true")
    pick_inventory_parser = subparsers.add_parser("preview-pick-inventory-snapshots", help="Read-only projection of future pick inventory rows for roster snapshots.")
    pick_inventory_parser.add_argument("--team-code", default="MEM")
    pick_inventory_parser.add_argument("--fixture-path", default=str(DEFAULT_FUTURE_PICK_OBLIGATION_PATH))
    pick_inventory_parser.add_argument("--max-draft-year", type=int, default=2032)
    pick_inventory_obligations_parser = subparsers.add_parser("preview-pick-inventory-obligations", help="Read-only validation preview of curated future pick obligation fixture rows.")
    pick_inventory_obligations_parser.add_argument("--team-code", default="MEM")
    pick_inventory_obligations_parser.add_argument("--fixture-path", default=str(DEFAULT_FUTURE_PICK_OBLIGATION_PATH))
    pick_inventory_obligations_parser.add_argument(
        "--allow-update-id",
        action="append",
        default=[],
        help="Explicit obligation_id allowed to update if the fixture conflicts with an existing source-backed row. May be passed more than once.",
    )
    load_pick_inventory_obligations_parser = subparsers.add_parser("load-pick-inventory-obligations", help="Guarded load of source-backed future pick obligations and needed pick assets.")
    load_pick_inventory_obligations_parser.add_argument("--team-code", default="MEM")
    load_pick_inventory_obligations_parser.add_argument("--fixture-path", default=str(DEFAULT_FUTURE_PICK_OBLIGATION_PATH))
    load_pick_inventory_obligations_parser.add_argument("--dry-run", action="store_true")
    load_pick_inventory_obligations_parser.add_argument(
        "--allow-update-id",
        action="append",
        default=[],
        help="Explicit obligation_id allowed to update if the fixture conflicts with an existing source-backed row. May be passed more than once.",
    )
    load_pick_inventory_snapshots_parser = subparsers.add_parser("load-pick-inventory-snapshots", help="Guarded replacement of derived roster snapshot future-pick inventory rows.")
    load_pick_inventory_snapshots_parser.add_argument("--team-code", default="MEM")
    load_pick_inventory_snapshots_parser.add_argument("--max-draft-year", type=int, default=2032)
    load_pick_inventory_snapshots_parser.add_argument("--dry-run", action="store_true")
    two_way_preview_parser = subparsers.add_parser("preview-two-way-status", help="Read-only preview of curated two-way status intervals against roster snapshot players.")
    two_way_preview_parser.add_argument("--team-code", default="MEM")
    two_way_preview_parser.add_argument("--fixture-path", default=str(DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH))
    two_way_load_parser = subparsers.add_parser("load-two-way-status", help="Guarded reset/apply load of curated two-way status intervals.")
    two_way_load_parser.add_argument("--team-code", default="MEM")
    two_way_load_parser.add_argument("--fixture-path", default=str(DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH))
    two_way_load_parser.add_argument("--dry-run", action="store_true")
    draft_lottery_preview_parser = subparsers.add_parser("preview-draft-lottery-results", help="Read-only preview of curated Memphis draft lottery result rows.")
    draft_lottery_preview_parser.add_argument("--team-code", default="MEM")
    draft_lottery_preview_parser.add_argument("--fixture-path", default=str(DEFAULT_DRAFT_LOTTERY_RESULTS_FIXTURE_PATH))
    draft_lottery_load_parser = subparsers.add_parser("load-draft-lottery-results", help="Guarded load of curated Memphis draft lottery result rows.")
    draft_lottery_load_parser.add_argument("--team-code", default="MEM")
    draft_lottery_load_parser.add_argument("--fixture-path", default=str(DEFAULT_DRAFT_LOTTERY_RESULTS_FIXTURE_PATH))
    draft_lottery_load_parser.add_argument("--dry-run", action="store_true")
    subparsers.add_parser("reset-db-state", help="Drop current non-system schemas and clear public objects to restart from scratch.")
    bootstrap_foundation_parser = subparsers.add_parser("bootstrap-foundation-ingest", help="Apply the reset-era foundation ingest bootstrap SQL.")
    bootstrap_foundation_parser.add_argument("--sql-path", default="sql/0001_foundation_ingest_bootstrap.sql")
    bootstrap_roster_parser = subparsers.add_parser("bootstrap-foundation-roster-baseline", help="Apply the reset-era foundation roster baseline bootstrap SQL.")
    bootstrap_roster_parser.add_argument("--sql-path", default="sql/0003_foundation_roster_baseline_bootstrap.sql")
    bootstrap_canonical_parser = subparsers.add_parser("bootstrap-foundation-canonical", help="Apply the reset-era foundation canonical bootstrap SQL.")
    bootstrap_canonical_parser.add_argument("--sql-path", default="sql/0002_foundation_canonical_bootstrap.sql")
    bootstrap_context_parser = subparsers.add_parser("bootstrap-foundation-context", help="Apply reset-era identity, roster snapshot, and draft context SQL.")
    bootstrap_context_parser.add_argument("--sql-path", default="sql/0004_foundation_context_bootstrap.sql")
    bootstrap_draft_resolution_parser = subparsers.add_parser("bootstrap-foundation-draft-pick-resolution", help="Apply reset-era draft pick resolution SQL.")
    bootstrap_draft_resolution_parser.add_argument("--sql-path", default="sql/0005_foundation_draft_pick_resolution_bootstrap.sql")
    bootstrap_pick_inventory_parser = subparsers.add_parser("bootstrap-foundation-pick-inventory", help="Apply reset-era pick inventory obligation bootstrap SQL.")
    bootstrap_pick_inventory_parser.add_argument("--sql-path", default="sql/0006_foundation_pick_inventory_bootstrap.sql")
    bootstrap_daily_and_prior_owner_parser = subparsers.add_parser(
        "bootstrap-foundation-daily-roster-and-prior-owner",
        help="Apply reset-era daily roster state and draft prior-owner lineage bootstrap SQL.",
    )
    bootstrap_daily_and_prior_owner_parser.add_argument(
        "--sql-path",
        default="sql/0007_foundation_daily_roster_and_prior_owner_bootstrap.sql",
    )
    subparsers.add_parser("preview-derived-foundation-entities", help="Build player, pick, and asset rows from the current foundation.source_event table without writing.")
    subparsers.add_parser("load-derived-foundation-entities", help="Build and load player, pick, and asset rows from the current foundation.source_event table.")
    subparsers.add_parser("load-roster-snapshots-from-baselines", help="Build approximate checkpoint roster snapshots from loaded roster baseline rows.")
    preview_daily_roster_state_parser = subparsers.add_parser(
        "preview-daily-roster-state",
        help="Read-only preview of additive daily Memphis roster occupancy derived from baselines, source events, and two-way intervals.",
    )
    preview_daily_roster_state_parser.add_argument("--team-code", default="MEM")
    preview_daily_roster_state_parser.add_argument(
        "--fixture-path",
        default=str(DEFAULT_DAILY_ROSTER_TWO_WAY_FIXTURE_PATH),
    )
    load_daily_roster_state_parser = subparsers.add_parser(
        "load-daily-roster-state",
        help="Guarded load of additive daily Memphis roster occupancy rows.",
    )
    load_daily_roster_state_parser.add_argument("--team-code", default="MEM")
    load_daily_roster_state_parser.add_argument(
        "--fixture-path",
        default=str(DEFAULT_DAILY_ROSTER_TWO_WAY_FIXTURE_PATH),
    )
    load_daily_roster_state_parser.add_argument("--dry-run", action="store_true")
    preview_roster_validation_parser = subparsers.add_parser(
        "preview-roster-snapshot-validation",
        help="Read-only preview of official season-reference validation rows for roster checkpoints.",
    )
    preview_roster_validation_parser.add_argument("--team-code", default="MEM")
    load_roster_validation_parser = subparsers.add_parser(
        "load-roster-snapshot-validation",
        help="Compute and write official season-reference validation rows for roster checkpoints.",
    )
    load_roster_validation_parser.add_argument("--team-code", default="MEM")
    draft_prior_owner_preview_parser = subparsers.add_parser(
        "preview-draft-prior-owner-lineage",
        help="Read-only preview of additive prior-owner draft lineage rows for Memphis selections.",
    )
    draft_prior_owner_preview_parser.add_argument("--team-code", default="MEM")
    draft_prior_owner_preview_parser.add_argument(
        "--fixture-path",
        default=str(DEFAULT_DRAFT_PRIOR_OWNER_OVERRIDE_PATH),
    )
    draft_prior_owner_load_parser = subparsers.add_parser(
        "load-draft-prior-owner-lineage",
        help="Guarded load of additive prior-owner draft lineage rows for Memphis selections.",
    )
    draft_prior_owner_load_parser.add_argument("--team-code", default="MEM")
    draft_prior_owner_load_parser.add_argument(
        "--fixture-path",
        default=str(DEFAULT_DRAFT_PRIOR_OWNER_OVERRIDE_PATH),
    )
    draft_prior_owner_load_parser.add_argument("--dry-run", action="store_true")
    draft_prior_owner_replay_proof_parser = subparsers.add_parser(
        "preview-draft-prior-owner-replay-proof",
        help="Read-only proof summary for Memphis draft-selection replay coverage, exact derivation closure, and selection-day evidence.",
    )
    draft_prior_owner_replay_proof_parser.add_argument("--team-code", default="MEM")
    draft_prior_owner_replay_proof_parser.add_argument(
        "--fixture-path",
        default=str(DEFAULT_DRAFT_PRIOR_OWNER_OVERRIDE_PATH),
    )
    subparsers.add_parser("preview-foundation-canonical", help="Build canonical events, members, and transitions from the current foundation tables without writing.")
    subparsers.add_parser("load-foundation-canonical", help="Build and load canonical events, members, and transitions from the current foundation tables.")
    export_graph_parser = subparsers.add_parser("export-foundation-graph", help="Build the first graph-ready export from the current foundation tables.")
    export_graph_parser.add_argument("--output-path", default=None)
    export_visualization_parser = subparsers.add_parser(
        "export-visualization-graph",
        help="Build the derived visualization export from the current foundation tables.",
    )
    export_visualization_parser.add_argument("--output-path", default=None)
    preview_bref_parser = subparsers.add_parser("preview-bref-source-events", help="Normalize a locked Basketball-Reference transactions bundle without writing to the database.")
    preview_bref_parser.add_argument("--team-code", default="MEM")
    preview_bref_parser.add_argument("--season-end-year", type=int)
    add_locked_bundle_arguments(preview_bref_parser)
    load_bref_parser = subparsers.add_parser("load-bref-source-events", help="Load a reviewed locked Basketball-Reference transactions bundle into foundation.source_record and foundation.source_event.")
    load_bref_parser.add_argument("--team-code", default="MEM")
    load_bref_parser.add_argument("--season-end-year", type=int)
    add_locked_bundle_arguments(load_bref_parser)
    load_bref_span_parser = subparsers.add_parser("load-bref-source-events-span", help="Load one reviewed locked Basketball-Reference transactions bundle; live span fetching is retired.")
    load_bref_span_parser.add_argument("--team-code", default="MEM")
    add_locked_bundle_arguments(load_bref_span_parser)
    preview_bref_roster_parser = subparsers.add_parser("preview-bref-roster-baseline", help="Fetch and normalize one Basketball-Reference team roster page without writing to the database.")
    preview_bref_roster_parser.add_argument("--team-code", default="MEM")
    preview_bref_roster_parser.add_argument("--season-end-year", type=int, required=True)
    load_bref_roster_parser = subparsers.add_parser("load-bref-roster-baseline", help="Fetch and load one Basketball-Reference team roster baseline into foundation.source_record, foundation.player, and foundation.roster_baseline_player.")
    load_bref_roster_parser.add_argument("--team-code", default="MEM")
    load_bref_roster_parser.add_argument("--season-end-year", type=int, required=True)
    load_bref_roster_span_parser = subparsers.add_parser("load-bref-roster-baseline-span", help="Fetch and load Basketball-Reference roster baselines for a season-end-year range.")
    load_bref_roster_span_parser.add_argument("--team-code", default="MEM")
    load_bref_roster_span_parser.add_argument("--start-season-end-year", type=int, default=2017)
    load_bref_roster_span_parser.add_argument("--end-season-end-year", type=int, default=2026)
    load_bref_roster_span_parser.add_argument("--request-delay", type=float, default=0.8)
    preview_bref_draft_parser = subparsers.add_parser("preview-bref-draft-results", help="Normalize a locked Basketball-Reference draft bundle without writing.")
    preview_bref_draft_parser.add_argument("--team-code", default="MEM")
    preview_bref_draft_parser.add_argument("--draft-year", type=int)
    add_locked_bundle_arguments(preview_bref_draft_parser)
    load_bref_draft_parser = subparsers.add_parser("load-bref-draft-results", help="Load a reviewed locked Basketball-Reference draft bundle into draft selections.")
    load_bref_draft_parser.add_argument("--team-code", default="MEM")
    load_bref_draft_parser.add_argument("--draft-year", type=int)
    add_locked_bundle_arguments(load_bref_draft_parser)
    load_bref_draft_span_parser = subparsers.add_parser("load-bref-draft-results-span", help="Load one reviewed locked Basketball-Reference draft bundle; live span fetching is retired.")
    load_bref_draft_span_parser.add_argument("--team-code", default="MEM")
    add_locked_bundle_arguments(load_bref_draft_span_parser)
    preview_curated_draft_pick_detail_parser = subparsers.add_parser(
        "preview-curated-draft-pick-detail-sources",
        help="Read-only preview of curated draft-pick-detail corroboration rows generated from loaded Memphis draft selections.",
    )
    preview_curated_draft_pick_detail_parser.add_argument("--team-code", default="MEM")
    load_curated_draft_pick_detail_parser = subparsers.add_parser(
        "load-curated-draft-pick-detail-sources",
        help="Build curated draft-pick-detail source_record/source_event candidates and write them only with --execute.",
    )
    load_curated_draft_pick_detail_parser.add_argument("--team-code", default="MEM")
    load_curated_draft_pick_detail_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit read-only mode; this is also the default unless --execute is supplied.",
    )
    load_curated_draft_pick_detail_parser.add_argument(
        "--execute",
        action="store_true",
        help="Write foundation.source_record and foundation.source_event rows after preview review.",
    )
    preview_nba_parser = subparsers.add_parser("preview-nba-reference", help="Fetch and normalize NBA stats player and roster reference data without writing to the database.")
    preview_nba_parser.add_argument("--season", required=True)
    preview_nba_parser.add_argument("--team-id", type=int, default=1610612763)
    preview_nba_roster_parser = subparsers.add_parser(
        "preview-nba-roster-reference",
        help="Fetch and normalize official NBA roster reference rows for one season without writing to foundation.player.",
    )
    preview_nba_roster_parser.add_argument("--season", required=True)
    preview_nba_roster_parser.add_argument("--team-id", type=int, default=1610612763)
    preview_nba_roster_parser.add_argument("--team-code", default="MEM")
    preview_nba_player_movement_parser = subparsers.add_parser("preview-nba-player-movement", help="Normalize a locked NBA player-movement bundle without writing.")
    add_locked_bundle_arguments(preview_nba_player_movement_parser)
    load_nba_player_movement_parser = subparsers.add_parser(
        "load-nba-player-movement",
        help="Load a reviewed locked NBA player-movement bundle only with --execute.",
    )
    add_locked_bundle_arguments(load_nba_player_movement_parser)
    preview_official_release_parser = subparsers.add_parser(
        "preview-official-release-sources",
        help="Read-only preview of curated official NBA.com or team-release corroboration sources.",
    )
    add_locked_bundle_arguments(preview_official_release_parser)
    load_official_release_parser = subparsers.add_parser(
        "load-official-release-sources",
        help="Build curated official release source_record/source_event candidates and write them only with --execute.",
    )
    add_locked_bundle_arguments(load_official_release_parser)
    preview_official_roster_reference_parser = subparsers.add_parser(
        "preview-official-roster-reference-fixture",
        help="Read-only preview of checked-in official roster-reference fixture rows normalized to the validator contract.",
    )
    preview_official_roster_reference_parser.add_argument(
        "--fixture-path",
        default=str(DEFAULT_OFFICIAL_ROSTER_REFERENCE_FIXTURE_PATH),
    )
    preview_roster_reference_alias_parser = subparsers.add_parser(
        "preview-roster-reference-aliases",
        help="Read-only preview of checked-in manual aliases for roster-reference reconciliation.",
    )
    preview_roster_reference_alias_parser.add_argument(
        "--fixture-path",
        default=str(DEFAULT_ROSTER_REFERENCE_ALIAS_FIXTURE_PATH),
    )
    load_official_roster_reference_parser = subparsers.add_parser(
        "load-official-roster-reference-fixture",
        help="Build checked-in official roster-reference source_record rows and write them only with --execute.",
    )
    load_official_roster_reference_parser.add_argument(
        "--fixture-path",
        default=str(DEFAULT_OFFICIAL_ROSTER_REFERENCE_FIXTURE_PATH),
    )
    load_official_roster_reference_parser.add_argument("--dry-run", action="store_true", help="Explicit read-only mode; this is also the default unless --execute is supplied.")
    load_official_roster_reference_parser.add_argument("--execute", action="store_true", help="Write foundation.source_record rows after preview review.")
    load_roster_reference_alias_parser = subparsers.add_parser(
        "load-roster-reference-aliases",
        help="Load checked-in manual aliases for roster-reference reconciliation.",
    )
    load_roster_reference_alias_parser.add_argument(
        "--fixture-path",
        default=str(DEFAULT_ROSTER_REFERENCE_ALIAS_FIXTURE_PATH),
    )
    load_roster_reference_alias_parser.add_argument("--dry-run", action="store_true", help="Explicit read-only mode; this is also the default unless --execute is supplied.")
    load_roster_reference_alias_parser.add_argument("--execute", action="store_true", help="Write foundation.player_alias rows after preview review.")
    load_nba_parser = subparsers.add_parser("load-nba-reference", help="Fetch and load NBA stats player and roster reference data into foundation.source_record and foundation.player.")
    load_nba_parser.add_argument("--season", required=True)
    load_nba_parser.add_argument("--team-id", type=int, default=1610612763)
    load_nba_roster_parser = subparsers.add_parser(
        "load-nba-roster-reference",
        help="Fetch and load official NBA roster reference rows into foundation.source_record and foundation.roster_baseline_player only.",
    )
    load_nba_roster_parser.add_argument("--season", required=True)
    load_nba_roster_parser.add_argument("--team-id", type=int, default=1610612763)
    load_nba_roster_parser.add_argument("--team-code", default="MEM")
    load_nba_roster_span_parser = subparsers.add_parser(
        "load-nba-roster-reference-span",
        help="Fetch and load official NBA roster reference rows for a season-end-year range.",
    )
    load_nba_roster_span_parser.add_argument("--team-id", type=int, default=1610612763)
    load_nba_roster_span_parser.add_argument("--team-code", default="MEM")
    load_nba_roster_span_parser.add_argument("--start-season-end-year", type=int, default=2017)
    load_nba_roster_span_parser.add_argument("--end-season-end-year", type=int, default=2026)
    load_nba_roster_span_parser.add_argument("--request-delay", type=float, default=0.8)
    subparsers.add_parser("inspect-foundation-graph-baseline", help="Read-only graph baseline counts and checksum for checkpoint review.")
    subparsers.add_parser("inspect-visualization-graph-baseline", help="Read-only visualization export counts and checksum for checkpoint review.")
    subparsers.add_parser("show-base-export", help="Print the current base export scaffold as JSON.")
    subparsers.add_parser("show-visualization-export", help="Print the current visualization export scaffold as JSON.")
    subparsers.add_parser("show-source-plan", help="Print the current reset-era source plan as JSON.")
    subparsers.add_parser("run-normalization-workbench", help="Run the local normalization workbench over representative raw samples.")
    subparsers.add_parser("build-foundation-ingest-sample", help="Build sample ingest rows from the normalization workbench output.")
    full_span_parser = subparsers.add_parser("load-foundation-full-span", help="Load the current full-span foundation source set and rebuild derived/canonical layers.")
    full_span_parser.add_argument("--team-code", default="MEM")
    full_span_parser.add_argument("--start-season-end-year", type=int, default=2017)
    full_span_parser.add_argument("--end-season-end-year", type=int, default=2026)
    full_span_parser.add_argument("--start-draft-year", type=int, default=2016)
    full_span_parser.add_argument("--end-draft-year", type=int, default=2025)
    full_span_parser.add_argument("--request-delay", type=float, default=0.8)
    full_span_parser.add_argument("--output-path", default=None)
    full_span_parser.add_argument("--replace-existing", action="store_true", help="Clear active foundation tables before reloading the full-span source set.")

    return parser.parse_args()


def command_status() -> dict[str, object]:
    return {
        "phase": "foundation-reset",
        "scope": "memphis-grizzlies",
        "product_target": "10-year asset evolution graph",
        "active_packages": ["foundation"],
        "archived_reference_root": "legacy/",
        "next_design_focus": [
            "minimum base graph contract",
            "source definitions",
            "supabase ingestion/storage model",
            "frontend rebuild from smaller truth surface",
        ],
    }


def command_check_db() -> dict[str, object]:
    database_url = load_database_url()
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select current_database(), current_user")
            current_database, current_user = cursor.fetchone()
    return {
        "status": "ok",
        "database": current_database,
        "user": current_user,
    }


def command_inspect_db_state() -> dict[str, object]:
    database_url = load_database_url()
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select n.nspname as schema_name,
                       c.relkind,
                       count(*) as relation_count
                from pg_class c
                join pg_namespace n on n.oid = c.relnamespace
                where n.nspname not in ('information_schema')
                  and n.nspname not like 'pg_%'
                  and c.relkind in ('r', 'v', 'm', 'S', 'f', 'p')
                group by n.nspname, c.relkind
                order by n.nspname, c.relkind
                """
            )
            rows = cursor.fetchall()

    by_schema: dict[str, dict[str, int]] = defaultdict(dict)
    for schema_name, relkind, relation_count in rows:
        by_schema[str(schema_name)][str(relkind)] = int(relation_count)

    return {
        "status": "ok",
        "schemas": by_schema,
    }


def command_reset_db_state() -> dict[str, object]:
    database_url = load_database_url()
    dropped_schemas: list[str] = []
    dropped_public_relations: list[str] = []

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select schema_name
                from information_schema.schemata
                where schema_name = any(%s)
                order by schema_name
                """
                ,
                (list(RESETTABLE_PROJECT_SCHEMAS),),
            )
            schemas = [str(row[0]) for row in cursor.fetchall()]

            for schema_name in schemas:
                cursor.execute(sql.SQL("drop schema if exists {} cascade").format(sql.Identifier(schema_name)))
                dropped_schemas.append(schema_name)

            cursor.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                order by table_name
                """
            )
            public_tables = [str(row[0]) for row in cursor.fetchall()]
            for table_name in public_tables:
                cursor.execute(sql.SQL("drop table if exists public.{} cascade").format(sql.Identifier(table_name)))
                dropped_public_relations.append(f"table:{table_name}")

            cursor.execute(
                """
                select sequence_name
                from information_schema.sequences
                where sequence_schema = 'public'
                order by sequence_name
                """
            )
            public_sequences = [str(row[0]) for row in cursor.fetchall()]
            for sequence_name in public_sequences:
                cursor.execute(sql.SQL("drop sequence if exists public.{} cascade").format(sql.Identifier(sequence_name)))
                dropped_public_relations.append(f"sequence:{sequence_name}")

            cursor.execute(
                """
                select routine_name, specific_name
                from information_schema.routines
                where routine_schema = 'public'
                order by routine_name, specific_name
                """
            )
            public_routines = [(str(row[0]), str(row[1])) for row in cursor.fetchall()]
            for routine_name, _specific_name in public_routines:
                cursor.execute(sql.SQL("drop routine if exists public.{} cascade").format(sql.Identifier(routine_name)))
                dropped_public_relations.append(f"routine:{routine_name}")

    return {
        "status": "ok",
        "dropped_schemas": dropped_schemas,
        "dropped_public_relations": dropped_public_relations,
    }


def command_inspect_foundation_counts() -> dict[str, object]:
    database_url = load_database_url()
    counts: dict[str, int] = {}
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            for table_name in (
                "source_record",
                "source_event",
                "player",
                "pick",
                "asset",
                "player_alias",
                "roster_baseline_player",
                "roster_snapshot",
                "roster_snapshot_player",
                "roster_snapshot_pick",
                "roster_snapshot_validation",
                "draft_selection",
                "draft_pick_resolution",
                "pick_inventory_obligation",
                "draft_lottery_result",
                "canonical_event",
                "canonical_event_member",
                "event_asset_transition",
            ):
                cursor.execute("select to_regclass(%s)", (f"foundation.{table_name}",))
                if cursor.fetchone()[0] is None:
                    counts[table_name] = 0
                    continue
                cursor.execute(sql.SQL("select count(*) from foundation.{}").format(sql.Identifier(table_name)))
                counts[table_name] = int(cursor.fetchone()[0])
    return {
        "status": "ok",
        "schema": "foundation",
        "counts": counts,
    }


def command_clear_foundation_data() -> dict[str, object]:
    database_url = load_database_url()
    table_names = (
        "draft_lottery_result",
        "draft_pick_resolution",
        "draft_selection",
        "roster_snapshot_validation",
        "roster_snapshot_pick",
        "roster_snapshot_player",
        "roster_snapshot",
        "event_asset_transition",
        "canonical_event_member",
        "canonical_event",
        "asset",
        "pick",
        "player_alias",
        "roster_baseline_player",
        "player",
        "source_event",
        "source_record",
    )
    existing_tables: list[str] = []
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            for table_name in table_names:
                cursor.execute("select to_regclass(%s)", (f"foundation.{table_name}",))
                if cursor.fetchone()[0] is not None:
                    existing_tables.append(table_name)
            if existing_tables:
                identifiers = [
                    sql.SQL("foundation.{}").format(sql.Identifier(table_name))
                    for table_name in existing_tables
                ]
                cursor.execute(
                    sql.SQL("truncate table {} cascade").format(sql.SQL(", ").join(identifiers))
                )
        connection.commit()
    return {
        "status": "ok",
        "cleared_tables": existing_tables,
    }


def main() -> None:
    args = parse_args()

    def guarded_database_url(source_kind: str, source_scope: dict[str, object] | None) -> str | None:
        if not args.execute:
            return None
        preflight_locked_source_bundle(
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            expected_source_kind=source_kind,
            expected_source_scope=source_scope,
        )
        return load_database_url()

    if args.command == "status":
        payload = command_status()
    elif args.command == "check-db":
        payload = command_check_db()
    elif args.command == "inspect-db-state":
        payload = command_inspect_db_state()
    elif args.command == "inspect-foundation-counts":
        payload = command_inspect_foundation_counts()
    elif args.command == "audit-foundation-data":
        payload = audit_foundation_data(
            load_database_url(),
            pick_obligation_fixture_path=Path(args.pick_obligation_fixture_path),
        )
    elif args.command == "inspect-contract-semantics":
        payload = dict(audit_foundation_data(load_database_url()).get("contract_semantics", {}))
        payload["writes_to_database"] = False
    elif args.command == "preview-draft-pick-resolution":
        payload = preview_draft_pick_resolution(load_database_url(), team_code=args.team_code).model_dump(mode="json")
    elif args.command == "preview-curated-draft-pick-resolution":
        payload = preview_curated_draft_pick_resolution(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
        ).model_dump(mode="json")
    elif args.command == "load-curated-draft-pick-resolution":
        payload = load_curated_draft_pick_resolution(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
            dry_run=args.dry_run,
        ).model_dump(mode="json")
    elif args.command == "preview-pick-inventory-snapshots":
        payload = preview_pick_inventory_snapshots(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
            max_draft_year=args.max_draft_year,
        ).model_dump(mode="json")
    elif args.command == "preview-pick-inventory-obligations":
        payload = preview_pick_inventory_obligations(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
            allow_update_ids=set(args.allow_update_id or []),
        ).model_dump(mode="json")
    elif args.command == "load-pick-inventory-obligations":
        payload = load_pick_inventory_obligations(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
            dry_run=args.dry_run,
            allow_update_ids=set(args.allow_update_id or []),
        ).model_dump(mode="json")
    elif args.command == "load-pick-inventory-snapshots":
        payload = load_pick_inventory_snapshots(
            load_database_url(),
            team_code=args.team_code,
            max_draft_year=args.max_draft_year,
            dry_run=args.dry_run,
        ).model_dump(mode="json")
    elif args.command == "preview-two-way-status":
        payload = preview_two_way_status(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
        ).model_dump(mode="json")
    elif args.command == "load-two-way-status":
        payload = load_two_way_status(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
            dry_run=args.dry_run,
        ).model_dump(mode="json")
    elif args.command == "preview-draft-lottery-results":
        payload = preview_draft_lottery_results(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
        ).model_dump(mode="json")
    elif args.command == "load-draft-lottery-results":
        payload = load_draft_lottery_results(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
            dry_run=args.dry_run,
        ).model_dump(mode="json")
    elif args.command == "reset-db-state":
        payload = command_reset_db_state()
    elif args.command == "bootstrap-foundation-ingest":
        bootstrap_foundation_ingest_schema(load_database_url(), sql_path=Path(args.sql_path))
        payload = {"status": "ok", "sql_path": args.sql_path}
    elif args.command == "bootstrap-foundation-roster-baseline":
        bootstrap_foundation_ingest_schema(load_database_url(), sql_path=Path(args.sql_path))
        payload = {"status": "ok", "sql_path": args.sql_path}
    elif args.command == "bootstrap-foundation-canonical":
        bootstrap_foundation_canonical_schema(load_database_url(), sql_path=Path(args.sql_path))
        payload = {"status": "ok", "sql_path": args.sql_path}
    elif args.command == "bootstrap-foundation-context":
        bootstrap_foundation_ingest_schema(load_database_url(), sql_path=Path(args.sql_path))
        payload = {"status": "ok", "sql_path": args.sql_path}
    elif args.command == "bootstrap-foundation-draft-pick-resolution":
        bootstrap_foundation_draft_pick_resolution_schema(load_database_url(), sql_path=Path(args.sql_path))
        payload = {"status": "ok", "sql_path": args.sql_path}
    elif args.command == "bootstrap-foundation-pick-inventory":
        bootstrap_foundation_ingest_schema(load_database_url(), sql_path=Path(args.sql_path))
        payload = {"status": "ok", "sql_path": args.sql_path}
    elif args.command == "bootstrap-foundation-daily-roster-and-prior-owner":
        bootstrap_foundation_ingest_schema(load_database_url(), sql_path=Path(args.sql_path))
        payload = {"status": "ok", "sql_path": args.sql_path}
    elif args.command == "preview-derived-foundation-entities":
        derived = derive_foundation_entities_from_database(load_database_url())
        payload = {
            "status": "ok",
            "players": len(derived.players),
            "picks": len(derived.picks),
            "assets": len(derived.assets),
            "first_player": derived.players[0].model_dump(mode="json") if derived.players else None,
            "first_pick": derived.picks[0].model_dump(mode="json") if derived.picks else None,
            "first_asset": derived.assets[0].model_dump(mode="json") if derived.assets else None,
        }
    elif args.command == "load-derived-foundation-entities":
        counts = load_derived_foundation_entities(load_database_url())
        payload = {"status": "ok", **counts}
    elif args.command == "load-roster-snapshots-from-baselines":
        counts = load_roster_snapshots_from_baselines(load_database_url())
        payload = {"status": "ok", **counts}
    elif args.command == "preview-daily-roster-state":
        payload = preview_daily_roster_state(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
        ).model_dump(mode="json")
    elif args.command == "load-daily-roster-state":
        payload = load_daily_roster_state(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
            dry_run=args.dry_run,
        ).model_dump(mode="json")
    elif args.command == "preview-roster-snapshot-validation":
        payload = preview_roster_snapshot_validation(
            load_database_url(),
            team_code=args.team_code,
        )
    elif args.command == "load-roster-snapshot-validation":
        payload = load_roster_snapshot_validation(
            load_database_url(),
            team_code=args.team_code,
        )
    elif args.command == "preview-draft-prior-owner-lineage":
        payload = preview_draft_prior_owner_lineage(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
        ).model_dump(mode="json")
    elif args.command == "load-draft-prior-owner-lineage":
        payload = load_draft_prior_owner_lineage(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
            dry_run=args.dry_run,
        ).model_dump(mode="json")
    elif args.command == "preview-draft-prior-owner-replay-proof":
        payload = preview_draft_prior_owner_replay_proof(
            load_database_url(),
            team_code=args.team_code,
            fixture_path=Path(args.fixture_path),
        ).model_dump(mode="json")
    elif args.command == "preview-foundation-canonical":
        bundle = derive_foundation_canonical_bundle_from_database(load_database_url())
        payload = {
            "status": "ok",
            "canonical_events": len(bundle.canonical_events),
            "canonical_event_members": len(bundle.canonical_event_members),
            "event_asset_transitions": len(bundle.event_asset_transitions),
            "first_canonical_event": bundle.canonical_events[0].model_dump(mode="json") if bundle.canonical_events else None,
            "first_transition": bundle.event_asset_transitions[0].model_dump(mode="json") if bundle.event_asset_transitions else None,
        }
    elif args.command == "load-foundation-canonical":
        counts = load_foundation_canonical_bundle(load_database_url())
        payload = {"status": "ok", **counts}
    elif args.command == "preview-bref-roster-baseline":
        payload = preview_bref_roster_baseline(team_code=args.team_code, season_end_year=args.season_end_year)
    elif args.command == "load-bref-roster-baseline":
        payload = load_bref_roster_baseline(load_database_url(), team_code=args.team_code, season_end_year=args.season_end_year)
    elif args.command == "export-foundation-graph":
        export = build_base_export_from_database(load_database_url())
        payload = export.model_dump(mode="json")
        if args.output_path:
            Path(args.output_path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            payload = {
                "status": "ok",
                "output_path": args.output_path,
                "events": len(export.events),
                "player_assets": len(export.player_assets),
                "pick_assets": len(export.pick_assets),
                "transitions": len(export.transitions),
                "roster_snapshots": len(export.roster_snapshots),
                "daily_roster_states": len(export.daily_roster_states),
                "draft_prior_owner_lineages": len(export.draft_prior_owner_lineages),
                "conditional_pick_families": sum(len(snapshot.conditional_pick_families) for snapshot in export.roster_snapshots),
                "draft_lottery_results": len(export.draft_lottery_results),
            }
    elif args.command == "export-visualization-graph":
        base_export = build_base_export_from_database(load_database_url())
        export = build_visualization_export(base_export)
        payload = export.model_dump(mode="json")
        if args.output_path:
            Path(args.output_path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            payload = {
                "status": "ok",
                "output_path": args.output_path,
                "lanes": len(export.lanes),
                "assets": len(export.assets),
                "occupancy_intervals": len(export.occupancy_intervals),
                "event_nodes": len(export.event_nodes),
                "strand_segments": len(export.strand_segments),
                "event_connectors": len(export.event_connectors),
                "conditional_pick_families": len(export.additive_context.conditional_pick_families),
                "draft_lottery_results": len(export.additive_context.draft_lottery_results),
            }
    elif args.command == "preview-bref-source-events":
        payload = load_bref_source_events(
            team_code=args.team_code,
            season_end_year=args.season_end_year,
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            dry_run=True,
        )
    elif args.command == "load-bref-source-events":
        payload = load_bref_source_events(
            guarded_database_url("bref_transactions", {"team_code": args.team_code.upper()}),
            team_code=args.team_code,
            season_end_year=args.season_end_year,
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            dry_run=args.dry_run,
            execute=args.execute,
        )
    elif args.command == "load-bref-source-events-span":
        payload = load_bref_source_events(
            guarded_database_url("bref_transactions", {"team_code": args.team_code.upper()}),
            team_code=args.team_code,
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            dry_run=args.dry_run,
            execute=args.execute,
        )
    elif args.command == "load-bref-roster-baseline-span":
        payload = load_bref_roster_baseline_span(
            load_database_url(),
            team_code=args.team_code,
            start_season_end_year=args.start_season_end_year,
            end_season_end_year=args.end_season_end_year,
            request_delay=args.request_delay,
        )
    elif args.command == "preview-bref-draft-results":
        payload = load_bref_draft_results(
            team_code=args.team_code,
            draft_year=args.draft_year,
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            dry_run=True,
        )
    elif args.command == "load-bref-draft-results":
        payload = load_bref_draft_results(
            guarded_database_url("bref_draft", {"team_code": args.team_code.upper()}),
            team_code=args.team_code,
            draft_year=args.draft_year,
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            dry_run=args.dry_run,
            execute=args.execute,
        )
    elif args.command == "load-bref-draft-results-span":
        payload = load_bref_draft_results(
            guarded_database_url("bref_draft", {"team_code": args.team_code.upper()}),
            team_code=args.team_code,
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            dry_run=args.dry_run,
            execute=args.execute,
        )
    elif args.command == "preview-curated-draft-pick-detail-sources":
        payload = preview_curated_draft_pick_detail_sources(load_database_url(), team_code=args.team_code)
    elif args.command == "load-curated-draft-pick-detail-sources":
        payload = load_curated_draft_pick_detail_sources(
            load_database_url(),
            team_code=args.team_code,
            dry_run=args.dry_run,
            execute=args.execute,
        )
    elif args.command == "preview-nba-reference":
        payload = preview_nba_reference(season=args.season, team_id=args.team_id)
    elif args.command == "preview-nba-player-movement":
        payload = load_nba_player_movement(
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            dry_run=True,
        )
    elif args.command == "load-nba-player-movement":
        payload = load_nba_player_movement(
            guarded_database_url("nba_player_movement", {"team_code": "MEM"}),
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            dry_run=args.dry_run,
            execute=args.execute,
        )
    elif args.command == "preview-official-release-sources":
        payload = load_official_release_sources(
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            dry_run=True,
        )
    elif args.command == "load-official-release-sources":
        payload = load_official_release_sources(
            guarded_database_url("official_releases", {"team_code": "MEM"}),
            payload_bundle_path=Path(args.payload_bundle_path),
            expected_bundle_sha256=args.expected_bundle_sha256,
            dry_run=args.dry_run,
            execute=args.execute,
        )
    elif args.command == "preview-official-roster-reference-fixture":
        payload = preview_official_roster_reference_fixture(
            load_database_url(),
            fixture_path=Path(args.fixture_path),
        )
    elif args.command == "preview-roster-reference-aliases":
        payload = preview_roster_reference_aliases(
            load_database_url(),
            fixture_path=Path(args.fixture_path),
        )
    elif args.command == "load-official-roster-reference-fixture":
        payload = load_official_roster_reference_fixture(
            load_database_url(),
            fixture_path=Path(args.fixture_path),
            dry_run=args.dry_run,
            execute=args.execute,
        )
    elif args.command == "load-roster-reference-aliases":
        payload = load_roster_reference_aliases(
            load_database_url(),
            fixture_path=Path(args.fixture_path),
            dry_run=args.dry_run,
            execute=args.execute,
        )
    elif args.command == "preview-nba-roster-reference":
        payload = preview_nba_roster_reference(
            load_database_url(),
            season=args.season,
            team_id=args.team_id,
            team_code=args.team_code,
        )
    elif args.command == "load-nba-reference":
        payload = load_nba_reference(load_database_url(), season=args.season, team_id=args.team_id)
    elif args.command == "load-nba-roster-reference":
        payload = load_nba_roster_reference(
            load_database_url(),
            season=args.season,
            team_id=args.team_id,
            team_code=args.team_code,
        )
    elif args.command == "load-nba-roster-reference-span":
        payload = load_nba_roster_reference_span(
            load_database_url(),
            team_id=args.team_id,
            team_code=args.team_code,
            start_season_end_year=args.start_season_end_year,
            end_season_end_year=args.end_season_end_year,
            request_delay=args.request_delay,
        )
    elif args.command == "inspect-foundation-graph-baseline":
        counts = command_inspect_foundation_counts()["counts"]
        export = build_base_export_from_database(load_database_url())
        export_payload = export.model_dump(mode="json")
        checksum = hashlib.sha256(
            json.dumps(export_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        payload = {
            "status": "ok",
            "writes_to_database": False,
            "canonical_counts": {
                "canonical_event": counts.get("canonical_event", 0),
                "canonical_event_member": counts.get("canonical_event_member", 0),
                "event_asset_transition": counts.get("event_asset_transition", 0),
            },
            "graph_export_counts": {
                "events": len(export.events),
                "player_assets": len(export.player_assets),
                "pick_assets": len(export.pick_assets),
                "transitions": len(export.transitions),
                "roster_snapshots": len(export.roster_snapshots),
                "daily_roster_states": len(export.daily_roster_states),
                "draft_prior_owner_lineages": len(export.draft_prior_owner_lineages),
                "conditional_pick_families": sum(len(snapshot.conditional_pick_families) for snapshot in export.roster_snapshots),
                "draft_lottery_results": len(export.draft_lottery_results),
            },
            "graph_export_checksum_sha256": checksum,
        }
    elif args.command == "inspect-visualization-graph-baseline":
        export = build_visualization_export(build_base_export_from_database(load_database_url()))
        export_payload = export.model_dump(mode="json")
        checksum = hashlib.sha256(
            json.dumps(export_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        payload = {
            "status": "ok",
            "writes_to_database": False,
            "visualization_export_counts": {
                "lanes": len(export.lanes),
                "assets": len(export.assets),
                "occupancy_intervals": len(export.occupancy_intervals),
                "event_nodes": len(export.event_nodes),
                "strand_segments": len(export.strand_segments),
                "event_connectors": len(export.event_connectors),
                "conditional_pick_families": len(export.additive_context.conditional_pick_families),
                "draft_lottery_results": len(export.additive_context.draft_lottery_results),
            },
            "visualization_export_checksum_sha256": checksum,
        }
    elif args.command == "show-base-export":
        payload = build_empty_base_export().model_dump(mode="json")
    elif args.command == "show-visualization-export":
        payload = build_visualization_export(build_empty_base_export()).model_dump(mode="json")
    elif args.command == "show-source-plan":
        payload = get_default_source_plan().model_dump(mode="json")
    elif args.command == "run-normalization-workbench":
        payload = serialize_sample_workbench()
    elif args.command == "build-foundation-ingest-sample":
        payload = serialize_foundation_ingest_sample_bundle()
    elif args.command == "load-foundation-full-span":
        database_url = load_database_url()
        bootstrap_foundation_ingest_schema(database_url, sql_path=Path("sql/0001_foundation_ingest_bootstrap.sql"))
        bootstrap_foundation_ingest_schema(database_url, sql_path=Path("sql/0003_foundation_roster_baseline_bootstrap.sql"))
        bootstrap_foundation_ingest_schema(database_url, sql_path=Path("sql/0004_foundation_context_bootstrap.sql"))
        bootstrap_foundation_canonical_schema(database_url, sql_path=Path("sql/0002_foundation_canonical_bootstrap.sql"))
        bootstrap_foundation_draft_pick_resolution_schema(database_url, sql_path=Path("sql/0005_foundation_draft_pick_resolution_bootstrap.sql"))
        clear_result = command_clear_foundation_data() if args.replace_existing else None
        transaction_result = load_bref_source_events_span(
            database_url,
            team_code=args.team_code,
            start_season_end_year=args.start_season_end_year,
            end_season_end_year=args.end_season_end_year,
            request_delay=args.request_delay,
        )
        roster_result = load_bref_roster_baseline_span(
            database_url,
            team_code=args.team_code,
            start_season_end_year=args.start_season_end_year,
            end_season_end_year=args.end_season_end_year,
            request_delay=args.request_delay,
        )
        draft_result = load_bref_draft_results_span(
            database_url,
            team_code=args.team_code,
            start_draft_year=args.start_draft_year,
            end_draft_year=args.end_draft_year,
            request_delay=args.request_delay,
        )
        entity_counts = load_derived_foundation_entities(database_url)
        draft_resolution_result = load_curated_draft_pick_resolution(
            database_url,
            team_code=args.team_code,
            fixture_path=DEFAULT_CURATED_DRAFT_PICK_RESOLUTION_PATH,
            dry_run=False,
        )
        snapshot_counts = load_roster_snapshots_from_baselines(database_url)
        two_way_result = load_two_way_status(
            database_url,
            team_code=args.team_code,
            fixture_path=DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
            dry_run=False,
        )
        canonical_counts = load_foundation_canonical_bundle(database_url)
        export = build_base_export_from_database(database_url)
        if args.output_path:
            Path(args.output_path).write_text(json.dumps(export.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        payload = {
            "status": "ok",
            "cleared": clear_result,
            "transactions": transaction_result,
            "rosters": roster_result,
            "drafts": draft_result,
            "entities": entity_counts,
            "draft_resolution": draft_resolution_result.model_dump(mode="json"),
            "snapshots": snapshot_counts,
            "two_way_status": two_way_result.model_dump(mode="json"),
            "canonical": canonical_counts,
            "export": {
                "output_path": args.output_path,
                "events": len(export.events),
                "player_assets": len(export.player_assets),
                "pick_assets": len(export.pick_assets),
                "transitions": len(export.transitions),
                "roster_snapshots": len(export.roster_snapshots),
                "daily_roster_states": len(export.daily_roster_states),
                "draft_prior_owner_lineages": len(export.draft_prior_owner_lineages),
                "conditional_pick_families": sum(len(snapshot.conditional_pick_families) for snapshot in export.roster_snapshots),
                "draft_lottery_results": len(export.draft_lottery_results),
            },
            "documented_limitations": [
                "Future pick inventory snapshots are intentionally left to the separate obligation and snapshot loaders; this convenience command does not populate them.",
                "Draft lottery results still load through the dedicated lottery command; this convenience command does not populate that additive export surface.",
            ],
        }
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
