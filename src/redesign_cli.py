from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Sequence

from db_config import load_db_config
from evidence.ingest import (
    bootstrap_evidence_schema,
    build_live_source_records,
    fetch_source_records,
    insert_normalized_claims,
    insert_source_records,
    normalize_source_records,
)
from evidence.normalize import normalize_source_record
from evidence.overrides import insert_override_bundle, load_override_bundle
from evidence.validate import validate_stage1_rows


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run redesign implementation tasks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap-evidence", help="Apply the Stage 1 evidence bootstrap SQL.")
    bootstrap_parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path("sql/redesign/0001_evidence_bootstrap.sql"),
    )

    build_parser = subparsers.add_parser(
        "build-evidence",
        help="Ingest live evidence, normalize claims, load overrides, and validate Stage 1 rows.",
    )
    build_parser.add_argument("--sources", default="spotrac,nba_api")
    build_parser.add_argument("--team-slug", default="memphis-grizzlies")
    build_parser.add_argument("--team-code", default="mem")
    build_parser.add_argument("--team-abbrevs", default="MEM,VAN")
    build_parser.add_argument("--start-date", default="2016-01-01")
    build_parser.add_argument("--end-date", default=date.today().isoformat())
    build_parser.add_argument("--parser-version", default="stage1-live-v1")
    build_parser.add_argument("--normalizer-version", default="stage1-normalizer-v1")
    build_parser.add_argument("--overrides-path", type=Path, default=Path("overrides"))

    normalize_parser = subparsers.add_parser("normalize-evidence", help="Normalize source records already loaded in DB.")
    normalize_parser.add_argument("--normalizer-version", default="stage1-normalizer-v1")
    normalize_parser.add_argument("--source-record-id")

    override_parser = subparsers.add_parser("load-overrides", help="Load override files into evidence.overrides.")
    override_parser.add_argument("--overrides-path", type=Path, default=Path("overrides"))

    validate_parser = subparsers.add_parser("validate-evidence", help="Validate Stage 1 evidence rows currently in DB.")
    validate_parser.add_argument("--sample-limit", type=int, default=5000)

    return parser.parse_args(argv)


def _connect():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for redesign CLI database commands.") from exc
    return psycopg.connect(load_db_config().dsn)


def _emit(payload: dict[str, object]) -> int:
    print(json.dumps(payload, sort_keys=True, default=str))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command == "bootstrap-evidence":
        bootstrap_evidence_schema(args.sql_path)
        return _emit({"command": args.command, "sql_path": str(args.sql_path), "status": "success"})

    if args.command == "build-evidence":
        sources = {entry.strip().lower() for entry in args.sources.split(",") if entry.strip()}
        team_abbrevs = {entry.strip().upper() for entry in args.team_abbrevs.split(",") if entry.strip()}
        source_records = build_live_source_records(
            sources=sources,
            team_slug=args.team_slug,
            team_code=args.team_code,
            team_abbrevs=team_abbrevs,
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
            parser_version=args.parser_version,
        )
        override_bundle = load_override_bundle(args.overrides_path)

        with _connect() as conn:
            inserted_source_records = insert_source_records(conn, source_records)
            normalized_claims = [
                claim
                for record in source_records
                for claim in normalize_source_record(
                    record,
                    normalizer_version=args.normalizer_version,
                )
            ]
            inserted_claims = insert_normalized_claims(conn, normalized_claims)
            override_counts = insert_override_bundle(conn, override_bundle)
            conn.commit()

        report = validate_stage1_rows(
            source_records=source_records,
            normalized_claims=normalized_claims,
            overrides=override_bundle.overrides,
        )
        return _emit(
            {
                "command": args.command,
                "status": "success" if report.ok else "validation_failed",
                "source_record_count": len(source_records),
                "inserted_source_record_count": inserted_source_records,
                "normalized_claim_count": len(normalized_claims),
                "inserted_claim_count": inserted_claims,
                **override_counts,
                "errors": report.errors,
                "warnings": report.warnings,
            }
        )

    if args.command == "normalize-evidence":
        with _connect() as conn:
            claims = normalize_source_records(
                conn,
                normalizer_version=args.normalizer_version,
                source_record_id=args.source_record_id,
            )
            inserted_claims = insert_normalized_claims(conn, claims)
            conn.commit()
        return _emit(
            {
                "command": args.command,
                "status": "success",
                "normalized_claim_count": len(claims),
                "inserted_claim_count": inserted_claims,
            }
        )

    if args.command == "load-overrides":
        bundle = load_override_bundle(args.overrides_path)
        with _connect() as conn:
            counts = insert_override_bundle(conn, bundle)
            conn.commit()
        return _emit({"command": args.command, "status": "success", **counts})

    if args.command == "validate-evidence":
        with _connect() as conn:
            source_records = fetch_source_records(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        claim_id,
                        source_record_id,
                        claim_type,
                        claim_subject_type,
                        claim_subject_key,
                        claim_group_hint,
                        claim_date,
                        source_sequence,
                        claim_payload,
                        confidence_flag,
                        normalizer_version,
                        created_at
                    from evidence.normalized_claims
                    order by created_at, claim_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                claim_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        override_id,
                        override_type,
                        target_type,
                        target_key,
                        payload,
                        reason,
                        authored_by,
                        authored_at,
                        is_active
                    from evidence.overrides
                    order by authored_at, override_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                override_rows = cur.fetchall()

        from evidence.models import NormalizedClaim, OverrideRecord

        claims = [
            NormalizedClaim(
                claim_id=row[0],
                source_record_id=row[1],
                claim_type=row[2],
                claim_subject_type=row[3],
                claim_subject_key=row[4],
                claim_group_hint=row[5],
                claim_date=row[6],
                source_sequence=row[7],
                claim_payload=row[8],
                confidence_flag=row[9],
                normalizer_version=row[10],
                created_at=row[11],
            )
            for row in claim_rows
        ]
        overrides = [
            OverrideRecord(
                override_id=row[0],
                override_type=row[1],
                target_type=row[2],
                target_key=row[3],
                payload=row[4],
                reason=row[5],
                authored_by=row[6],
                authored_at=row[7],
                is_active=row[8],
            )
            for row in override_rows
        ]
        report = validate_stage1_rows(
            source_records=source_records,
            normalized_claims=claims,
            overrides=overrides,
        )
        return _emit(
            {
                "command": args.command,
                "status": "success" if report.ok else "validation_failed",
                "source_record_count": report.source_record_count,
                "normalized_claim_count": report.normalized_claim_count,
                "override_count": report.override_count,
                "errors": report.errors,
                "warnings": report.warnings,
            }
        )

    raise RuntimeError(f"Unsupported command: {args.command}")
