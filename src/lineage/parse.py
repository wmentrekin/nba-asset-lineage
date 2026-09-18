"""Pure parsing of the NBA player-movement feed into transactions and movements.

The feed itemizes players only. A trade leg with PLAYER_ID 0 and a "received draft
consideration from" description is the only trace of pick movement, so those legs become
`DraftConsideration` markers and the real pick truth is curated in data/pick_events.json.
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from lineage.teams import MEM, MEM_TEAM_ID, tricode_for_id

FEED_ROOT_KEY = "NBA_Player_Movement"
FEED_ROWS_KEY = "rows"

FREE_AGENCY = "FA"
DRAFT_POOL = "DRAFT"
PICK_USED = "USED"

# Longest-first so "guard-forward" is not consumed by the bare "guard" alternative.
_POSITION_RE = re.compile(
    r"\b(?:guard-forward|forward-guard|forward-center|center-forward|guard|forward|center)\s+"
)
_NAME_TERMINATORS = (" from ", " to a ", " to an ")

KIND_TRADE = "trade"
KIND_WAIVER = "waiver"
KIND_SIGNING = "signing"
KIND_TWO_WAY_SIGNING = "two_way_signing"
KIND_TWO_WAY_CONVERSION = "two_way_conversion"
KIND_TEN_DAY = "ten_day"

CONTRACT_TWO_WAY = "two_way"
CONTRACT_TEN_DAY = "ten_day"
CONTRACT_STANDARD = "standard"

# Feed phrases that mean a plain standard contract.
_STANDARD_CONTRACT_PHRASES = (
    "Rookie Scale Contract",
    "Rest-of-Season Contract",
    "Veteran Extension",
    "Exhibit 10 Contract",
    "to a Contract",
    "to an Extension",
)


class FeedParseError(ValueError):
    """Raised when the feed contains a shape or phrase the parser refuses to guess at."""


@dataclass(frozen=True)
class FeedRow:
    """One normalized row of the player-movement feed."""

    group_key: str
    team_id: int
    additional_sort: int
    player_id: int
    player_slug: str
    team_slug: str
    occurred_on: dt.date
    transaction_type: str
    description: str

    @property
    def sort_key(self) -> tuple:
        return (
            self.occurred_on,
            self.team_id,
            self.additional_sort,
            self.player_id,
            self.description,
        )


@dataclass(frozen=True)
class Group:
    """All feed rows sharing one GroupSort, i.e. one transaction."""

    group_key: str
    rows: tuple[FeedRow, ...]

    @property
    def occurred_on(self) -> dt.date:
        return min(row.occurred_on for row in self.rows)

    @property
    def transaction_type(self) -> str:
        types = {row.transaction_type for row in self.rows}
        if len(types) != 1:
            raise FeedParseError(
                f"group {self.group_key!r} mixes Transaction_Type values: {sorted(types)}"
            )
        return next(iter(types))


@dataclass(frozen=True)
class PlayerRef:
    """A player as the feed describes them."""

    id: int
    full_name: str
    slug: str


@dataclass(frozen=True)
class DraftConsideration:
    """A PLAYER_ID-0 trade leg: picks moved, but the feed does not say which."""

    receiving: str
    sending: str


@dataclass
class MovementSpec:
    """One asset changing hands inside a transaction, before holder resolution.

    `from_holder_placeholder` marks a movement whose origin is "whoever held the asset
    before" - a re-signing or conversion. `entering_holder` is used instead when the asset
    has no earlier movement at all.
    """

    asset_type: str
    asset_id: str
    to_holder: str
    from_holder: str | None = None
    from_holder_placeholder: bool = False
    entering_holder: str | None = None
    contract_type: str | None = None
    note: str | None = None


@dataclass
class Transaction:
    """A derived graph node plus the movements it causes."""

    id: str
    occurred_on: dt.date
    kind: str
    description: str
    group_key: str | None
    counterparties: list[str]
    source_key: str = "feed"
    movements: list[MovementSpec] = field(default_factory=list)
    draft_considerations: list[DraftConsideration] = field(default_factory=list)
    note: str | None = None
    players: list[PlayerRef] = field(default_factory=list)


def slugify_name(full_name: str) -> str:
    """Return the feed's PLAYER_SLUG spelling of a full name ("PJ Hall" -> "pj-hall")."""
    cleaned = re.sub(r"[.'’]", "", full_name.lower())
    return re.sub(r"\s+", "-", cleaned.strip())


