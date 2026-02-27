from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EXPORTS_DIR = DATA_DIR / "exports"
SCHEMAS_DIR = ROOT / "schemas"

MANUAL_RAW_DIR = RAW_DIR / "manual"
INGESTED_RAW_DIR = RAW_DIR / "ingested"

DEFAULT_TEAM_CODE = "MEM"
DEFAULT_TEAM_NAME = "Memphis Grizzlies"
DEFAULT_START_DATE = "2022-05-14"
DEFAULT_END_DATE = "2026-02-26"

START_STATE_NODE_PREFIX = "state_start"
END_STATE_NODE_PREFIX = "state_end"

EXPECTED_RAW_FILES = {
    "initial_assets.csv": [
        "asset_key",
        "asset_type",
        "subtype",
        "player_name",
        "contract_expiry_year",
        "average_annual_salary",
        "acquisition_method",
        "original_team",
        "pick_year",
        "pick_number",
        "protections_raw",
        "protections_structured",
        "swap_conditions_raw",
        "swap_conditions_structured",
        "start_date",
        "source_id",
    ],
    "events.csv": [
        "event_key",
        "event_date",
        "event_type",
        "event_label",
        "description",
        "source_id",
    ],
    "event_assets.csv": [
        "event_key",
        "action",
        "asset_key",
        "asset_type",
        "subtype",
        "player_name",
        "contract_expiry_year",
        "average_annual_salary",
        "acquisition_method",
        "original_team",
        "pick_year",
        "pick_number",
        "protections_raw",
        "protections_structured",
        "swap_conditions_raw",
        "swap_conditions_structured",
        "prior_transactions",
    ],
    "sources.csv": [
        "source_id",
        "source_name",
        "source_url",
        "retrieved_date",
        "notes",
    ],
}

ALLOWED_EVENT_TYPES = {
    "trade",
    "draft_pick",
    "contract_signing",
    "extension",
    "re_signing",
    "conversion",
    "waiver",
}

ALLOWED_ACTIONS = {
    "acquire",
    "relinquish",
    "modify",
    "terminate",
}
