from __future__ import annotations

from pathlib import Path

import yaml


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def validate_required_columns(rows: list[dict[str, str]], required_columns: list[str], table_name: str) -> None:
    if not rows:
        return
    missing = [column for column in required_columns if column not in rows[0]]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"{table_name} missing required columns: {joined}")
