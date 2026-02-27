from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nba_asset_lineage.bronze.io import load_raw_records
from nba_asset_lineage.bronze.raw_contract import RawAssetRecord, RawEventAssetLinkRecord, RawEventRecord
from nba_asset_lineage.db_config import load_db_config


def _payload_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_event(record: dict[str, Any], default_source_system: str) -> RawEventRecord:
    source_payload = record.get("source_payload") or record
    if not isinstance(source_payload, dict):
        raise ValueError("event source_payload must be an object")

    source_system = str(record.get("source_system") or default_source_system).strip()
    source_event_ref = str(record.get("source_event_ref") or record.get("event_key") or "").strip()
    if not source_event_ref:
        raise ValueError("event source_event_ref is required")

    return RawEventRecord(
        source_system=source_system,
        source_event_ref=source_event_ref,
        event_date_raw=str(record.get("event_date_raw") or record.get("event_date") or "").strip(),
        event_type_raw=str(record.get("event_type_raw") or record.get("event_type") or "").strip(),
        source_url=str(record.get("source_url") or "").strip(),
        source_payload=source_payload,
    )


def _normalize_asset(record: dict[str, Any], default_source_system: str) -> RawAssetRecord:
    source_payload = record.get("source_payload") or record
    if not isinstance(source_payload, dict):
        raise ValueError("asset source_payload must be an object")

    source_system = str(record.get("source_system") or default_source_system).strip()
    source_asset_ref = str(record.get("source_asset_ref") or record.get("asset_key") or "").strip()
    if not source_asset_ref:
        raise ValueError("asset source_asset_ref is required")

    return RawAssetRecord(
        source_system=source_system,
        source_asset_ref=source_asset_ref,
        asset_type_raw=str(record.get("asset_type_raw") or record.get("asset_type") or "").strip(),
        effective_date_raw=str(record.get("effective_date_raw") or record.get("event_date") or "").strip(),
        source_payload=source_payload,
    )


def _normalize_link(record: dict[str, Any], default_source_system: str) -> RawEventAssetLinkRecord:
    source_payload = record.get("source_payload") or record
    if not isinstance(source_payload, dict):
        raise ValueError("link source_payload must be an object")

    source_system = str(record.get("source_system") or default_source_system).strip()
    source_event_ref = str(record.get("source_event_ref") or record.get("event_key") or "").strip()
    source_asset_ref = str(record.get("source_asset_ref") or record.get("asset_key") or "").strip()
    if not source_event_ref or not source_asset_ref:
        raise ValueError("link source_event_ref and source_asset_ref are required")

    return RawEventAssetLinkRecord(
        source_system=source_system,
        source_event_ref=source_event_ref,
        source_asset_ref=source_asset_ref,
        action_raw=str(record.get("action_raw") or record.get("action") or "").strip(),
        direction_raw=str(record.get("direction_raw") or record.get("direction") or "").strip(),
        effective_date_raw=str(record.get("effective_date_raw") or record.get("event_date") or "").strip(),
        source_payload=source_payload,
    )


@dataclass(frozen=True)
class BronzeLoadSummary:
    run_mode: str
    source_system: str
    records_seen: int
    records_written: int
    status: str
    run_id: str | None
    notes: str


