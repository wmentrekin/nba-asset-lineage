from __future__ import annotations

import shutil
from pathlib import Path

from nba_asset_lineage.files import ensure_dir, read_csv, write_csv, write_json
from nba_asset_lineage.settings import EXPECTED_RAW_FILES, INGESTED_RAW_DIR, MANUAL_RAW_DIR


def _write_template(path: Path, columns: list[str]) -> None:
    write_csv(path, [], columns)


def run_ingest(context: dict[str, str]) -> None:
    ensure_dir(MANUAL_RAW_DIR)
    ensure_dir(INGESTED_RAW_DIR)

    created_templates: list[str] = []
    copied_files: list[str] = []

    for file_name, expected_columns in EXPECTED_RAW_FILES.items():
        source_path = MANUAL_RAW_DIR / file_name
        if not source_path.exists():
            _write_template(source_path, expected_columns)
            created_templates.append(file_name)

        rows = read_csv(source_path)
        if rows:
            existing_columns = set(rows[0].keys())
            missing = [col for col in expected_columns if col not in existing_columns]
            if missing:
                joined = ", ".join(missing)
                raise ValueError(f"{file_name} missing columns: {joined}")

        destination_path = INGESTED_RAW_DIR / file_name
        shutil.copy2(source_path, destination_path)
        copied_files.append(file_name)

    report = {
        "team_code": context["team_code"],
        "start_date": context["start_date"],
        "end_date": context["end_date"],
        "manual_raw_dir": str(MANUAL_RAW_DIR),
        "ingested_raw_dir": str(INGESTED_RAW_DIR),
        "copied_files": copied_files,
        "created_templates": created_templates,
        "notes": "Non-API scraping is intentionally excluded from automated ingestion. Populate data/raw/manual/*.csv using approved sources.",
    }
    write_json(INGESTED_RAW_DIR / "ingest_report.json", report)

    if created_templates:
        created = ", ".join(created_templates)
        raise RuntimeError(
            "Created missing raw templates. Fill these files with source-backed data and rerun pipeline: "
            f"{created}"
        )
