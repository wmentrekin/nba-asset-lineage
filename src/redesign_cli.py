from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Sequence

from canonical.events import bootstrap_canonical_events_schema, build_and_persist_canonical_events
from canonical.player_tenure import (
    bootstrap_canonical_player_tenure_schema,
    build_and_persist_canonical_player_tenures,
)
from canonical.validate import validate_canonical_events
from canonical.validate_player_tenure import validate_canonical_player_tenures
from db_config import load_database_url
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

    bootstrap_canonical_parser = subparsers.add_parser(
        "bootstrap-canonical-events",
        help="Apply the Stage 2 canonical event bootstrap SQL.",
    )
    bootstrap_canonical_parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path("sql/redesign/0002_canonical_events_bootstrap.sql"),
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

    canonical_build_parser = subparsers.add_parser(
        "build-canonical-events",
        help="Build Stage 2 canonical events and provenance from evidence plus overrides.",
    )
    canonical_build_parser.add_argument("--builder-version", default="stage2-events-v1")

    canonical_validate_parser = subparsers.add_parser(
        "validate-canonical-events",
        help="Validate canonical events and event provenance currently stored in DB.",
    )
    canonical_validate_parser.add_argument("--sample-limit", type=int, default=5000)

    bootstrap_player_tenure_parser = subparsers.add_parser(
        "bootstrap-canonical-player-tenure",
        help="Apply the Stage 3 canonical player tenure bootstrap SQL.",
    )
    bootstrap_player_tenure_parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path("sql/redesign/0003_player_tenure_bootstrap.sql"),
    )

    build_player_tenure_parser = subparsers.add_parser(
        "build-canonical-player-tenures",
        help="Build Stage 3 canonical player tenures, assets, and provenance from evidence plus Stage 2 events.",
    )
    build_player_tenure_parser.add_argument("--builder-version", default="stage3-player-tenure-v1")

    validate_player_tenure_parser = subparsers.add_parser(
        "validate-canonical-player-tenures",
        help="Validate canonical player tenure tables currently stored in DB.",
    )
    validate_player_tenure_parser.add_argument("--sample-limit", type=int, default=5000)

    return parser.parse_args(argv)


def _connect():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for redesign CLI database commands.") from exc
    return psycopg.connect(load_database_url())