def feed_rows(payload: dict[str, Any]) -> list[FeedRow]:
    """Normalize a raw feed payload into FeedRow objects."""
    try:
        raw_rows = payload[FEED_ROOT_KEY][FEED_ROWS_KEY]
    except (KeyError, TypeError):
        raise FeedParseError(
            f"feed payload is missing {FEED_ROOT_KEY}.{FEED_ROWS_KEY}"
        ) from None
    return [_normalize_row(raw) for raw in raw_rows]


def _normalize_row(raw: dict[str, Any]) -> FeedRow:
    return FeedRow(
        group_key=raw["GroupSort"],
        team_id=int(raw["TEAM_ID"]),
        additional_sort=int(raw["Additional_Sort"]),
        player_id=int(raw["PLAYER_ID"]),
        player_slug=raw["PLAYER_SLUG"],
        team_slug=raw["TEAM_SLUG"],
        occurred_on=dt.date.fromisoformat(raw["TRANSACTION_DATE"][:10]),
        transaction_type=raw["Transaction_Type"],
        description=raw["TRANSACTION_DESCRIPTION"],
    )


def memphis_groups(rows: list[FeedRow], since: dt.date) -> list[Group]:
    """Group rows by GroupSort, keeping Memphis-involving groups dated on/after `since`."""
    by_key: dict[str, list[FeedRow]] = {}
    for row in rows:
        by_key.setdefault(row.group_key, []).append(row)

    groups: list[Group] = []
    for group_key, group_rows in by_key.items():
        touches_memphis = any(
            row.team_id == MEM_TEAM_ID or row.additional_sort == MEM_TEAM_ID
            for row in group_rows
        )
        if not touches_memphis:
            continue
        ordered = tuple(sorted(group_rows, key=lambda row: row.sort_key))
        group = Group(group_key=group_key, rows=ordered)
        if group.occurred_on < since:
            continue
        groups.append(group)

    return sorted(groups, key=lambda group: (group.occurred_on, group.group_key))


def classify(group: Group) -> str:
    """Return the transaction kind for a group, raising on an unknown Transaction_Type."""
    transaction_type = group.transaction_type
    if transaction_type == "Trade":
        return KIND_TRADE
    if transaction_type == "Waive":
        return KIND_WAIVER
    if transaction_type == "ContractConverted":
        return KIND_TWO_WAY_CONVERSION
    if transaction_type == "AwardOnWaivers":
        return KIND_SIGNING
    if transaction_type == "Signing":
        description = " ".join(row.description for row in group.rows)
        if "Two-Way Contract" in description:
            return KIND_TWO_WAY_SIGNING
        if "10-Day Contract" in description:
            return KIND_TEN_DAY
        return KIND_SIGNING
    raise FeedParseError(
        f"group {group.group_key!r} has unknown Transaction_Type {transaction_type!r}"
    )


def contract_type(description: str) -> str:
    """Return the contract type named by a signing description."""
    if "Two-Way Contract" in description:
        return CONTRACT_TWO_WAY
    if "10-Day Contract" in description:
        return CONTRACT_TEN_DAY
    if any(phrase in description for phrase in _STANDARD_CONTRACT_PHRASES):
        return CONTRACT_STANDARD
    raise FeedParseError(f"unrecognized contract phrasing: {description!r}")


