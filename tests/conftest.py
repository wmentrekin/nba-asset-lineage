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


@pytest.fixture
def curated_inputs():
    return load_inputs(DATA_DIR)


@pytest.fixture
def resolvable_inputs(curated_inputs):
    """The real data files, every snapshot person_id already filled in."""
    return curated_inputs
