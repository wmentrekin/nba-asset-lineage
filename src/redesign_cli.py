from __future__ import annotations

import argparse
import json

import psycopg

from db_config import load_database_url
from foundation.export import build_empty_base_export
from foundation.sources import get_default_source_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset-era Memphis asset lineage CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show the current reset-era scaffold status.")
    subparsers.add_parser("check-db", help="Run a minimal database connectivity check.")
    subparsers.add_parser("show-base-export", help="Print the current base export scaffold as JSON.")
    subparsers.add_parser("show-source-plan", help="Print the current reset-era source plan as JSON.")

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


def main() -> None:
    args = parse_args()
    if args.command == "status":
        payload = command_status()
    elif args.command == "check-db":
        payload = command_check_db()
    elif args.command == "show-base-export":
        payload = build_empty_base_export().model_dump(mode="json")
    elif args.command == "show-source-plan":
        payload = get_default_source_plan().model_dump(mode="json")
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
