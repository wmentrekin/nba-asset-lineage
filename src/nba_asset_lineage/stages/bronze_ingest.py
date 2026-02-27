from __future__ import annotations

from datetime import datetime, timezone

from nba_asset_lineage.bronze.loader import run_bronze_load
from nba_asset_lineage.files import ensure_dir, write_json
from nba_asset_lineage.settings import BRONZE_CHECKPOINTS_DIR, BRONZE_RAW_DIR


def run_bronze_ingest(context: dict[str, str]) -> None:
    ensure_dir(BRONZE_RAW_DIR)
    ensure_dir(BRONZE_CHECKPOINTS_DIR)

    summary = run_bronze_load(
        raw_dir=BRONZE_RAW_DIR,
        pipeline_name="bronze_ingest",
        run_mode=context["run_mode"],
        source_system=context["source_system"],
        dry_run=context["dry_run"] == "true",
    )

    manifest = {
        "stage": "bronze_ingest",
        "status": summary.status,
        "franchise_id": context["franchise_id"],
        "scope_config_path": context["scope_config_path"],
        "start_date": context["start_date"],
        "end_date": context["end_date"],
        "run_mode": context["run_mode"],
        "as_of_date": context["as_of_date"],
        "source_system": context["source_system"],
        "dry_run": context["dry_run"] == "true",
        "records_seen": summary.records_seen,
        "records_written": summary.records_written,
        "run_id": summary.run_id,
        "notes": summary.notes,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(BRONZE_CHECKPOINTS_DIR / "bronze_stage_manifest.json", manifest)
