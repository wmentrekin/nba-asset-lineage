from __future__ import annotations

from datetime import datetime, timezone

from nba_asset_lineage.files import ensure_dir, write_json
from nba_asset_lineage.settings import SILVER_DIR


def run_silver_transform(context: dict[str, str]) -> None:
    ensure_dir(SILVER_DIR)

    manifest = {
        "stage": "silver_transform",
        "status": "scaffold_ready",
        "franchise_id": context["franchise_id"],
        "scope_config_path": context["scope_config_path"],
        "start_date": context["start_date"],
        "end_date": context["end_date"],
        "run_mode": context["run_mode"],
        "as_of_date": context["as_of_date"],
        "notes": "Silver transformations not implemented yet. Canonical events/assets/lineage tables are expected in Supabase.",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(SILVER_DIR / "silver_stage_manifest.json", manifest)
