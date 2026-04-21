from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Sequence

from canonical.events import bootstrap_canonical_events_schema, build_and_persist_canonical_events
from canonical.event_asset_flow import (
    bootstrap_canonical_event_asset_flow_schema,
    build_and_persist_canonical_event_asset_flows,
)
from canonical.pick_lifecycle import (
    bootstrap_canonical_pick_lifecycle_schema,
    build_and_persist_canonical_pick_lifecycle,
)
from canonical.player_tenure import (
    bootstrap_canonical_player_tenure_schema,
    build_and_persist_canonical_player_tenures,
)
from canonical.validate import validate_canonical_events
from canonical.validate_event_asset_flow import validate_canonical_event_asset_flows
from canonical.validate_pick_lifecycle import validate_canonical_pick_lifecycle
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
from editorial.contract import (
    build_and_persist_editorial_overlays,
    bootstrap_editorial_overlay_schema,
    export_editorial_overlays_json,
    fetch_editorial_overlays,
    validate_editorial_overlay_bundle,
)
from presentation.contract import (
    bootstrap_presentation_contract_schema,
    build_and_persist_presentation_contract,
    export_presentation_contract_json,
    fetch_presentation_contract,
)
from presentation.validate import validate_presentation_contract


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run redesign implementation tasks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap-evidence", help="Apply the Stage 1 evidence bootstrap SQL.")
    bootstrap_parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path("sql/0001_evidence_bootstrap.sql"),
    )

    bootstrap_canonical_parser = subparsers.add_parser(
        "bootstrap-canonical-events",
        help="Apply the Stage 2 canonical event bootstrap SQL.",
    )
    bootstrap_canonical_parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path("sql/0002_canonical_events_bootstrap.sql"),
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
    build_parser.add_argument("--overrides-path", type=Path, default=Path("configs/data"))

    normalize_parser = subparsers.add_parser("normalize-evidence", help="Normalize source records already loaded in DB.")
    normalize_parser.add_argument("--normalizer-version", default="stage1-normalizer-v1")
    normalize_parser.add_argument("--source-record-id")

    override_parser = subparsers.add_parser("load-overrides", help="Load override files into evidence.overrides.")
    override_parser.add_argument("--overrides-path", type=Path, default=Path("configs/data"))

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

    bootstrap_pick_lifecycle_parser = subparsers.add_parser(
        "bootstrap-canonical-pick-lifecycle",
        help="Apply the Stage 4 canonical pick lifecycle bootstrap SQL.",
    )
    bootstrap_pick_lifecycle_parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path("sql/0004_pick_lifecycle_bootstrap.sql"),
    )

    bootstrap_event_asset_flow_parser = subparsers.add_parser(
        "bootstrap-canonical-event-asset-flow",
        help="Apply the Stage 5 canonical event asset flow bootstrap SQL.",
    )
    bootstrap_event_asset_flow_parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path("sql/0005_event_asset_flow_bootstrap.sql"),
    )

    build_pick_lifecycle_parser = subparsers.add_parser(
        "build-canonical-pick-lifecycle",
        help="Build Stage 4 canonical pick assets, transitions, and provenance from evidence plus Stage 2 events.",
    )
    build_pick_lifecycle_parser.add_argument("--builder-version", default="stage4-pick-lifecycle-v1")

    build_event_asset_flow_parser = subparsers.add_parser(
        "build-canonical-event-asset-flows",
        help="Build Stage 5 canonical event asset flows and provenance from Stage 2-4 canonical rows.",
    )
    build_event_asset_flow_parser.add_argument("--builder-version", default="stage5-event-asset-flow-v1")

    validate_pick_lifecycle_parser = subparsers.add_parser(
        "validate-canonical-pick-lifecycle",
        help="Validate canonical pick lifecycle tables currently stored in DB.",
    )
    validate_pick_lifecycle_parser.add_argument("--sample-limit", type=int, default=5000)

    validate_event_asset_flow_parser = subparsers.add_parser(
        "validate-canonical-event-asset-flows",
        help="Validate canonical event asset flow tables currently stored in DB.",
    )
    validate_event_asset_flow_parser.add_argument("--sample-limit", type=int, default=5000)

    bootstrap_presentation_parser = subparsers.add_parser(
        "bootstrap-presentation-contract",
        help="Apply the Stage 6 presentation contract bootstrap SQL.",
    )
    bootstrap_presentation_parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path("sql/0006_presentation_contract_bootstrap.sql"),
    )

    build_presentation_parser = subparsers.add_parser(
        "build-presentation-contract",
        help="Build Stage 6 presentation timeline nodes, edges, lanes, and build metadata.",
    )
    build_presentation_parser.add_argument("--builder-version", default="stage6-presentation-contract-v1")

    validate_presentation_parser = subparsers.add_parser(
        "validate-presentation-contract",
        help="Validate Stage 6 presentation contract tables currently stored in DB.",
    )
    validate_presentation_parser.add_argument("--sample-limit", type=int, default=5000)

    export_presentation_parser = subparsers.add_parser(
        "export-presentation-contract",
        help="Export the latest Stage 6 presentation contract as JSON.",
    )
    export_presentation_parser.add_argument("--output-path", type=Path)
    export_presentation_parser.add_argument(
        "--include-editorial",
        action="store_true",
        help="Include Stage 7 editorial overlays in the exported JSON under an editorial key.",
    )

    bootstrap_editorial_parser = subparsers.add_parser(
        "bootstrap-editorial-overlays",
        help="Apply the Stage 7 editorial overlay bootstrap SQL.",
    )
    bootstrap_editorial_parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path("sql/0007_editorial_overlay_bootstrap.sql"),
    )

    load_editorial_parser = subparsers.add_parser(
        "load-editorial-overlays",
        help="Load Stage 7 editorial overlay rows from tracked structured files and persist them.",
    )
    load_editorial_parser.add_argument(
        "--input-path",
        type=Path,
        default=Path("configs/data"),
    )
    load_editorial_parser.add_argument(
        "--builder-version",
        default="stage7-editorial-overlay-v1",
    )

    validate_editorial_parser = subparsers.add_parser(
        "validate-editorial-overlays",
        help="Validate Stage 7 editorial overlay rows currently stored in DB.",
    )

    export_editorial_parser = subparsers.add_parser(
        "export-editorial-overlays",
        help="Export the latest Stage 7 editorial overlays as JSON.",
    )
    export_editorial_parser.add_argument("--output-path", type=Path)

    bootstrap_player_tenure_parser = subparsers.add_parser(
        "bootstrap-canonical-player-tenure",
        help="Apply the Stage 3 canonical player tenure bootstrap SQL.",
    )
    bootstrap_player_tenure_parser.add_argument(
        "--sql-path",
        type=Path,
        default=Path("sql/0003_player_tenure_bootstrap.sql"),
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

    if args.command == "bootstrap-canonical-pick-lifecycle":
        bootstrap_canonical_pick_lifecycle_schema(args.sql_path)
        return _emit({"command": args.command, "sql_path": str(args.sql_path), "status": "success"})

    if args.command == "bootstrap-canonical-event-asset-flow":
        bootstrap_canonical_event_asset_flow_schema(args.sql_path)
        return _emit({"command": args.command, "sql_path": str(args.sql_path), "status": "success"})

    if args.command == "bootstrap-presentation-contract":
        bootstrap_presentation_contract_schema(args.sql_path)
        return _emit({"command": args.command, "sql_path": str(args.sql_path), "status": "success"})

    if args.command == "bootstrap-editorial-overlays":
        bootstrap_editorial_overlay_schema(args.sql_path)
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

    if args.command == "validate-editorial-overlays":
        with _connect() as conn:
            editorial_result = fetch_editorial_overlays(conn)
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
                    """
                )
                event_rows = cur.fetchall()
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
                    """
                )
                asset_rows = cur.fetchall()

        from canonical.models import CanonicalAsset, CanonicalEvent

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
        report = validate_editorial_overlay_bundle(
            editorial_result,
            canonical_events=events,
            canonical_assets=assets,
        )
        return _emit(
            {
                "command": args.command,
                "status": "success" if report.ok else "validation_failed",
                "annotation_count": report.annotation_count,
                "calendar_marker_count": report.calendar_marker_count,
                "game_overlay_count": report.game_overlay_count,
                "era_count": report.era_count,
                "story_chapter_count": report.story_chapter_count,
                "errors": report.errors,
                "warnings": report.warnings,
            }
        )

    if args.command == "build-canonical-events":
        counts = build_and_persist_canonical_events(builder_version=args.builder_version)
        return _emit({"command": args.command, "status": "success", **counts})

    if args.command == "build-canonical-pick-lifecycle":
        counts = build_and_persist_canonical_pick_lifecycle(builder_version=args.builder_version)
        return _emit({"command": args.command, "status": "success", **counts})

    if args.command == "build-canonical-event-asset-flows":
        counts = build_and_persist_canonical_event_asset_flows(builder_version=args.builder_version)
        return _emit({"command": args.command, "status": "success", **counts})

    if args.command == "build-presentation-contract":
        counts = build_and_persist_presentation_contract(builder_version=args.builder_version)
        return _emit({"command": args.command, "status": "success", **counts})

    if args.command == "load-editorial-overlays":
        counts = build_and_persist_editorial_overlays(
            input_path=args.input_path,
            builder_version=args.builder_version,
        )
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
                    """,
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

    if args.command == "validate-canonical-pick-lifecycle":
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        pick_asset_id,
                        origin_team_code,
                        draft_year,
                        draft_round,
                        protection_summary,
                        protection_payload,
                        drafted_player_id,
                        current_pick_stage,
                        created_at,
                        updated_at
                    from canonical.pick_asset
                    order by created_at, pick_asset_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                pick_asset_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        pick_asset_provenance_id,
                        pick_asset_id,
                        source_record_id,
                        claim_id,
                        override_id,
                        provenance_role,
                        fallback_reason,
                        created_at
                    from canonical.pick_asset_provenance
                    order by created_at, pick_asset_provenance_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                pick_asset_provenance_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        pick_resolution_id,
                        pick_asset_id,
                        state_type,
                        effective_start_date,
                        effective_end_date,
                        overall_pick_number,
                        lottery_context,
                        drafted_player_id,
                        source_event_id,
                        state_payload,
                        created_at,
                        updated_at
                    from canonical.pick_resolution
                    order by created_at, pick_resolution_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                pick_resolution_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        pick_resolution_provenance_id,
                        pick_resolution_id,
                        source_record_id,
                        claim_id,
                        override_id,
                        provenance_role,
                        fallback_reason,
                        created_at
                    from canonical.pick_resolution_provenance
                    order by created_at, pick_resolution_provenance_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                pick_resolution_provenance_rows = cur.fetchall()
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
                    where pick_asset_id is not null
                    order by created_at, asset_id
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
                    where pick_asset_id is not null
                    order by created_at, asset_provenance_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                asset_provenance_rows = cur.fetchall()
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
                    order by created_at, player_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                player_identity_rows = cur.fetchall()
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

        from canonical.models import (
            AssetProvenance,
            CanonicalAsset,
            CanonicalEvent,
            CanonicalPickAsset,
            CanonicalPickResolution,
            CanonicalPlayerIdentity,
            PickAssetProvenance,
            PickResolutionProvenance,
        )

        pick_assets = [
            CanonicalPickAsset(
                pick_asset_id=row[0],
                origin_team_code=row[1],
                draft_year=row[2],
                draft_round=row[3],
                protection_summary=row[4],
                protection_payload=row[5],
                drafted_player_id=row[6],
                current_pick_stage=row[7],
                created_at=row[8],
                updated_at=row[9],
            )
            for row in pick_asset_rows
        ]
        pick_asset_provenance = [
            PickAssetProvenance(
                pick_asset_provenance_id=row[0],
                pick_asset_id=row[1],
                source_record_id=row[2],
                claim_id=row[3],
                override_id=row[4],
                provenance_role=row[5],
                fallback_reason=row[6],
                created_at=row[7],
            )
            for row in pick_asset_provenance_rows
        ]
        pick_resolutions = [
            CanonicalPickResolution(
                pick_resolution_id=row[0],
                pick_asset_id=row[1],
                state_type=row[2],
                effective_start_date=row[3],
                effective_end_date=row[4],
                overall_pick_number=row[5],
                lottery_context=row[6],
                drafted_player_id=row[7],
                source_event_id=row[8],
                state_payload=row[9],
                created_at=row[10],
                updated_at=row[11],
            )
            for row in pick_resolution_rows
        ]
        pick_resolution_provenance = [
            PickResolutionProvenance(
                pick_resolution_provenance_id=row[0],
                pick_resolution_id=row[1],
                source_record_id=row[2],
                claim_id=row[3],
                override_id=row[4],
                provenance_role=row[5],
                fallback_reason=row[6],
                created_at=row[7],
            )
            for row in pick_resolution_provenance_rows
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
        report = validate_canonical_pick_lifecycle(
            player_identities=player_identities,
            pick_assets=pick_assets,
            pick_asset_provenance_rows=pick_asset_provenance,
            pick_resolutions=pick_resolutions,
            pick_resolution_provenance_rows=pick_resolution_provenance,
            assets=assets,
            asset_provenance_rows=asset_provenance,
            events=events,
        )
        return _emit(
            {
                "command": args.command,
                "status": "success" if report.ok else "validation_failed",
                "pick_asset_count": report.pick_asset_count,
                "pick_asset_provenance_count": report.pick_asset_provenance_count,
                "pick_resolution_count": report.pick_resolution_count,
                "pick_resolution_provenance_count": report.pick_resolution_provenance_count,
                "asset_count": report.asset_count,
                "asset_provenance_count": report.asset_provenance_count,
                "errors": report.errors,
                "warnings": report.warnings,
            }
        )

    if args.command == "validate-canonical-event-asset-flows":
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
                        event_asset_flow_id,
                        event_id,
                        asset_id,
                        flow_direction,
                        flow_role,
                        flow_order,
                        effective_date,
                        created_at
                    from canonical.event_asset_flow
                    order by event_id, flow_order, event_asset_flow_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                flow_rows = cur.fetchall()
                cur.execute(
                    """
                    select
                        event_asset_flow_provenance_id,
                        event_asset_flow_id,
                        source_record_id,
                        claim_id,
                        override_id,
                        provenance_role,
                        fallback_reason,
                        created_at
                    from canonical.event_asset_flow_provenance
                    order by created_at, event_asset_flow_provenance_id
                    limit %s
                    """,
                    (args.sample_limit,),
                )
                provenance_rows = cur.fetchall()

        from canonical.models import CanonicalAsset, CanonicalEvent, CanonicalEventAssetFlow, EventAssetFlowProvenance

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
        flows = [
            CanonicalEventAssetFlow(
                event_asset_flow_id=row[0],
                event_id=row[1],
                asset_id=row[2],
                flow_direction=row[3],
                flow_role=row[4],
                flow_order=row[5],
                effective_date=row[6],
                created_at=row[7],
            )
            for row in flow_rows
        ]
        provenance = [
            EventAssetFlowProvenance(
                event_asset_flow_provenance_id=row[0],
                event_asset_flow_id=row[1],
                source_record_id=row[2],
                claim_id=row[3],
                override_id=row[4],
                provenance_role=row[5],
                fallback_reason=row[6],
                created_at=row[7],
            )
            for row in provenance_rows
        ]
        report = validate_canonical_event_asset_flows(events=events, assets=assets, flows=flows, provenance_rows=provenance)
        return _emit(
            {
                "command": args.command,
                "status": "success" if report.ok else "validation_failed",
                "event_count": report.event_count,
                "asset_count": report.asset_count,
                "flow_count": report.flow_count,
                "provenance_count": report.provenance_count,
                "errors": report.errors,
                "warnings": report.warnings,
            }
        )

    if args.command == "validate-presentation-contract":
        with _connect() as conn:
            result = fetch_presentation_contract(conn)
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

        from canonical.models import CanonicalEvent

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
        report = validate_presentation_contract(
            nodes=result.nodes,
            edges=result.edges,
            lanes=result.lanes,
            canonical_events=events,
        )
        return _emit(
            {
                "command": args.command,
                "status": "success" if report.ok else "validation_failed",
                "node_count": report.node_count,
                "edge_count": report.edge_count,
                "lane_count": report.lane_count,
                "errors": report.errors,
                "warnings": report.warnings,
            }
        )

    if args.command == "export-presentation-contract":
        payload = export_presentation_contract_json(args.output_path, include_editorial=args.include_editorial)
        if args.output_path is None:
            print(payload)
            return 0
        return _emit({"command": args.command, "status": "success", "output_path": str(args.output_path)})

    if args.command == "export-editorial-overlays":
        payload = export_editorial_overlays_json(args.output_path)
        if args.output_path is None:
            print(payload)
            return 0
        return _emit({"command": args.command, "status": "success", "output_path": str(args.output_path)})

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
