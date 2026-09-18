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


@pytest.fixture
def curated_inputs():
    return load_inputs(DATA_DIR)


@pytest.fixture
def resolvable_inputs(curated_inputs):
    """The real data files, every snapshot person_id already filled in."""
    return curated_inputs
