"""Shared offline fixtures: the captured feed payload and the curated data files."""

import json
from pathlib import Path

import pytest

from lineage.derive import load_inputs

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
FEED_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "nba_player_movement_mem_2025_26.json"


@pytest.fixture
def feed_payload():
    return json.loads(FEED_FIXTURE.read_text())


# Verbatim from the full cumulative feed: the position word is missing, leaving a double
# space. It is a Denver row, so nothing in the Memphis graph depends on it - but it sits in
# the same payload the identity index scans, and it used to stop the whole derivation.
MALFORMED_NON_MEMPHIS_ROW = {
    "GroupSort": "Signing 1160001",
    "TEAM_ID": 1610612743.0,
    "Additional_Sort": 0.0,
    "PLAYER_ID": 1641801.0,
    "PLAYER_SLUG": "bryce-hopkins",
    "TEAM_SLUG": "nuggets",
    "TRANSACTION_DATE": "2026-01-15T00:00:00",
    "Transaction_Type": "Signing",
    "TRANSACTION_DESCRIPTION": (
        "Denver Nuggets signed  Bryce Hopkins to a Two-Way Contract."
    ),
}


@pytest.fixture
def feed_payload_with_malformed_row(feed_payload):
    """The captured fixture plus one unreadable row from an unrelated team."""
    feed_payload["NBA_Player_Movement"]["rows"].append(MALFORMED_NON_MEMPHIS_ROW)
    return feed_payload


# Training-camp cuts as the November feed carries them: the camp signing itself is absent.
# Collins was never signed by Memphis in the feed; Lovering's last Memphis movement is his
# February 10-day, which expires to FA long before this waiver.
COLLINS_CAMP_CUT_ROW = {
    "TEAM_ID": 1610612763.0,
    "GroupSort": "Waive 1154381",
    "PLAYER_ID": 1641879.0,
    "TEAM_SLUG": "grizzlies",
    "PLAYER_SLUG": "yuri-collins",
    "Additional_Sort": 0.0,
    "TRANSACTION_DATE": "2026-09-26T00:00:00",
    "Transaction_Type": "Waive",
    "TRANSACTION_DESCRIPTION": "Memphis Grizzlies waived guard Yuri Collins.",
}
LOVERING_CAMP_CUT_ROW = {
    "TEAM_ID": 1610612763.0,
    "GroupSort": "Waive 1154444",
    "PLAYER_ID": 1643133.0,
    "TEAM_SLUG": "grizzlies",
    "PLAYER_SLUG": "lawson-lovering",
    "Additional_Sort": 0.0,
    "TRANSACTION_DATE": "2026-09-28T00:00:00",
    "Transaction_Type": "Waive",
    "TRANSACTION_DESCRIPTION": "Memphis Grizzlies waived center Lawson Lovering.",
}
SAUNDERS_TWO_WAY_SIGNING_ROW = {
    "TEAM_ID": 1610612763.0,
    "GroupSort": "Signing 1157609",
    "PLAYER_ID": 1643563.0,
    "TEAM_SLUG": "grizzlies",
    "PLAYER_SLUG": "richie-saunders",
    "Additional_Sort": 0.0,
    "TRANSACTION_DATE": "2026-11-07T00:00:00",
    "Transaction_Type": "Signing",
    "TRANSACTION_DESCRIPTION": (
        "Memphis Grizzlies signed guard Richie Saunders to a Two-Way Contract."
    ),
}


@pytest.fixture
def feed_payload_with_camp_cuts(feed_payload):
    """The captured fixture plus two camp-cut waivers of players Memphis does not hold."""
    feed_payload["NBA_Player_Movement"]["rows"] += [
        COLLINS_CAMP_CUT_ROW,
        LOVERING_CAMP_CUT_ROW,
    ]
    return feed_payload


@pytest.fixture
def curated_inputs():
    return load_inputs(DATA_DIR)


@pytest.fixture
def resolvable_inputs(curated_inputs):
    """The real data files, every snapshot person_id already filled in."""
    return curated_inputs
