"""Tests for lineage.events: loading curated trade/draft/event truth and pick-id parsing."""

import datetime as dt

import pytest

from lineage.events import (
    CuratedEventsError,
    DraftSelection,
    draft_transaction_id,
    load_curated_events,
    parse_pick_id,
    synthetic_player_id,
)

from tests.conftest import DATA_DIR

CURATED_EVENTS_PATH = DATA_DIR / "curated_events.json"


def test_load_curated_events_reads_the_curated_file():
    curated = load_curated_events(CURATED_EVENTS_PATH)

    assert [trade.group_key for trade in curated.trades] == [
        "Trade 2025022",
        "Trade 2025037",
        "Trade 2025063",
        "Trade 2026006",
        "Trade 2026014",
    ]
    assert len(curated.draft_selections) == 3
    assert len(curated.events) == 1
    assert curated.events[0].kind == "contract_void"


def test_pick_in_reads_the_from_alias():
    from lineage.events import PickIn

    pick_in = PickIn.model_validate(
        {
            "pick_id": "2030-R1-ORL",
            "from": "ORL",
            "protections": "top-5 protected",
            "source_url": "https://example.com/trade",
            "verified": True,
            "confidence": "high",
        }
    )

    assert pick_in.from_holder == "ORL"
    assert pick_in.protections == "top-5 protected"


def test_pick_out_reads_the_to_alias():
    from lineage.events import PickOut

    pick_out = PickOut.model_validate(
        {
            "pick_id": "2030-R1-ORL",
            "to": "ORL",
            "protections": None,
            "source_url": None,
            "verified": True,
            "confidence": "high",
        }
    )

    assert pick_out.to_holder == "ORL"


def test_trade_entry_forbids_unknown_fields():
    from lineage.events import TradeEntry

    with pytest.raises(ValueError):
        TradeEntry.model_validate(
            {
                "group_key": "Trade 2025022",
                "date": "2026-02-03",
                "counterparty": "UTA",
                "verified": True,
                "confidence": "high",
                "picks_in": [],
                "picks_out": [],
                "footnotes": [],
                "unexpected": "nope",
            }
        )


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
    selection = DraftSelection(
        date=dt.date(2026, 6, 24),
        pick_no=32,
        pick_id="2026-R2-MEM",
        player_id=None,
        player_name="Richie Saunders",
    )

    assert draft_transaction_id(selection) == "Draft-2026-06-24-2026-R2-MEM"


def test_synthetic_player_id_is_deterministic_and_negative():
    selection = DraftSelection(
        date=dt.date(2026, 6, 24),
        pick_no=32,
        pick_id="2026-R2-MEM",
        player_id=None,
        player_name="Richie Saunders",
    )

    assert synthetic_player_id(selection) == -202632


def test_curated_events_error_is_a_value_error():
    assert issubclass(CuratedEventsError, ValueError)