def run_bronze_load(
    *,
    raw_dir: Path,
    pipeline_name: str,
    run_mode: str,
    source_system: str,
    dry_run: bool,
) -> BronzeLoadSummary:
    raw_event_rows = load_raw_records(raw_dir, "events")
    raw_asset_rows = load_raw_records(raw_dir, "assets")
    raw_link_rows = load_raw_records(raw_dir, "event_asset_links")

    records_seen = len(raw_event_rows) + len(raw_asset_rows) + len(raw_link_rows)

    normalized_events = [_normalize_event(row, source_system) for row in raw_event_rows]
    normalized_assets = [_normalize_asset(row, source_system) for row in raw_asset_rows]
    normalized_links = [_normalize_link(row, source_system) for row in raw_link_rows]

    if dry_run:
        status = "no_new_data" if records_seen == 0 else "success"
        return BronzeLoadSummary(
            run_mode=run_mode,
            source_system=source_system,
            records_seen=records_seen,
            records_written=0,
            status=status,
            run_id=None,
            notes="Dry-run mode: validated and normalized raw input files without DB writes.",
        )

    if records_seen == 0:
        return BronzeLoadSummary(
            run_mode=run_mode,
            source_system=source_system,
            records_seen=0,
            records_written=0,
            status="no_new_data",
            run_id=None,
            notes="No raw Bronze records found. Expected files under data/bronze/raw/{events,assets,event_asset_links}/*.jsonl or *.json.",
        )

    config = load_db_config()

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for Bronze DB loading. Install dependencies first.") from exc

    with psycopg.connect(config.dsn) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bronze.ingest_runs (
                    pipeline_name, source_system, run_mode, status, started_at
                )
                values (%s, %s, %s, %s, %s)
                returning run_id
                """,
                (
                    pipeline_name,
                    source_system,
                    run_mode,
                    "running",
                    datetime.now(timezone.utc),
                ),
            )
            run_id = str(cur.fetchone()[0])

        records_written = 0
        try:
            with conn.cursor() as cur:
                for record in normalized_events:
                    cur.execute(
                        """
                        insert into bronze.raw_events (
                            ingest_run_id,
                            source_system,
                            source_event_ref,
                            event_date_raw,
                            event_type_raw,
                            source_url,
                            source_payload,
                            payload_hash
                        )
                        values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                        on conflict (source_system, source_event_ref, payload_hash) do nothing
                        returning raw_event_id
                        """,
                        (
                            run_id,
                            record.source_system,
                            record.source_event_ref,
                            record.event_date_raw,
                            record.event_type_raw,
                            record.source_url,
                            json.dumps(record.source_payload),
                            _payload_hash(record.source_payload),
                        ),
                    )
                    if cur.fetchone() is not None:
                        records_written += 1

                for record in normalized_assets:
                    cur.execute(
                        """
                        insert into bronze.raw_assets (
                            ingest_run_id,
                            source_system,
                            source_asset_ref,
                            asset_type_raw,
                            effective_date_raw,
                            source_payload,
                            payload_hash
                        )
                        values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                        on conflict (source_system, source_asset_ref, payload_hash) do nothing
                        returning raw_asset_id
                        """,
                        (
                            run_id,
                            record.source_system,
                            record.source_asset_ref,
                            record.asset_type_raw,
                            record.effective_date_raw,
                            json.dumps(record.source_payload),
                            _payload_hash(record.source_payload),
                        ),
                    )
                    if cur.fetchone() is not None:
                        records_written += 1

                for record in normalized_links:
                    cur.execute(
                        """
                        insert into bronze.raw_event_asset_links (
                            ingest_run_id,
                            source_system,
                            source_event_ref,
                            source_asset_ref,
                            action_raw,
                            direction_raw,
                            effective_date_raw,
                            source_payload,
                            payload_hash
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                        on conflict (source_system, source_event_ref, source_asset_ref, action_raw, payload_hash) do nothing
                        returning raw_link_id
                        """,
                        (
                            run_id,
                            record.source_system,
                            record.source_event_ref,
                            record.source_asset_ref,
                            record.action_raw,
                            record.direction_raw,
                            record.effective_date_raw,
                            json.dumps(record.source_payload),
                            _payload_hash(record.source_payload),
                        ),
                    )
                    if cur.fetchone() is not None:
                        records_written += 1

            status = "success" if records_written > 0 else "no_new_data"
            notes = (
                "Bronze load completed with inserts."
                if records_written > 0
                else "Bronze load completed. All records already present (idempotent no-op)."
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update bronze.ingest_runs
                    set status = %s,
                        finished_at = %s,
                        records_seen = %s,
                        records_written = %s,
                        notes = %s
                    where run_id = %s::uuid
                    """,
                    (
                        status,
                        datetime.now(timezone.utc),
                        records_seen,
                        records_written,
                        notes,
                        run_id,
                    ),
                )
            conn.commit()

            return BronzeLoadSummary(
                run_mode=run_mode,
                source_system=source_system,
                records_seen=records_seen,
                records_written=records_written,
                status=status,
                run_id=run_id,
                notes=notes,
            )
        except Exception as exc:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update bronze.ingest_runs
                    set status = %s,
                        finished_at = %s,
                        records_seen = %s,
                        records_written = %s,
                        error_text = %s
                    where run_id = %s::uuid
                    """,
                    (
                        "failed",
                        datetime.now(timezone.utc),
                        records_seen,
                        records_written,
                        str(exc),
                        run_id,
                    ),
                )
            conn.commit()
            raise
