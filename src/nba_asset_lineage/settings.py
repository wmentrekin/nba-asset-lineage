from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
CONFIGS_DIR = ROOT / "configs"
SCHEMAS_DIR = ROOT / "schemas"
SQL_DIR = ROOT / "sql"

# Medallion layout.
BRONZE_DIR = DATA_DIR / "bronze"
BRONZE_RAW_DIR = BRONZE_DIR / "raw"
BRONZE_CHECKPOINTS_DIR = BRONZE_DIR / "checkpoints"

SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
GOLD_EXPORTS_DIR = GOLD_DIR / "exports"

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
