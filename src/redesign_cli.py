from __future__ import annotations

import argparse
import json
from collections import defaultdict

import psycopg
from psycopg import sql

from db_config import load_database_url
from foundation.export import build_empty_base_export
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
    subparsers.add_parser("reset-db-state", help="Drop current non-system schemas and clear public objects to restart from scratch.")
    subparsers.add_parser("show-base-export", help="Print the current base export scaffold as JSON.")
    subparsers.add_parser("show-source-plan", help="Print the current reset-era source plan as JSON.")
    subparsers.add_parser("run-normalization-workbench", help="Run the local normalization workbench over representative raw samples.")

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


def main() -> None:
    args = parse_args()
    if args.command == "status":
        payload = command_status()
    elif args.command == "check-db":
        payload = command_check_db()
    elif args.command == "inspect-db-state":
        payload = command_inspect_db_state()
    elif args.command == "reset-db-state":
        payload = command_reset_db_state()
    elif args.command == "show-base-export":
        payload = build_empty_base_export().model_dump(mode="json")
    elif args.command == "show-source-plan":
        payload = get_default_source_plan().model_dump(mode="json")
    elif args.command == "run-normalization-workbench":
        payload = serialize_sample_workbench()
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