def _emit(payload: dict[str, object]) -> int:
    print(json.dumps(payload, sort_keys=True, default=str))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command == "bootstrap-evidence":
        bootstrap_evidence_schema(args.sql_path)
        return _emit({"command": args.command, "sql_path": str(args.sql_path), "status": "success"})

    if args.command == "bootstrap-canonical-events":
        bootstrap_canonical_events_schema(args.sql_path)
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

    if args.command == "build-canonical-events":
        counts = build_and_persist_canonical_events(builder_version=args.builder_version)
        return _emit({"command": args.command, "status": "success", **counts})

    if args.command == "bootstrap-canonical-player-tenure":
        bootstrap_canonical_player_tenure_schema(args.sql_path)
        return _emit({"command": args.command, "sql_path": str(args.sql_path), "status": "success"})

    if args.command == "build-canonical-player-tenures":
        counts = build_and_persist_canonical_player_tenures(builder_version=args.builder_version)
        return _emit({"command": args.command, "status": "success", **counts})

    if args.command == "validate-canonical-events":
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        event_id,
                        event_type,
                        event_date,
                        event_order,
                        event_label,
                        description,
                        transaction_group_key,
                        is_compound,
                        notes,
                        created_at,
                        updated_at
                    from canonical.events
                    order by event_date, event_order, event_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                event_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        event_provenance_id,
                        event_id,
                        source_record_id,
                        claim_id,
                        override_id,
                        provenance_role,
                        fallback_reason,
                        created_at
                    from canonical.event_provenance
                    order by created_at, event_provenance_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                provenance_rows = cur.fetchall()

        from canonical.models import CanonicalEvent, EventProvenance

        events = [
            CanonicalEvent(
                event_id=row[0],
                event_type=row[1],
                event_date=row[2],
                event_order=row[3],
                event_label=row[4],
                description=row[5],
                transaction_group_key=row[6],
                is_compound=row[7],
                notes=row[8],
                created_at=row[9],
                updated_at=row[10],
            )
            for row in event_rows
        ]
        provenance = [
            EventProvenance(
                event_provenance_id=row[0],
                event_id=row[1],
                source_record_id=row[2],
                claim_id=row[3],
                override_id=row[4],
                provenance_role=row[5],
                fallback_reason=row[6],
                created_at=row[7],
            )
            for row in provenance_rows
        ]
        report = validate_canonical_events(events=events, provenance_rows=provenance)
        return _emit(
            {
                "command": args.command,
                "status": "success" if report.ok else "validation_failed",
                "event_count": report.event_count,
                "provenance_count": report.provenance_count,
                "errors": report.errors,
                "warnings": report.warnings,
            }
        )

    if args.command == "validate-canonical-player-tenures":
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        player_id,
                        display_name,
                        normalized_name,
                        nba_person_id,
                        created_at,
                        updated_at
                    from canonical.player_identity
                    order by player_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                player_identity_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        player_identity_provenance_id,
                        player_id,
                        source_record_id,
                        claim_id,
                        override_id,
                        provenance_role,
                        fallback_reason,
                        created_at
                    from canonical.player_identity_provenance
                    order by created_at, player_identity_provenance_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                player_identity_provenance_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        player_tenure_id,
                        player_id,
                        tenure_start_date,
                        tenure_end_date,
                        entry_event_id,
                        exit_event_id,
                        tenure_type,
                        roster_path_type,
                        created_at,
                        updated_at
                    from canonical.player_tenure
                    order by player_id, tenure_start_date, player_tenure_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                player_tenure_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        asset_id,
                        asset_kind,
                        player_tenure_id,
                        pick_asset_id,
                        asset_label,
                        created_at,
                        updated_at
                    from canonical.asset
                    order by asset_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                asset_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        asset_provenance_id,
                        asset_id,
                        player_tenure_id,
                        pick_asset_id,
                        source_record_id,
                        claim_id,
                        override_id,
                        provenance_role,
                        fallback_reason,
                        created_at
                    from canonical.asset_provenance
                    order by created_at, asset_provenance_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                asset_provenance_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        asset_state_id,
                        asset_id,
                        state_type,
                        effective_start_date,
                        effective_end_date,
                        state_payload,
                        source_event_id,
                        created_at,
                        updated_at
                    from canonical.asset_state
                    order by created_at, asset_state_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                asset_state_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        asset_state_provenance_id,
                        asset_state_id,
                        source_record_id,
                        claim_id,
                        override_id,
                        provenance_role,
                        fallback_reason,
                        created_at
                    from canonical.asset_state_provenance
                    order by created_at, asset_state_provenance_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                asset_state_provenance_rows = cur.fetchall()

        from canonical.models import (
            AssetProvenance,
            AssetState,
            AssetStateProvenance,
            CanonicalAsset,
            CanonicalPlayerIdentity,
            CanonicalPlayerTenure,
            PlayerIdentityProvenance,
        )

        player_identities = [
            CanonicalPlayerIdentity(
                player_id=row[0],
                display_name=row[1],
                normalized_name=row[2],
                nba_person_id=row[3],
                created_at=row[4],
                updated_at=row[5],
            )
            for row in player_identity_rows
        ]
        player_identity_provenance = [
            PlayerIdentityProvenance(
                player_identity_provenance_id=row[0],
                player_id=row[1],
                source_record_id=row[2],
                claim_id=row[3],
                override_id=row[4],
                provenance_role=row[5],
                fallback_reason=row[6],
                created_at=row[7],
            )
            for row in player_identity_provenance_rows
        ]
        tenures = [
            CanonicalPlayerTenure(
                player_tenure_id=row[0],
                player_id=row[1],
                tenure_start_date=row[2],
                tenure_end_date=row[3],
                entry_event_id=row[4],
                exit_event_id=row[5],
                tenure_type=row[6],
                roster_path_type=row[7],
                created_at=row[8],
                updated_at=row[9],
            )
            for row in player_tenure_rows
        ]
        assets = [
            CanonicalAsset(
                asset_id=row[0],
                asset_kind=row[1],
                player_tenure_id=row[2],
                pick_asset_id=row[3],
                asset_label=row[4],
                created_at=row[5],
                updated_at=row[6],
            )
            for row in asset_rows
        ]
        asset_provenance = [
            AssetProvenance(
                asset_provenance_id=row[0],
                asset_id=row[1],
                player_tenure_id=row[2],
                pick_asset_id=row[3],
                source_record_id=row[4],
                claim_id=row[5],
                override_id=row[6],
                provenance_role=row[7],
                fallback_reason=row[8],
                created_at=row[9],
            )
            for row in asset_provenance_rows
        ]
        asset_states = [
            AssetState(
                asset_state_id=row[0],
                asset_id=row[1],
                state_type=row[2],
                effective_start_date=row[3],
                effective_end_date=row[4],
                state_payload=row[5],
                source_event_id=row[6],
                created_at=row[7],
                updated_at=row[8],
            )
            for row in asset_state_rows
        ]
        asset_state_provenance = [
            AssetStateProvenance(
                asset_state_provenance_id=row[0],
                asset_state_id=row[1],
                source_record_id=row[2],
                claim_id=row[3],
                override_id=row[4],
                provenance_role=row[5],
                fallback_reason=row[6],
                created_at=row[7],
            )
            for row in asset_state_provenance_rows
        ]
        report = validate_canonical_player_tenures(
            player_identities=player_identities,
            player_identity_provenance_rows=player_identity_provenance,
            player_tenures=tenures,
            assets=assets,
            asset_provenance_rows=asset_provenance,
            asset_states=asset_states,
            asset_state_provenance_rows=asset_state_provenance,
        )
        return _emit(
            {
                "command": args.command,
                "status": "success" if report.ok else "validation_failed",
                "player_identity_count": report.player_identity_count,
                "player_tenure_count": report.player_tenure_count,
                "asset_count": report.asset_count,
                "asset_state_count": report.asset_state_count,
                "errors": report.errors,
                "warnings": report.warnings,
            }
        )

    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
