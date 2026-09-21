"""Per-asset holder timelines, built on demand from asset movements.

Strands are never stored: both `validate` and `export` rebuild them here so there is exactly
one definition of "who held this asset when".
"""

import datetime as dt
from dataclasses import dataclass, replace

AssetKey = tuple[str, str]


@dataclass(frozen=True)
class Movement:
    """One derived `lineage.asset_movement` row.

    `sequence` stands in for the row's bigserial id: it is the tie-breaker that makes the
    order of two movements on the same asset, date and transaction deterministic.
    """

    transaction_id: str
    occurred_on: dt.date
    asset_type: str
    asset_id: str
    to_holder: str
    from_holder: str | None = None
    contract_type: str | None = None
    note: str | None = None
    sequence: int = 0
    from_holder_placeholder: bool = False
    entering_holder: str | None = None


@dataclass(frozen=True)
class Segment:
    """The interval during which one holder held one asset."""

    from_node: str | None
    to_node: str | None
    holder: str
    contract_type: str | None


def movement_sort_key(movement: Movement) -> tuple:
    """The canonical movement ordering: (occurred_on, transaction_id, row id)."""
    return (movement.occurred_on, movement.transaction_id, movement.sequence)


def sorted_movements(movements: list[Movement]) -> list[Movement]:
    """Return movements in canonical order."""
    return sorted(movements, key=movement_sort_key)


def by_asset(movements: list[Movement]) -> dict[AssetKey, list[Movement]]:
    """Group movements by (asset_type, asset_id), each list in canonical order."""
    grouped: dict[AssetKey, list[Movement]] = {}
    for movement in sorted_movements(movements):
        grouped.setdefault((movement.asset_type, movement.asset_id), []).append(movement)
    return grouped


def resolve_from_holders(movements: list[Movement]) -> list[Movement]:
    """Fill in `from_holder` for movements that mean "whoever held this before".

    A re-signing, extension or conversion does not change the holder, and the feed row does
    not name one. Walking each asset's timeline supplies it. An asset whose first movement
    is such a placeholder takes its `entering_holder` (FA for a signing); the baseline
    origin is not a placeholder and keeps a NULL `from_holder`.
    """
    resolved: list[Movement] = []
    for asset_movements in by_asset(movements).values():
        previous_holder: str | None = None
        for movement in asset_movements:
            if movement.from_holder_placeholder:
                movement = replace(
                    movement,
                    from_holder=(
                        previous_holder
                        if previous_holder is not None
                        else movement.entering_holder
                    ),
                    from_holder_placeholder=False,
                    entering_holder=None,
                )
            resolved.append(movement)
            previous_holder = movement.to_holder
    return sorted_movements(resolved)


def build_timelines(movements: list[Movement]) -> dict[AssetKey, list[Segment]]:
    """Return each asset's holder intervals, in canonical movement order.

    Each movement opens a segment held by its `to_holder`; the next movement on that asset
    closes it. The final segment stays open (`to_node` is None).
    """
    timelines: dict[AssetKey, list[Segment]] = {}
    for asset_key, asset_movements in by_asset(movements).items():
        segments: list[Segment] = []
        for index, movement in enumerate(asset_movements):
            next_movement = (
                asset_movements[index + 1] if index + 1 < len(asset_movements) else None
            )
            segments.append(
                Segment(
                    from_node=movement.transaction_id,
                    to_node=next_movement.transaction_id if next_movement else None,
                    holder=movement.to_holder,
                    contract_type=movement.contract_type,
                )
            )
        timelines[asset_key] = segments
    return timelines
