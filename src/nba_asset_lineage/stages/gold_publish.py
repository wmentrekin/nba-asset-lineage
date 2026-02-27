from __future__ import annotations

from datetime import datetime, timezone

from nba_asset_lineage.files import ensure_dir, write_json
from nba_asset_lineage.settings import GOLD_DIR, GOLD_EXPORTS_DIR


def run_gold_publish(context: dict[str, str]) -> None:
    ensure_dir(GOLD_DIR)
    ensure_dir(GOLD_EXPORTS_DIR)

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
    write_json(GOLD_DIR / "gold_stage_manifest.json", manifest)
