"""Tests for lineage.parse against the captured Memphis player-movement fixture."""

import datetime as dt

import pytest

from lineage.parse import (
    DraftConsideration,
    FeedParseError,
    Group,
    classify,
    contract_type,
    feed_rows,
    group_to_transaction,
    memphis_groups,
    player_name_from_description,
    slugify_name,
    transaction_id,
    try_player_name_from_description,
)

WINDOW_START = dt.date(2025, 10, 22)

EXPECTED_KINDS = {
    "Signing 1135682": "signing",
    "Signing 1135806": "two_way_signing",
    "Signing 1135851": "signing",
    "Signing 1135856": "signing",
    "Signing 1135871": "signing",
    "Signing 1135875": "signing",
    "Signing 1135877": "signing",
    "Signing 1135917": "two_way_signing",
    "Signing 1136449": "two_way_signing",
    "Signing 1139430": "ten_day",
    "Signing 1140528": "two_way_signing",
    "Signing 1141169": "ten_day",
    "Signing 1142557": "ten_day",
    "Signing 1143016": "ten_day",
    "Signing 1145049": "ten_day",
    "Signing 1145858": "ten_day",
    "Signing 1146113": "signing",
    "Signing 1146537": "signing",
    "Signing 1146538": "two_way_signing",
    "Signing 1146960": "ten_day",
    "Signing 1147037": "ten_day",
    "Signing 1147490": "ten_day",
    "Signing 1147491": "ten_day",
    "Signing 1147703": "ten_day",
    "Signing 1147883": "ten_day",
    "Signing 1147950": "ten_day",
    "Signing 1147951": "ten_day",
    "Signing 1148392": "ten_day",
    "Signing 1148495": "ten_day",
    "Signing 1153039": "signing",
    "Signing 1153118": "signing",
    "Signing 1153251": "signing",
    "Trade 2024042": "trade",
    "Trade 2025003": "trade",
    "Trade 2025022": "trade",
    "Trade 2025037": "trade",
    "Trade 2025063": "trade",
    "Trade 2026006": "trade",
    "Trade 2026014": "trade",
    "Waive 1135841": "waiver",
    "Waive 1135916": "waiver",
    "Waive 1137300": "waiver",
    "Waive 1137885": "waiver",
    "Waive 1138135": "waiver",
    "Waive 1138136": "waiver",
    "Waive 1138137": "waiver",
    "Waive 1138138": "waiver",
    "Waive 1140530": "waiver",
    "Waive 1144740": "waiver",
    "Waive 1144932": "waiver",
    "Waive 1146134": "waiver",
    "Waive 1153232": "waiver",
}


@pytest.fixture
def all_groups(feed_payload):
    """Every fixture group, unfiltered by date, keyed by GroupSort."""
    rows = feed_rows(feed_payload)
    groups = memphis_groups(rows, dt.date(2000, 1, 1))
    return {group.group_key: group for group in groups}


def test_fixture_has_the_captured_row_count(feed_payload):
    assert len(feed_rows(feed_payload)) == 86


def test_classify_every_fixture_group(all_groups):
    assert {key: classify(group) for key, group in all_groups.items()} == EXPECTED_KINDS


def test_unknown_transaction_type_raises():
    rows = feed_rows(
        {
            "NBA_Player_Movement": {
                "rows": [
                    {
                        "GroupSort": "Mystery 1",
                        "TEAM_ID": 1610612763.0,
                        "Additional_Sort": 0.0,
                        "PLAYER_ID": 1.0,
                        "PLAYER_SLUG": "x",
                        "TEAM_SLUG": "grizzlies",
                        "TRANSACTION_DATE": "2026-01-01T00:00:00",
                        "Transaction_Type": "Teleported",
                        "TRANSACTION_DESCRIPTION": "Memphis Grizzlies teleported guard X.",
                    }
                ]
            }
        }
    )
    with pytest.raises(FeedParseError, match="Teleported"):
        classify(Group(group_key="Mystery 1", rows=tuple(rows)))


def _single_row_group(group_key, transaction_type, description):
    rows = feed_rows(
        {
            "NBA_Player_Movement": {
                "rows": [
                    {
                        "GroupSort": group_key,
                        "TEAM_ID": 1610612763.0,
                        "Additional_Sort": 0.0,
                        "PLAYER_ID": 1.0,
                        "PLAYER_SLUG": "x",
                        "TEAM_SLUG": "grizzlies",
                        "TRANSACTION_DATE": "2026-01-01T00:00:00",
                        "Transaction_Type": transaction_type,
                        "TRANSACTION_DESCRIPTION": description,
                    }
                ]
            }
        }
    )
    return Group(group_key=group_key, rows=tuple(rows))


