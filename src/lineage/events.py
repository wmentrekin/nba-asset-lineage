"""Loads data/curated_events.json: the curated truth the NBA player-movement feed cannot
supply - trade picks in and out, draft selections (pick strand ends, player strand begins),
and standalone roster events such as a contract void.
"""

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from lineage.teams import require_tricode

PICK_ID_RE = re.compile(r"^(\d{4})-R([12])-([A-Z]{3})$")

UNCURATED_NOTE = "draft consideration: picks not yet curated"

Confidence = Literal["high", "medium", "low"]


class CuratedEventsError(ValueError):
    """Raised when data/curated_events.json cannot be reconciled with the parsed feed."""


class PickIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pick_id: str
    from_holder: str = Field(alias="from")
    protections: str | None = None
    source_url: str | None = None
    verified: bool = False
    confidence: Confidence = "low"


class PickOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pick_id: str
    to_holder: str = Field(alias="to")
    protections: str | None = None
    source_url: str | None = None
    verified: bool = False
    confidence: Confidence = "low"


class TradeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_key: str
    date: dt.date
    counterparty: str
    verified: bool = False
    confidence: Confidence = "low"
    picks_in: list[PickIn] = Field(default_factory=list)
    picks_out: list[PickOut] = Field(default_factory=list)
    footnotes: list[str] = Field(default_factory=list)


class DraftSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date
    pick_no: int
    pick_id: str
    player_id: int | None = None
    player_name: str
    signed: bool = False
    source_url: str | None = None
    verified: bool = False
    confidence: Confidence = "low"
    footnotes: list[str] = Field(default_factory=list)


class EventEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    date: dt.date
    kind: Literal["contract_void"]
    player_id: int
    player_name: str
    to_holder: Literal["VOID"]
    description: str
    source_url: str | None = None
    verified: bool = False
    confidence: Confidence = "low"
    footnotes: list[str] = Field(default_factory=list)


class CuratedEvents(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    comment: str | None = Field(default=None, alias="$comment")
    pick_row_shape: dict[str, Any] | None = None
    trades: list[TradeEntry] = Field(default_factory=list)
    draft_selections: list[DraftSelection] = Field(default_factory=list)
    events: list[EventEntry] = Field(default_factory=list)


def load_curated_events(path: str | Path) -> CuratedEvents:
    """Read and validate the curated events file."""
    return CuratedEvents.model_validate(json.loads(Path(path).read_text()))


def parse_pick_id(pick_id: str) -> tuple[int, int, str]:
    """Split `{draft_year}-R{round}-{original_team}` into its parts, raising on junk."""
    match = PICK_ID_RE.match(pick_id)
    if match is None:
        raise CuratedEventsError(f"malformed pick id: {pick_id!r}")
    draft_year, round_, original_team = match.groups()
    return int(draft_year), int(round_), require_tricode(original_team)


def draft_transaction_id(selection: DraftSelection) -> str:
    """Transaction id for a curated draft selection."""
    return f"Draft-{selection.date.isoformat()}-{selection.pick_id}"


def synthetic_player_id(selection: DraftSelection) -> int:
    """Deterministic negative id for a drafted player the feed has no NBA person id for."""
    draft_year, _, _ = parse_pick_id(selection.pick_id)
    return -(draft_year * 100 + selection.pick_no)