def player_name_from_description(description: str) -> str:
    """Extract a player's full name from a formulaic feed description.

    The name sits between the position word and " from "/" to a ", or runs to the end of the
    sentence. Trailing sentence periods are stripped one at a time so that "Charlie Brown
    Jr.." yields "Charlie Brown Jr.".
    """
    match = _POSITION_RE.search(description)
    if match is None:
        raise FeedParseError(f"no position word in description: {description!r}")
    tail = description[match.end() :]
    for terminator in _NAME_TERMINATORS:
        index = tail.find(terminator)
        if index != -1:
            return tail[:index].strip()
    if tail.endswith("."):
        tail = tail[:-1]
    return tail.strip()


def player_ref(row: FeedRow) -> PlayerRef:
    """Build a PlayerRef from an itemized (PLAYER_ID > 0) feed row."""
    return PlayerRef(
        id=row.player_id,
        full_name=player_name_from_description(row.description),
        slug=row.player_slug,
    )


def _counterparties(group: Group) -> list[str]:
    tricodes: set[str] = set()
    for row in group.rows:
        tricodes.add(tricode_for_id(row.team_id))
        if row.additional_sort:
            tricodes.add(tricode_for_id(row.additional_sort))
    tricodes.discard(MEM)
    return sorted(tricodes)


def transaction_id(group_key: str) -> str:
    """Turn a feed GroupSort into a transaction id ("Trade 2025022" -> "Trade-2025022")."""
    return group_key.replace(" ", "-")


def group_to_transaction(group: Group) -> Transaction:
    """Turn one feed group into a Transaction with its Memphis-relevant movements."""
    kind = classify(group)
    descriptions: list[str] = []
    for row in group.rows:
        if row.description not in descriptions:
            descriptions.append(row.description)

    transaction = Transaction(
        id=transaction_id(group.group_key),
        occurred_on=group.occurred_on,
        kind=kind,
        description=" ".join(descriptions),
        group_key=group.group_key,
        counterparties=_counterparties(group),
    )

    for row in group.rows:
        _add_row(transaction, group, row, kind)
    return transaction


def _add_row(transaction: Transaction, group: Group, row: FeedRow, kind: str) -> None:
    if kind == KIND_TRADE:
        _add_trade_row(transaction, row)
        return

    if row.player_id <= 0:
        raise FeedParseError(
            f"group {group.group_key!r} has a non-trade row without a player: {row.description!r}"
        )
    player = player_ref(row)
    transaction.players.append(player)
    asset_id = str(player.id)

    if kind == KIND_WAIVER:
        transaction.movements.append(
            MovementSpec(
                asset_type="player",
                asset_id=asset_id,
                from_holder=MEM,
                to_holder=FREE_AGENCY,
            )
        )
        return

    if kind == KIND_TWO_WAY_CONVERSION:
        transaction.movements.append(
            MovementSpec(
                asset_type="player",
                asset_id=asset_id,
                to_holder=MEM,
                from_holder_placeholder=True,
                entering_holder=MEM,
                contract_type=CONTRACT_STANDARD,
            )
        )
        return

    # Signing kinds (Signing, AwardOnWaivers). A claim off waivers carries the player's
    # existing standard deal; the description names no contract to parse.
    resolved_contract = (
        CONTRACT_STANDARD
        if row.transaction_type == "AwardOnWaivers"
        else contract_type(row.description)
    )
    transaction.movements.append(
        MovementSpec(
            asset_type="player",
            asset_id=asset_id,
            to_holder=MEM,
            from_holder_placeholder=True,
            entering_holder=FREE_AGENCY,
            contract_type=resolved_contract,
        )
    )


def _add_trade_row(transaction: Transaction, row: FeedRow) -> None:
    receiving = tricode_for_id(row.team_id)
    sending = tricode_for_id(row.additional_sort)
    if MEM not in (receiving, sending):
        # A leg of a multi-team trade that does not touch Memphis: out of scope as a
        # strand, but its teams still count as counterparties.
        return

    if row.player_id <= 0:
        transaction.draft_considerations.append(
            DraftConsideration(receiving=receiving, sending=sending)
        )
        return

    player = player_ref(row)
    transaction.players.append(player)
    transaction.movements.append(
        MovementSpec(
            asset_type="player",
            asset_id=str(player.id),
            from_holder=sending,
            to_holder=receiving,
        )
    )
