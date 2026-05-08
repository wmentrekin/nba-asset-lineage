from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import psycopg
from psycopg import sql

from db_config import load_database_url
from foundation.export import build_empty_base_export
from foundation.ingest import bootstrap_foundation_ingest_schema, serialize_foundation_ingest_sample_bundle
from foundation.live_sources import (
    load_bref_source_events,
    load_nba_reference,
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
    subparsers.add_parser("reset-db-state", help="Drop current non-system schemas and clear public objects to restart from scratch.")
    bootstrap_foundation_parser = subparsers.add_parser("bootstrap-foundation-ingest", help="Apply the reset-era foundation ingest bootstrap SQL.")
    bootstrap_foundation_parser.add_argument("--sql-path", default="sql/0001_foundation_ingest_bootstrap.sql")
    preview_bref_parser = subparsers.add_parser("preview-bref-source-events", help="Fetch and normalize one Basketball-Reference transactions season without writing to the database.")
    preview_bref_parser.add_argument("--team-code", default="MEM")
    preview_bref_parser.add_argument("--season-end-year", type=int, required=True)
    load_bref_parser = subparsers.add_parser("load-bref-source-events", help="Fetch and load one Basketball-Reference transactions season into foundation.source_record and foundation.source_event.")
    load_bref_parser.add_argument("--team-code", default="MEM")
    load_bref_parser.add_argument("--season-end-year", type=int, required=True)
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
            for table_name in ("source_record", "source_event", "player", "pick", "asset"):
                cursor.execute(
                    sql.SQL("select count(*) from foundation.{}").format(sql.Identifier(table_name))
                )
                counts[table_name] = int(cursor.fetchone()[0])
    return {
        "status": "ok",
        "schema": "foundation",
        "counts": counts,
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
    elif args.command == "reset-db-state":
        payload = command_reset_db_state()
    elif args.command == "bootstrap-foundation-ingest":
        bootstrap_foundation_ingest_schema(load_database_url(), sql_path=Path(args.sql_path))
        payload = {"status": "ok", "sql_path": args.sql_path}
    elif args.command == "preview-bref-source-events":
        payload = preview_bref_source_events(team_code=args.team_code, season_end_year=args.season_end_year)
    elif args.command == "load-bref-source-events":
        payload = load_bref_source_events(load_database_url(), team_code=args.team_code, season_end_year=args.season_end_year)
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
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
