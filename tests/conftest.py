"""Shared offline fixtures: the captured feed payload and the curated data files."""

import json
from pathlib import Path

import pytest

from lineage.derive import load_inputs

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
FEED_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "nba_player_movement_mem_2025_26.json"

# Jaylen Wells' snapshot row has person_id null and his only feed appearance (a 2024
# rookie-scale signing) predates the captured window, so the fixture cannot resolve him.
# Tests substitute an obviously-fake id; see the T3.2 blocker note.
PLACEHOLDER_PERSON_ID = -1


@pytest.fixture
def feed_payload():
    return json.loads(FEED_FIXTURE.read_text())


@pytest.fixture
def curated_inputs():
    return load_inputs(DATA_DIR)


@pytest.fixture
def resolvable_inputs(curated_inputs):
    """The real data files with unresolvable snapshot person_ids stubbed out."""
    snapshot, pick_events, corrections = curated_inputs
    for player in snapshot.players:
        if player.person_id is None:
            player.person_id = PLACEHOLDER_PERSON_ID
    return snapshot, pick_events, corrections