def test_classify_contract_converted():
    group = _single_row_group(
        "ContractConverted 1",
        "ContractConverted",
        "Toronto Raptors converted the contract of guard A.J. Lawson to an NBA Contract.",
    )
    assert classify(group) == "two_way_conversion"


def test_classify_award_on_waivers():
    group = _single_row_group(
        "AwardOnWaivers 1",
        "AwardOnWaivers",
        "Memphis Grizzlies claimed guard Tony Wroten off waivers.",
    )
    assert classify(group) == "signing"


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Memphis Grizzlies signed guard Ty Jerome to a Contract.", "standard"),
        ("Memphis Grizzlies re-signed guard Javon Small to a Two-Way Contract.", "two_way"),
        ("Memphis Grizzlies signed center Charles Bassey to a 10-Day Contract.", "ten_day"),
        (
            "Memphis Grizzlies re-signed guard Cedric Coward to a Rookie Scale Contract.",
            "standard",
        ),
        (
            "Memphis Grizzlies signed forward Taj Gibson to a Rest-of-Season Contract.",
            "standard",
        ),
        (
            "Memphis Grizzlies re-signed forward Jaren Jackson Jr. to a Veteran Extension.",
            "standard",
        ),
        # The other two real signing tails, per the full ~9,800-row feed history: Rookie
        # Scale Extension (101 occurrences) and Substitute Player Contract (15).
        (
            "Memphis Grizzlies signed forward Sample Player to a Rookie Scale Extension.",
            "standard",
        ),
        (
            "Memphis Grizzlies signed guard Sample Player to a Substitute Player Contract.",
            "standard",
        ),
    ],
)
def test_contract_type(description, expected):
    assert contract_type(description) == expected


def test_contract_type_raises_on_unknown_phrasing():
    with pytest.raises(FeedParseError):
        contract_type("Memphis Grizzlies signed guard X to a Vibes Agreement.")


def test_every_fixture_description_yields_a_name_matching_its_slug(feed_payload):
    itemized = [row for row in feed_rows(feed_payload) if row.player_id > 0]
    assert len(itemized) == 75
    for row in itemized:
        name = player_name_from_description(row.description)
        assert name
        assert slugify_name(name) == row.player_slug, row.description


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (
            "Memphis Grizzlies received guard Kentavious Caldwell-Pope from Orlando Magic.",
            "Kentavious Caldwell-Pope",
        ),
        (
            "Memphis Grizzlies received guard D'Angelo Russell from Washington Wizards.",
            "D'Angelo Russell",
        ),
        (
            "Memphis Grizzlies received guard Walter Clayton Jr. from Utah Jazz.",
            "Walter Clayton Jr.",
        ),
        # Note the doubled period: the suffix's period plus the sentence terminator.
        ("Memphis Grizzlies waived guard Charlie Brown Jr..", "Charlie Brown Jr."),
        (
            "Memphis Grizzlies re-signed forward Jaren Jackson Jr. to a Veteran Extension.",
            "Jaren Jackson Jr.",
        ),
        ("Memphis Grizzlies waived forward Tyler Burton.", "Tyler Burton"),
        (
            "Memphis Grizzlies received guard-forward Sample Name from Utah Jazz.",
            "Sample Name",
        ),
        # AwardOnWaivers: the name extractor must stop at " off waivers".
        (
            "Memphis Grizzlies claimed guard Tony Wroten off waivers.",
            "Tony Wroten",
        ),
        # ContractConverted: note the "to an" article, not "to a".
        (
            "Toronto Raptors converted the contract of guard A.J. Lawson to an NBA "
            "Contract.",
            "A.J. Lawson",
        ),
    ],
)
def test_player_name_from_description(description, expected):
    assert player_name_from_description(description) == expected


def test_player_name_reads_a_missing_position_word_from_the_double_space():
    # The full feed really contains this row; the position word is simply absent.
    assert (
        player_name_from_description(
            "Denver Nuggets signed  Bryce Hopkins to a Two-Way Contract."
        )
        == "Bryce Hopkins"
    )
    assert (
        player_name_from_description("Denver Nuggets waived  Bryce Hopkins.")
        == "Bryce Hopkins"
    )


def test_player_name_requires_a_readable_description():
    with pytest.raises(FeedParseError):
        player_name_from_description("Memphis Grizzlies did something inscrutable.")


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Memphis Grizzlies waived forward Tyler Burton.", "Tyler Burton"),
        (
            "Denver Nuggets signed  Bryce Hopkins to a Two-Way Contract.",
            "Bryce Hopkins",
        ),
        ("Memphis Grizzlies did something inscrutable.", None),
        ("Memphis Grizzlies received draft consideration from Orlando Magic.", None),
        ("", None),
    ],
)
def test_lenient_extractor_returns_none_instead_of_raising(description, expected):
    assert try_player_name_from_description(description) == expected


