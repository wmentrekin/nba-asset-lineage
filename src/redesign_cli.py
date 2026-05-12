from __future__ import annotations

import argparse
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
from foundation.export import build_base_export_from_database, build_empty_base_export
from foundation.ingest import (
    bootstrap_foundation_ingest_schema,
    derive_foundation_entities_from_database,
    load_derived_foundation_entities,
    load_roster_snapshots_from_baselines,
    serialize_foundation_ingest_sample_bundle,
)
from foundation.live_sources import (
    load_bref_draft_results,
    load_bref_draft_results_span,
    load_bref_roster_baseline,
    load_bref_roster_baseline_span,
    load_bref_source_events,
    load_bref_source_events_span,
    load_nba_reference,
    preview_bref_draft_results,
    preview_bref_roster_baseline,
    preview_bref_source_events,
    preview_nba_reference,
)
from foundation.sources import get_default_source_plan
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

    subparsers.add_parser("status", help="Show the current reset-era scaffold status.")
    subparsers.add_parser("check-db", help="Run a minimal database connectivity check.")
    subparsers.add_parser("inspect-db-state", help="Inspect current non-system schemas and relation counts before reset.")
    subparsers.add_parser("inspect-foundation-counts", help="Inspect row counts for active foundation tables.")
    subparsers.add_parser("audit-foundation-data", help="Run a read-only audit of loaded foundation data coverage and known gaps.")
    subparsers.add_parser("reset-db-state", help="Drop current non-system schemas and clear public objects to restart from scratch.")
    bootstrap_foundation_parser = subparsers.add_parser("bootstrap-foundation-ingest", help="Apply the reset-era foundation ingest bootstrap SQL.")
    bootstrap_foundation_parser.add_argument("--sql-path", default="sql/0001_foundation_ingest_bootstrap.sql")
    bootstrap_roster_parser = subparsers.add_parser("bootstrap-foundation-roster-baseline", help="Apply the reset-era foundation roster baseline bootstrap SQL.")
    bootstrap_roster_parser.add_argument("--sql-path", default="sql/0003_foundation_roster_baseline_bootstrap.sql")
    bootstrap_canonical_parser = subparsers.add_parser("bootstrap-foundation-canonical", help="Apply the reset-era foundation canonical bootstrap SQL.")
    bootstrap_canonical_parser.add_argument("--sql-path", default="sql/0002_foundation_canonical_bootstrap.sql")
    bootstrap_context_parser = subparsers.add_parser("bootstrap-foundation-context", help="Apply reset-era identity, roster snapshot, and draft context SQL.")
    bootstrap_context_parser.add_argument("--sql-path", default="sql/0004_foundation_context_bootstrap.sql")
    subparsers.add_parser("preview-derived-foundation-entities", help="Build player, pick, and asset rows from the current foundation.source_event table without writing.")
    subparsers.add_parser("load-derived-foundation-entities", help="Build and load player, pick, and asset rows from the current foundation.source_event table.")
    subparsers.add_parser("load-roster-snapshots-from-baselines", help="Build approximate checkpoint roster snapshots from loaded roster baseline rows.")
    subparsers.add_parser("preview-foundation-canonical", help="Build canonical events, members, and transitions from the current foundation tables without writing.")
    subparsers.add_parser("load-foundation-canonical", help="Build and load canonical events, members, and transitions from the current foundation tables.")
    export_graph_parser = subparsers.add_parser("export-foundation-graph", help="Build the first graph-ready export from the current foundation tables.")
    export_graph_parser.add_argument("--output-path", default=None)
    preview_bref_parser = subparsers.add_parser("preview-bref-source-events", help="Fetch and normalize one Basketball-Reference transactions season without writing to the database.")
    preview_bref_parser.add_argument("--team-code", default="MEM")
    preview_bref_parser.add_argument("--season-end-year", type=int, required=True)
    load_bref_parser = subparsers.add_parser("load-bref-source-events", help="Fetch and load one Basketball-Reference transactions season into foundation.source_record and foundation.source_event.")
    load_bref_parser.add_argument("--team-code", default="MEM")
    load_bref_parser.add_argument("--season-end-year", type=int, required=True)
    load_bref_span_parser = subparsers.add_parser("load-bref-source-events-span", help="Fetch and load Basketball-Reference transactions for a season-end-year range.")
    load_bref_span_parser.add_argument("--team-code", default="MEM")
    load_bref_span_parser.add_argument("--start-season-end-year", type=int, default=2017)
    load_bref_span_parser.add_argument("--end-season-end-year", type=int, default=2026)
    load_bref_span_parser.add_argument("--request-delay", type=float, default=0.8)
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
    preview_bref_draft_parser = subparsers.add_parser("preview-bref-draft-results", help="Fetch and normalize one Basketball-Reference draft page without writing.")
    preview_bref_draft_parser.add_argument("--team-code", default="MEM")
    preview_bref_draft_parser.add_argument("--draft-year", type=int, required=True)
    load_bref_draft_parser = subparsers.add_parser("load-bref-draft-results", help="Fetch and load one Basketball-Reference draft page into draft selections.")
    load_bref_draft_parser.add_argument("--team-code", default="MEM")
    load_bref_draft_parser.add_argument("--draft-year", type=int, required=True)
    load_bref_draft_span_parser = subparsers.add_parser("load-bref-draft-results-span", help="Fetch and load Basketball-Reference draft results for a year range.")
    load_bref_draft_span_parser.add_argument("--team-code", default="MEM")
    load_bref_draft_span_parser.add_argument("--start-draft-year", type=int, default=2016)
    load_bref_draft_span_parser.add_argument("--end-draft-year", type=int, default=2025)
    load_bref_draft_span_parser.add_argument("--request-delay", type=float, default=0.8)
    preview_nba_parser = subparsers.add_parser("preview-nba-reference", help="Fetch and normalize NBA stats player and roster reference data without writing to the database.")
    preview_nba_parser.add_argument("--season", required=True)
    preview_nba_parser.add_argument("--team-id", type=int, default=1610612763)
    load_nba_parser = subparsers.add_parser("load-nba-reference", help="Fetch and load NBA stats player and roster reference data into foundation.source_record and foundation.player.")
    load_nba_parser.add_argument("--season", required=True)
    load_nba_parser.add_argument("--team-id", type=int, default=1610612763)
    subparsers.add_parser("show-base-export", help="Print the current base export scaffold as JSON.")
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
                "draft_selection",
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
        "draft_selection",
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
    if args.command == "status":
        payload = command_status()
    elif args.command == "check-db":
        payload = command_check_db()
    elif args.command == "inspect-db-state":
        payload = command_inspect_db_state()
    elif args.command == "inspect-foundation-counts":
        payload = command_inspect_foundation_counts()
    elif args.command == "audit-foundation-data":
        payload = audit_foundation_data(load_database_url())
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
            }
    elif args.command == "preview-bref-source-events":
        payload = preview_bref_source_events(team_code=args.team_code, season_end_year=args.season_end_year)
    elif args.command == "load-bref-source-events":
        payload = load_bref_source_events(load_database_url(), team_code=args.team_code, season_end_year=args.season_end_year)
    elif args.command == "load-bref-source-events-span":
        payload = load_bref_source_events_span(
            load_database_url(),
            team_code=args.team_code,
            start_season_end_year=args.start_season_end_year,
            end_season_end_year=args.end_season_end_year,
            request_delay=args.request_delay,
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
        payload = preview_bref_draft_results(team_code=args.team_code, draft_year=args.draft_year)
    elif args.command == "load-bref-draft-results":
        payload = load_bref_draft_results(load_database_url(), team_code=args.team_code, draft_year=args.draft_year)
    elif args.command == "load-bref-draft-results-span":
        payload = load_bref_draft_results_span(
            load_database_url(),
            team_code=args.team_code,
            start_draft_year=args.start_draft_year,
            end_draft_year=args.end_draft_year,
            request_delay=args.request_delay,
        )
    elif args.command == "preview-nba-reference":
        payload = preview_nba_reference(season=args.season, team_id=args.team_id)
    elif args.command == "load-nba-reference":
        payload = load_nba_reference(load_database_url(), season=args.season, team_id=args.team_id)
    elif args.command == "show-base-export":
        payload = build_empty_base_export().model_dump(mode="json")
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
        snapshot_counts = load_roster_snapshots_from_baselines(database_url)
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
            "snapshots": snapshot_counts,
            "canonical": canonical_counts,
            "export": {
                "output_path": args.output_path,
                "events": len(export.events),
                "player_assets": len(export.player_assets),
                "pick_assets": len(export.pick_assets),
                "transitions": len(export.transitions),
                "roster_snapshots": len(export.roster_snapshots),
            },
            "known_gaps": [
                "Basketball-Reference roster pages are season roster references, not date-exact checkpoint snapshots.",
                "Two-way versus standard contract status still needs a richer source.",
                "Draft selections are collected, but pick-to-player resolution is not fully linked to pick assets yet.",
                "Draft lottery results remain contextual and are not loaded by this command yet.",
            ],
        }
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
