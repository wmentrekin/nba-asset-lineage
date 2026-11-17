"""Loads the curated opening-night snapshot and resolves missing NBA person ids."""

import datetime as dt
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lineage.parse import FeedRow, slugify_name, try_player_name_from_description
from lineage.teams import require_tricode

ContractType = Literal["standard", "two_way", "ten_day"]


class UnresolvedPlayerError(ValueError):
    """Raised when a snapshot player has no person_id and none can be found in the feed."""


class SnapshotPlayer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    person_id: int | None = None
    name: str
    contract_type: ContractType
    verified: bool = False
    note: str | None = None
    mem_since: dt.date | None = None
    mem_since_note: str | None = None


class SnapshotPick(BaseModel):
    model_config = ConfigDict(extra="ignore")

    draft_year: int
    round: int = Field(ge=1, le=2)
    original_team: str
    protections: str | None = None
    verified: bool = False
    note: str | None = None

    @property
    def pick_id(self) -> str:
        return pick_id_for(self.draft_year, self.round, self.original_team)


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    team: str
    season: str
    as_of: dt.date
    players: list[SnapshotPlayer]
    picks: list[SnapshotPick]


def pick_id_for(draft_year: int, round_: int, original_team: str) -> str:
    """Build the natural pick key `{draft_year}-R{round}-{original_team}`."""
    if round_ not in (1, 2):
        raise ValueError(f"pick round must be 1 or 2, got {round_!r}")
    return f"{draft_year}-R{round_}-{require_tricode(original_team)}"


def load_snapshot(path: str | Path) -> Snapshot:
    """Read and validate the curated opening-night snapshot file."""
    return Snapshot.model_validate(json.loads(Path(path).read_text()))


def feed_identity_index(rows: list[FeedRow]) -> tuple[dict[str, int], dict[str, int]]:
    """Return (slug -> person id, full name -> person id) built from itemized feed rows.

    This index is built over the whole cumulative feed - every team, back to 2015 - purely to
    look up ids the curated snapshot left null. None of it becomes graph rows, so it is
    deliberately tolerant: PLAYER_SLUG needs no parsing at all, and a description the name
    extractor cannot read is skipped rather than raising. Strictness belongs on the Memphis
    movement path in `parse.group_to_transaction`, not here.

    A slug or name that the feed maps to more than one person id is dropped from the index
    rather than resolved arbitrarily.
    """
    by_slug: dict[str, set[int]] = {}
    by_name: dict[str, set[int]] = {}
    for row in rows:
        if row.player_id <= 0:
            continue
        if row.player_slug:
            by_slug.setdefault(row.player_slug, set()).add(row.player_id)
        full_name = try_player_name_from_description(row.description)
        if full_name is not None:
            by_name.setdefault(full_name, set()).add(row.player_id)
    return (
        {slug: next(iter(ids)) for slug, ids in by_slug.items() if len(ids) == 1},
        {name: next(iter(ids)) for name, ids in by_name.items() if len(ids) == 1},
    )


def resolve_person_ids(snapshot: Snapshot, rows: list[FeedRow]) -> dict[str, int]:
    """Return snapshot player name -> NBA person id, resolving nulls against the feed.

    Raises:
        UnresolvedPlayerError: naming every snapshot player whose id is still unknown.
    """
    by_slug, by_name = feed_identity_index(rows)

    resolved: dict[str, int] = {}
    unresolved: list[str] = []
    for player in snapshot.players:
        if player.person_id is not None:
            resolved[player.name] = player.person_id
            continue
        # Slug first: it is feed data, not parsed text, so it survives a malformed
        # description for the very player being resolved.
        person_id = by_slug.get(slugify_name(player.name))
        if person_id is None:
            person_id = by_name.get(player.name)
        if person_id is None:
            unresolved.append(player.name)
            continue
        resolved[player.name] = person_id

    if unresolved:
        raise UnresolvedPlayerError(
            "opening snapshot has person_id null and no exact feed match for: "
            + ", ".join(sorted(unresolved))
            + ". Fill person_id in data/opening_snapshot_2025_26.json."
        )
    return resolved
