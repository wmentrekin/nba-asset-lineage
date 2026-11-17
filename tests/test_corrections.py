"""Tests for lineage.corrections: declarative overrides over the parsed feed."""

import datetime as dt

import pytest

from lineage.corrections import (
    CorrectionError,
    Corrections,
    apply_drop_rows,
    apply_movement_corrections,
    load_corrections,
)
from lineage.parse import FeedRow, MovementSpec, Transaction

from tests.conftest import DATA_DIR


def _transaction() -> Transaction:
    return Transaction(
        id="Trade-2025022",
        occurred_on=dt.date(2026, 2, 3),
        kind="trade",
        description="...",
        group_key="Trade 2025022",
        counterparties=["UTA"],
        movements=[
            MovementSpec(
                asset_type="player",
                asset_id="1629111",
                from_holder="MEM",
                to_holder="UTA",
            )
        ],
    )


def _row(group_key: str, player_id: int) -> FeedRow:
    return FeedRow(
        group_key=group_key,
        team_id=1610612763,
        additional_sort=0,
        player_id=player_id,
        player_slug="x",
        team_slug="grizzlies",
        occurred_on=dt.date(2026, 2, 3),
        transaction_type="Waive",
        description="Memphis Grizzlies waived guard X.",
    )


def test_load_corrections_reads_the_curated_file():
    corrections = load_corrections(DATA_DIR / "corrections.json")

    assert corrections.drop_rows == []
    assert corrections.override_movements == []
    assert corrections.add_movements == []
    assert corrections.comment is not None


def test_unknown_top_level_key_raises():
    with pytest.raises(ValueError):
        Corrections.model_validate({"drop_rows": [], "rename_players": []})


def test_unknown_rule_key_raises():
    with pytest.raises(ValueError):
        Corrections.model_validate(
            {"drop_rows": [{"group_key": "Trade 1", "player_id": 1, "why": "typo"}]}
        )


def test_apply_drop_rows_removes_only_the_named_row():
    rows = [_row("Trade 2025022", 1629111), _row("Trade 2025022", 203937)]
    corrections = Corrections.model_validate(
        {"drop_rows": [{"group_key": "Trade 2025022", "player_id": 203937}]}
    )

    kept = apply_drop_rows(rows, corrections)

    assert [row.player_id for row in kept] == [1629111]


def test_apply_drop_rows_raises_when_a_rule_matches_nothing():
    corrections = Corrections.model_validate(
        {"drop_rows": [{"group_key": "Trade 9999999", "player_id": 1}]}
    )

    with pytest.raises(CorrectionError, match="Trade 9999999"):
        apply_drop_rows([_row("Trade 2025022", 1629111)], corrections)


def test_override_movements_replaces_only_the_named_fields():
    transactions = [_transaction()]
    corrections = Corrections.model_validate(
        {
            "override_movements": [
                {
                    "group_key": "Trade 2025022",
                    "asset_type": "player",
                    "asset_id": "1629111",
                    "to_holder": "PHX",
                    "note": "three-team rerouting",
                }
            ]
        }
    )

    apply_movement_corrections(transactions, corrections)
    (movement,) = transactions[0].movements

    assert (movement.from_holder, movement.to_holder) == ("MEM", "PHX")
    assert movement.note == "three-team rerouting"


def test_override_movements_clears_the_placeholder_when_it_sets_from_holder():
    transactions = [_transaction()]
    transactions[0].movements[0].from_holder_placeholder = True
    corrections = Corrections.model_validate(
        {
            "override_movements": [
                {
                    "group_key": "Trade 2025022",
                    "asset_type": "player",
                    "asset_id": "1629111",
                    "from_holder": "ORL",
                }
            ]
        }
    )

    apply_movement_corrections(transactions, corrections)

    assert transactions[0].movements[0].from_holder == "ORL"
    assert transactions[0].movements[0].from_holder_placeholder is False


def test_add_movements_appends_a_full_row():
    transactions = [_transaction()]
    corrections = Corrections.model_validate(
        {
            "add_movements": [
                {
                    "group_key": "Trade 2025022",
                    "asset_type": "pick",
                    "asset_id": "2031-R2-UTA",
                    "from_holder": "UTA",
                    "to_holder": "MEM",
                    "note": "curated by hand",
                }
            ]
        }
    )

    apply_movement_corrections(transactions, corrections)

    assert [m.asset_id for m in transactions[0].movements] == ["1629111", "2031-R2-UTA"]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "override_movements": [
                {"group_key": "Trade 0", "asset_type": "player", "asset_id": "1"}
            ]
        },
        {
            "override_movements": [
                {"group_key": "Trade 2025022", "asset_type": "pick", "asset_id": "nope"}
            ]
        },
        {
            "add_movements": [
                {
                    "group_key": "Trade 2025022",
                    "asset_type": "player",
                    "asset_id": "1629111",
                    "to_holder": "PHX",
                }
            ]
        },
    ],
)
def test_movement_corrections_raise_when_they_match_nothing_or_duplicate(payload):
    with pytest.raises(CorrectionError):
        apply_movement_corrections([_transaction()], Corrections.model_validate(payload))
