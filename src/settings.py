from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = ROOT / "configs"
SQL_DIR = ROOT / "sql"

# Local optional paths (not required for DB-backed Bronze/Silver).
DEFAULT_BRONZE_RAW_DIR = Path("/tmp/nba-asset-lineage/raw")
DEFAULT_EXPORTS_DIR = ROOT / "exports"

DEFAULT_FRANCHISE_ID = "grizzlies"
DEFAULT_START_DATE = "1995-06-23"
DEFAULT_END_DATE = date.today().isoformat()
DEFAULT_SCOPE_CONFIG_PATH = CONFIGS_DIR / "lineage_scope.yaml"

DEFAULT_ALLOWED_EVENT_TYPES = {
    "trade",
    "draft_pick",
    "contract_signing",
    "extension",
    "re_signing",
    "conversion",
    "waiver",
}

DEFAULT_ALLOWED_ACTIONS = {
    "acquire",
    "relinquish",
    "modify",
    "terminate",
    "transform",
}
