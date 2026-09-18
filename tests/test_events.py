"""Tests for lineage.picks: loading curated pick truth and pick-id parsing."""

import datetime as dt

import pytest

from lineage.picks import (
    PickEventsError,
    draft_transaction_id,
    load_pick_events,
    parse_pick_id,
)

from tests.conftest import DATA_DIR

PICK_EVENTS_PATH = DATA_DIR / "pick_events.json"


def test_load_pick_events_reads_the_curated_file():
    pick_events = load_pick_events(PICK_EVENTS_PATH)

    assert [trade.group_key for trade in pick_events.trades] == [
        "Trade 2025022",
        "Trade 2025037",
        "Trade 2026006",
        "Trade 2026014",
    ]
    # Nothing is curated yet, so every trade is an uncurated draft consideration.
    assert all(trade.picks == [] for trade in pick_events.trades)
    assert len(pick_events.draft_selections) == 2
    assert all(selection.is_todo for selection in pick_events.draft_selections)


def test_pick_move_reads_the_from_and_to_aliases():
    from lineage.picks import PickMove

    move = PickMove.model_validate(
        {
            "pick_id": "2030-R1-ORL",
            "from": "ORL",
            "to": "MEM",
            "protections": "top-5 protected",
            "source_url": "https://example.com/trade",
        }
    )

    assert (move.from_holder, move.to_holder) == ("ORL", "MEM")
    assert move.protections == "top-5 protected"


@pytest.mark.parametrize(
    ("pick_id", "expected"),
    [
        ("2026-R1-MEM", (2026, 1, "MEM")),
        ("2030-R2-ORL", (2030, 2, "ORL")),
    ],
)
def test_parse_pick_id(pick_id, expected):
    assert parse_pick_id(pick_id) == expected


@pytest.mark.parametrize(
    "pick_id", ["TODO", "2026-R3-MEM", "26-R1-MEM", "2026-R1-ZZZ", "2026-R1-mem"]
)
def test_parse_pick_id_rejects_junk(pick_id):
    with pytest.raises(ValueError):
        parse_pick_id(pick_id)


def test_draft_transaction_id():
    from lineage.picks import DraftSelection

    selection = DraftSelection(
        date=dt.date(2026, 6, 24),
        pick_id="2026-R1-MEM",
        player_id=1643409,
        player_name="Cameron Boozer",
    )

    assert draft_transaction_id(selection) == "Draft-2026-06-24-1643409"


def test_pick_events_error_is_a_value_error():
    assert issubclass(PickEventsError, ValueError)