def test_lenient_and_strict_agree_on_every_fixture_description(feed_payload):
    for row in feed_rows(feed_payload):
        if row.player_id > 0:
            assert try_player_name_from_description(
                row.description
            ) == player_name_from_description(row.description)


def test_transaction_id_replaces_the_space():
    assert transaction_id("Trade 2025022") == "Trade-2025022"
    assert transaction_id("Signing 1139430") == "Signing-1139430"


def test_memphis_groups_drop_pre_window_rows_and_sort_deterministically(feed_payload):
    groups = memphis_groups(feed_rows(feed_payload), WINDOW_START)
    keys = [group.group_key for group in groups]

    assert keys == sorted(keys, key=lambda key: (
        {group.group_key: group.occurred_on for group in groups}[key], key
    ))
    assert groups[0].group_key == "Signing 1139430"
    for pre_window in ("Trade 2024042", "Trade 2025003", "Signing 1135682", "Waive 1138138"):
        assert pre_window not in keys


def test_trade_2025022_leg_directions(feed_payload):
    groups = {g.group_key: g for g in memphis_groups(feed_rows(feed_payload), WINDOW_START)}
    transaction = group_to_transaction(groups["Trade 2025022"])
    directions = {
        movement.asset_id: (movement.from_holder, movement.to_holder)
        for movement in transaction.movements
    }

    assert transaction.id == "Trade-2025022"
    assert transaction.kind == "trade"
    assert transaction.counterparties == ["UTA"]
    assert directions["1628991"] == ("MEM", "UTA")  # Jaren Jackson Jr.
    assert directions["1629111"] == ("MEM", "UTA")  # Jock Landale
    assert directions["203937"] == ("UTA", "MEM")  # Kyle Anderson
    assert transaction.draft_considerations == [
        DraftConsideration(receiving="MEM", sending="UTA")
    ]


def test_trade_2026006_keeps_only_memphis_legs_but_all_counterparties(feed_payload):
    groups = {g.group_key: g for g in memphis_groups(feed_rows(feed_payload), WINDOW_START)}
    transaction = group_to_transaction(groups["Trade 2026006"])
    directions = {
        movement.asset_id: (movement.from_holder, movement.to_holder)
        for movement in transaction.movements
    }

    # Every team in the four-team group counts as a counterparty...
    assert transaction.counterparties == ["DAL", "DET", "LAC", "MIL", "WAS"]
    # ...but only legs where Memphis sends or receives become movements.
    assert directions == {
        "1626156": ("WAS", "MEM"),  # D'Angelo Russell
        "1630191": ("DET", "MEM"),  # Isaiah Stewart
        "1630583": ("MEM", "DAL"),  # Santi Aldama
        "1642358": ("DAL", "MEM"),  # AJ Johnson
    }
    # The DET<-LAC, DET<-MIL, MIL<-DET, DAL<-DET and WAS<-DAL legs are dropped as strands
    # but remain in the description, which keeps the whole trade readable.
    assert "Detroit Pistons received forward John Collins from LA Clippers." in (
        transaction.description
    )
    assert "Detroit Pistons received guard Gary Harris from Milwaukee Bucks." in (
        transaction.description
    )
    assert transaction.draft_considerations == [
        DraftConsideration(receiving="MEM", sending="DAL"),
        DraftConsideration(receiving="MEM", sending="WAS"),
        DraftConsideration(receiving="DET", sending="MEM"),
    ]


def test_signing_movements_use_a_current_holder_placeholder(feed_payload):
    groups = {g.group_key: g for g in memphis_groups(feed_rows(feed_payload), WINDOW_START)}
    transaction = group_to_transaction(groups["Signing 1139430"])
    (movement,) = transaction.movements

    assert movement.to_holder == "MEM"
    assert movement.from_holder_placeholder is True
    assert movement.entering_holder == "FA"
    assert movement.contract_type == "ten_day"


def test_waiver_movements_are_mem_to_fa(feed_payload):
    groups = {g.group_key: g for g in memphis_groups(feed_rows(feed_payload), WINDOW_START)}
    transaction = group_to_transaction(groups["Waive 1140530"])
    (movement,) = transaction.movements

    assert (movement.from_holder, movement.to_holder) == ("MEM", "FA")
    assert movement.from_holder_placeholder is False
