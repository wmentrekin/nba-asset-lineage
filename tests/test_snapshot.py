"""Tests for lineage.snapshot: loading and person-id resolution."""

import datetime as dt

import pytest

from lineage.parse import feed_rows
from lineage.snapshot import (
    Snapshot,
    UnresolvedPlayerError,
    load_snapshot,
    pick_id_for,
    resolve_person_ids,
)

from tests.conftest import DATA_DIR

SNAPSHOT_PATH = DATA_DIR / "opening_snapshot_2025_26.json"


def test_load_snapshot_reads_the_curated_file():
    snapshot = load_snapshot(SNAPSHOT_PATH)

    assert snapshot.team == "MEM"
    assert snapshot.season == "2025-26"
    assert snapshot.as_of == dt.date(2025, 10, 22)
    assert len(snapshot.players) == 18
    assert len(snapshot.picks) == 15


def test_pick_ids_are_built_from_the_natural_key():
    snapshot = load_snapshot(SNAPSHOT_PATH)
    pick_ids = [pick.pick_id for pick in snapshot.picks]

    assert "2026-R1-MEM" in pick_ids
    assert "2030-R1-ORL" in pick_ids
    assert len(set(pick_ids)) == len(pick_ids)


def test_pick_id_for_rejects_a_bad_round_or_team():
    with pytest.raises(ValueError):
        pick_id_for(2030, 3, "MEM")
    with pytest.raises(ValueError, match="tricode"):
        pick_id_for(2030, 1, "ZZZ")


def test_resolve_person_ids_keeps_curated_ids(feed_payload):
    snapshot = Snapshot.model_validate(
        {
            "team": "MEM",
            "season": "2025-26",
            "as_of": "2025-10-22",
            "players": [
                {"person_id": 1629630, "name": "Ja Morant", "contract_type": "standard"}
            ],
            "picks": [],
        }
    )

    assert resolve_person_ids(snapshot, feed_rows(feed_payload)) == {"Ja Morant": 1629630}


def test_resolve_person_ids_resolves_a_null_id_by_name_and_by_slug(feed_payload):
    rows = feed_rows(feed_payload)
    snapshot = Snapshot.model_validate(
        {
            "team": "MEM",
            "season": "2025-26",
            "as_of": "2025-10-22",
            "players": [
                # exact full-name match against a feed description
                {"person_id": None, "name": "Jock Landale", "contract_type": "standard"},
                # name whose slug, not its spelling, is what the feed carries
                {"person_id": None, "name": "PJ Hall", "contract_type": "two_way"},
            ],
            "picks": [],
        }
    )

    assert resolve_person_ids(snapshot, rows) == {
        "Jock Landale": 1629111,
        "PJ Hall": 1641790,
    }


def test_resolve_person_ids_fails_loudly_naming_the_player(feed_payload):
    # Built here rather than relying on data/opening_snapshot_2025_26.json having an
    # unresolved row: Jaylen Wells never appears by name or slug in the captured fixture,
    # so nulling his person_id on a copy of the loaded snapshot reliably exercises this.
    snapshot = load_snapshot(SNAPSHOT_PATH).model_copy(deep=True)
    wells = next(player for player in snapshot.players if player.name == "Jaylen Wells")
    wells.person_id = None

    with pytest.raises(UnresolvedPlayerError) as excinfo:
        resolve_person_ids(snapshot, feed_rows(feed_payload))

    assert "Jaylen Wells" in str(excinfo.value)
    assert "opening_snapshot_2025_26.json" in str(excinfo.value)
