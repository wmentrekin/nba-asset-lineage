from __future__ import annotations

import json
from datetime import datetime, timezone


def run_gold_publish(context: dict[str, str]) -> dict[str, object]:
    manifest = {
        "stage": "gold_publish",
        "status": "scaffold_ready",
        "franchise_id": context["franchise_id"],
        "scope_config_path": context["scope_config_path"],
        "start_date": context["start_date"],
        "end_date": context["end_date"],
        "run_mode": context["run_mode"],
        "as_of_date": context["as_of_date"],
        "notes": "Gold export generation not implemented yet. Target outputs: graph nodes/edges JSON, GraphML, and storyline-ready slices.",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(manifest, sort_keys=True))
    return manifest
