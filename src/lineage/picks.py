"""Loads data/pick_events.json: the curated pick truth the feed cannot supply."""

import datetime as dt
import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from lineage.teams import require_tricode

PICK_ID_RE = re.compile(r"^(\d{4})-R([12])-([A-Z]{3})$")

TODO_PICK_ID = "TODO"
UNCURATED_NOTE = "draft consideration: picks not yet curated"


class PickEventsError(ValueError):
    """Raised when data/pick_events.json cannot be reconciled with the parsed feed."""


class PickMove(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    pick_id: str
    from_holder: str = Field(alias="from")
    to_holder: str = Field(alias="to")
    protections: str | None = None
    source_url: str | None = None
    verified: bool = False


class PickTrade(BaseModel):
    model_config = ConfigDict(extra="ignore")

    group_key: str
    date: dt.date | None = None
    counterparty: str | None = None
    feed_legs: list[str] = Field(default_factory=list)
    picks: list[PickMove] = Field(default_factory=list)
    note: str | None = None
    verified: bool = False


class DraftSelection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: dt.date
    pick_id: str
    player_id: int
    player_name: str
    note: str | None = None
    verified: bool = False

    @property
    def is_todo(self) -> bool:
        return self.pick_id == TODO_PICK_ID


class PickEvents(BaseModel):
    model_config = ConfigDict(extra="ignore")

    trades: list[PickTrade] = Field(default_factory=list)
    draft_selections: list[DraftSelection] = Field(default_factory=list)


def load_pick_events(path: str | Path) -> PickEvents:
    """Read and validate the curated pick-events file."""
    return PickEvents.model_validate(json.loads(Path(path).read_text()))


def parse_pick_id(pick_id: str) -> tuple[int, int, str]:
    """Split `{draft_year}-R{round}-{original_team}` into its parts, raising on junk."""
    match = PICK_ID_RE.match(pick_id)
    if match is None:
        raise PickEventsError(f"malformed pick id: {pick_id!r}")
    draft_year, round_, original_team = match.groups()
    return int(draft_year), int(round_), require_tricode(original_team)


def draft_transaction_id(selection: DraftSelection) -> str:
    """Transaction id for a curated draft selection."""
    return f"Draft-{selection.date.isoformat()}-{selection.player_id}"
