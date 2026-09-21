"""Tests for lineage.timeline: ordering, placeholder resolution and holder intervals."""

import datetime as dt

from lineage.timeline import (
    Movement,
    Segment,
    build_timelines,
    movement_sort_key,
    resolve_from_holders,
    sorted_movements,
)

DAY_ONE = dt.date(2025, 10, 22)
DAY_TWO = dt.date(2026, 2, 3)


def movement(**overrides) -> Movement:
    defaults = {
        "transaction_id": "T1",
        "occurred_on": DAY_ONE,
        "asset_type": "player",
        "asset_id": "1",
        "to_holder": "MEM",
    }
    return Movement(**{**defaults, **overrides})


def test_sort_key_is_date_then_transaction_then_row_id():
    first = movement(transaction_id="B", sequence=1)
    second = movement(transaction_id="A", occurred_on=DAY_TWO, sequence=2)
    third = movement(transaction_id="B", sequence=3)

    assert movement_sort_key(first) == (DAY_ONE, "B", 1)
    assert sorted_movements([second, third, first]) == [first, third, second]


def test_baseline_origin_keeps_a_null_from_holder():
    baseline = movement(transaction_id="OPENING-2025-26", sequence=1)

    (resolved,) = resolve_from_holders([baseline])

    assert resolved.from_holder is None


def test_placeholder_takes_the_previous_to_holder():
    baseline = movement(transaction_id="OPENING-2025-26", sequence=1, contract_type="two_way")
    resigning = movement(
        transaction_id="Signing-1",
        occurred_on=DAY_TWO,
        sequence=2,
        from_holder_placeholder=True,
        entering_holder="FA",
        contract_type="standard",
    )

    _, resolved = resolve_from_holders([baseline, resigning])

    assert resolved.from_holder == "MEM"
    assert resolved.from_holder_placeholder is False
    assert resolved.entering_holder is None


def test_placeholder_with_no_history_takes_the_entering_holder():
    signing = movement(
        transaction_id="Signing-1",
        sequence=1,
        from_holder_placeholder=True,
        entering_holder="FA",
        contract_type="ten_day",
    )

    (resolved,) = resolve_from_holders([signing])

    assert resolved.from_holder == "FA"


def test_resolution_is_per_asset():
    first_asset = movement(asset_id="1", transaction_id="OPENING-2025-26", sequence=1)
    second_asset = movement(
        asset_id="2",
        transaction_id="Signing-1",
        occurred_on=DAY_TWO,
        sequence=2,
        from_holder_placeholder=True,
        entering_holder="FA",
    )

    resolved = {m.asset_id: m for m in resolve_from_holders([first_asset, second_asset])}

    assert resolved["1"].from_holder is None
    assert resolved["2"].from_holder == "FA"


def test_build_timelines_closes_each_segment_with_the_next_transaction():
    baseline = movement(
        transaction_id="OPENING-2025-26", sequence=1, contract_type="standard"
    )
    trade = movement(
        transaction_id="Trade-2025022",
        occurred_on=DAY_TWO,
        sequence=2,
        from_holder="MEM",
        to_holder="UTA",
    )

    timelines = build_timelines([trade, baseline])

    assert timelines == {
        ("player", "1"): [
            Segment(
                from_node="OPENING-2025-26",
                to_node="Trade-2025022",
                holder="MEM",
                contract_type="standard",
            ),
            Segment(
                from_node="Trade-2025022",
                to_node=None,
                holder="UTA",
                contract_type=None,
            ),
        ]
    }


def test_build_timelines_separates_picks_from_players():
    player = movement(asset_type="player", asset_id="1", sequence=1)
    pick = movement(asset_type="pick", asset_id="2026-R1-MEM", sequence=2)

    timelines = build_timelines([player, pick])

    assert set(timelines) == {("player", "1"), ("pick", "2026-R1-MEM")}
