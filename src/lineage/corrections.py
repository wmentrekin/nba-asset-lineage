"""Loads and applies data/corrections.json over the parsed feed.

Corrections are the only sanctioned way to fix bad or missing feed data: derived tables are
never hand-edited. Unknown keys raise instead of being ignored, so a typo cannot silently
become a no-op.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from lineage.parse import FeedRow, MovementSpec, Transaction


class CorrectionError(ValueError):
    """Raised when a correction does not match anything it claims to correct."""


class DropRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_key: str
    player_id: int
    note: str | None = None


class OverrideMovement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_key: str
    asset_type: str
    asset_id: str
    from_holder: str | None = None
    to_holder: str | None = None
    contract_type: str | None = None
    note: str | None = None


class AddMovement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_key: str
    asset_type: str
    asset_id: str
    to_holder: str
    from_holder: str | None = None
    contract_type: str | None = None
    note: str | None = None


class Corrections(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    comment: str | None = Field(default=None, alias="$comment")
    drop_rows: list[DropRow] = Field(default_factory=list)
    override_movements: list[OverrideMovement] = Field(default_factory=list)
    add_movements: list[AddMovement] = Field(default_factory=list)


def load_corrections(path: str | Path) -> Corrections:
    """Read and validate the corrections file."""
    return Corrections.model_validate(json.loads(Path(path).read_text()))


def apply_drop_rows(rows: list[FeedRow], corrections: Corrections) -> list[FeedRow]:
    """Remove feed rows named by (group_key, player_id); every rule must match something."""
    if not corrections.drop_rows:
        return list(rows)

    dropped: set[tuple[str, int]] = set()
    kept: list[FeedRow] = []
    for row in rows:
        key = (row.group_key, row.player_id)
        if any(
            rule.group_key == row.group_key and rule.player_id == row.player_id
            for rule in corrections.drop_rows
        ):
            dropped.add(key)
            continue
        kept.append(row)

    unmatched = [
        f"{rule.group_key}/{rule.player_id}"
        for rule in corrections.drop_rows
        if (rule.group_key, rule.player_id) not in dropped
    ]
    if unmatched:
        raise CorrectionError(f"drop_rows matched no feed row: {', '.join(unmatched)}")
    return kept


def apply_movement_corrections(
    transactions: list[Transaction], corrections: Corrections
) -> None:
    """Apply override_movements then add_movements in file order, in place."""
    by_group: dict[str, Transaction] = {
        transaction.group_key: transaction
        for transaction in transactions
        if transaction.group_key is not None
    }

    for override in corrections.override_movements:
        transaction = _require_group(by_group, override.group_key)
        movement = _find_movement(transaction, override.asset_type, override.asset_id)
        if movement is None:
            raise CorrectionError(
                f"override_movements found no {override.asset_type} {override.asset_id} "
                f"in {override.group_key}"
            )
        fields = override.model_fields_set - {"group_key", "asset_type", "asset_id"}
        for name in sorted(fields):
            setattr(movement, name, getattr(override, name))
        if "from_holder" in fields:
            movement.from_holder_placeholder = False

    for addition in corrections.add_movements:
        transaction = _require_group(by_group, addition.group_key)
        if _find_movement(transaction, addition.asset_type, addition.asset_id) is not None:
            raise CorrectionError(
                f"add_movements duplicates {addition.asset_type} {addition.asset_id} "
                f"in {addition.group_key}"
            )
        transaction.movements.append(
            MovementSpec(
                asset_type=addition.asset_type,
                asset_id=addition.asset_id,
                to_holder=addition.to_holder,
                from_holder=addition.from_holder,
                contract_type=addition.contract_type,
                note=addition.note,
            )
        )


def _require_group(by_group: dict[str, Transaction], group_key: str) -> Transaction:
    transaction = by_group.get(group_key)
    if transaction is None:
        raise CorrectionError(f"corrections name unknown group_key {group_key!r}")
    return transaction


def _find_movement(
    transaction: Transaction, asset_type: str, asset_id: str
) -> MovementSpec | None:
    for movement in transaction.movements:
        if movement.asset_type == asset_type and movement.asset_id == asset_id:
            return movement
    return None
