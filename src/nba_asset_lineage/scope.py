from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nba_asset_lineage.settings import DEFAULT_SCOPE_CONFIG_PATH


@dataclass(frozen=True)
class ScopeConfig:
    franchise_id: str
    scope_name: str
    start_date: str
    end_date: str
    operating_team_timeline: list[dict[str, Any]]
    allowed_event_types: list[str]
    source_system_priority: list[str]
    notes: str


def load_scope_config(path: Path | None = None) -> ScopeConfig:
    resolved = path or DEFAULT_SCOPE_CONFIG_PATH
    payload: dict[str, Any]
    with resolved.open("r", encoding="utf-8") as handle:
        content = handle.read()

    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(content)
    except ModuleNotFoundError:
        # Fallback for minimal Python environments without PyYAML.
        # The scope file is kept JSON-compatible YAML so json parsing works.
        payload = json.loads(content)

    return ScopeConfig(
        franchise_id=payload["franchise_id"],
        scope_name=payload.get("scope_name", "default_scope"),
        start_date=payload["start_date"],
        end_date=payload.get("end_date", "rolling"),
        operating_team_timeline=payload.get("operating_team_timeline", []),
        allowed_event_types=payload.get("allowed_event_types", []),
        source_system_priority=payload.get("source_system_priority", []),
        notes=payload.get("notes", ""),
    )
