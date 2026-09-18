"""Rebuilds the derived lineage tables from raw payloads plus the curated data files.

`build_graph` is a pure function of its inputs - no database, no clock, no network - so the
whole derivation is testable offline and two runs over identical inputs produce identical
output. `load_graph` is the thin DB half: truncate, then insert in a fixed order.
"""

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from lineage.corrections import (
    CorrectionError,
    Corrections,
    apply_drop_rows,
    apply_movement_corrections,
    load_corrections,
)
from lineage.parse import (
    CONTRACT_TEN_DAY,
    DRAFT_POOL,
    FREE_AGENCY,
    PICK_USED,
    FeedParseError,
    FeedRow,
    MovementSpec,
    PlayerRef,
    Transaction,
    feed_rows,
    group_to_transaction,
    memphis_groups,
    try_player_ref,
)
from lineage.picks import (
    UNCURATED_NOTE,
    PickEvents,
    PickEventsError,
    draft_transaction_id,
    load_pick_events,
    parse_pick_id,
)
from lineage.snapshot import (
    Snapshot,
    UnresolvedPlayerError,
    load_snapshot,
    pick_id_for,
    resolve_person_ids,
)
from lineage.teams import MEM
from lineage.timeline import Movement, resolve_from_holders

KIND_BASELINE = "baseline"
KIND_DRAFT_SELECTION = "draft_selection"
KIND_EXPIRY = "expiry"

BASELINE_DESCRIPTION = "Opening-night roster and owned pick inventory"

SOURCE_FEED = "nba_player_movement"
SOURCE_SNAPSHOT = "curated_snapshot"
SOURCE_PICK_EVENTS = "curated_pick_events"
SOURCE_CORRECTIONS = "curated_corrections"

SOURCE_KEY_FEED = "feed"
SOURCE_KEY_SNAPSHOT = "snapshot"
SOURCE_KEY_PICK_EVENTS = "pick_events"

CURATED_SOURCES: dict[str, tuple[str, str]] = {
    SOURCE_KEY_SNAPSHOT: (SOURCE_SNAPSHOT, "opening_snapshot_2025_26.json"),
    SOURCE_KEY_PICK_EVENTS: (SOURCE_PICK_EVENTS, "pick_events.json"),
    "corrections": (SOURCE_CORRECTIONS, "corrections.json"),
}

TRUNCATE_SQL = (
    "truncate lineage.asset_movement, lineage.transaction, lineage.pick, lineage.player "
    "restart identity cascade"
)
INSERT_PLAYER_SQL = "insert into lineage.player (id, full_name, slug) values (%s, %s, %s)"
INSERT_PICK_SQL = (
    "insert into lineage.pick (id, draft_year, round, original_team, protections) "
    "values (%s, %s, %s, %s, %s)"
)
INSERT_TRANSACTION_SQL = (
    "insert into lineage.transaction "
    "(id, occurred_on, kind, description, group_key, source_record_id, counterparties, note) "
    "values (%s, %s, %s, %s, %s, %s, %s, %s)"
)
INSERT_MOVEMENT_SQL = (
    "insert into lineage.asset_movement "
    "(transaction_id, asset_type, asset_id, from_holder, to_holder, contract_type, note) "
    "values (%s, %s, %s, %s, %s, %s, %s)"
)


class DeriveError(ValueError):
    """Raised when the inputs cannot be turned into a consistent graph."""


# Every way a bad input can stop a derivation; the CLI reports these instead of traceback.
DERIVE_ERRORS = (
    CorrectionError,
    DeriveError,
    FeedParseError,
    PickEventsError,
    UnresolvedPlayerError,
)


@dataclass(frozen=True)
class Player:
    id: int
    full_name: str
    slug: str | None


@dataclass(frozen=True)
class Pick:
    id: str
    draft_year: int
    round: int
    original_team: str
    protections: str | None


@dataclass(frozen=True)
class TransactionRow:
    id: str
    occurred_on: dt.date
    kind: str
    description: str
    group_key: str | None
    source_key: str
    counterparties: list[str]
    note: str | None = None


@dataclass
class DerivedGraph:
    """Everything `derive` produces, in deterministic order."""

    players: list[Player] = field(default_factory=list)
    picks: list[Pick] = field(default_factory=list)
    transactions: list[TransactionRow] = field(default_factory=list)
    movements: list[Movement] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def build_graph(
    feed_payload: dict[str, Any],
    snapshot: Snapshot,
    pick_events: PickEvents,
    corrections: Corrections,
) -> DerivedGraph:
    """Derive the whole graph from raw payloads plus curated files. Pure and deterministic."""
    rows = apply_drop_rows(feed_rows(feed_payload), corrections)
    person_ids = resolve_person_ids(snapshot, rows)
    identity = _feed_identity(rows)

    notes: list[str] = []
    transactions: list[Transaction] = [_baseline_transaction(snapshot, person_ids)]
    transactions += [
        group_to_transaction(group) for group in memphis_groups(rows, snapshot.as_of)
    ]
    _attach_pick_events(transactions, pick_events, notes)
    transactions += _draft_selection_transactions(pick_events, notes)

    apply_movement_corrections(transactions, corrections)
    transactions += _expiry_transactions(transactions)

    transactions.sort(key=lambda transaction: (transaction.occurred_on, transaction.id))
    movements = _flatten_movements(transactions)

    return DerivedGraph(
        players=_player_rows(movements, identity, snapshot, person_ids, pick_events),
        picks=_pick_rows(snapshot, pick_events, movements),
        transactions=[
            TransactionRow(
                id=transaction.id,
                occurred_on=transaction.occurred_on,
                kind=transaction.kind,
                description=transaction.description,
                group_key=transaction.group_key,
                source_key=transaction.source_key,
                counterparties=list(transaction.counterparties),
                note=transaction.note,
            )
            for transaction in transactions
        ],
        movements=movements,
        notes=notes,
    )


def _feed_identity(rows: list[FeedRow]) -> dict[int, PlayerRef]:
    """Player identity from every feed row, including rows before the window.

    Lenient for the same reason as `snapshot.feed_identity_index`: this scans the whole
    cumulative feed, so a description from an unrelated team that the extractor cannot read
    is skipped, leaving a later row for the same player free to supply the name. Memphis rows
    that become movements still go through the strict extractor in `parse`.
    """
    identity: dict[int, PlayerRef] = {}
    for row in rows:
        if row.player_id <= 0 or row.player_id in identity:
            continue
        ref = try_player_ref(row)
        if ref is not None:
            identity[row.player_id] = ref
    return identity


def _baseline_transaction(snapshot: Snapshot, person_ids: dict[str, int]) -> Transaction:
    """The virtual opening-night node: every roster player and owned pick enters at MEM."""
    transaction = Transaction(
        id=f"OPENING-{snapshot.season}",
        occurred_on=snapshot.as_of,
        kind=KIND_BASELINE,
        description=BASELINE_DESCRIPTION,
        group_key=None,
        counterparties=[],
        source_key=SOURCE_KEY_SNAPSHOT,
    )
    for player in snapshot.players:
        transaction.movements.append(
            MovementSpec(
                asset_type="player",
                asset_id=str(person_ids[player.name]),
                to_holder=MEM,
                contract_type=player.contract_type,
            )
        )
    for pick in snapshot.picks:
        transaction.movements.append(
            MovementSpec(asset_type="pick", asset_id=pick.pick_id, to_holder=MEM)
        )
    return transaction


def _draft_consideration_note(transaction: Transaction) -> str:
    """Summarize a trade's draft-consideration legs as `draft consideration: MEM<-DAL; ...`.

    Order matches `transaction.draft_considerations`, i.e. the order the feed rows were
    parsed in, so the note is deterministic.
    """
    legs = "; ".join(
        f"{consideration.receiving}<-{consideration.sending}"
        for consideration in transaction.draft_considerations
    )
    return f"draft consideration: {legs}"


def _attach_pick_events(
    transactions: list[Transaction], pick_events: PickEvents, notes: list[str]
) -> None:
    """Attach curated pick movements to the trade transactions they belong to."""
    by_group = {
        transaction.group_key: transaction
        for transaction in transactions
        if transaction.group_key is not None
    }
    for trade in pick_events.trades:
        transaction = by_group.get(trade.group_key)
        if transaction is None:
            raise PickEventsError(
                f"pick_events names group_key {trade.group_key!r}, which is not a parsed "
                "in-window Memphis transaction"
            )
        if not trade.picks:
            transaction.note = UNCURATED_NOTE
            notes.append(f"{transaction.id}: {UNCURATED_NOTE}")
            continue
        transaction.note = _draft_consideration_note(transaction)
        for move in trade.picks:
            parse_pick_id(move.pick_id)
            transaction.movements.append(
                MovementSpec(
                    asset_type="pick",
                    asset_id=move.pick_id,
                    from_holder=move.from_holder,
                    to_holder=move.to_holder,
                    note=move.source_url,
                )
            )


def _draft_selection_transactions(
    pick_events: PickEvents, notes: list[str]
) -> list[Transaction]:
    """Turn curated draft selections into nodes where a pick strand becomes a player strand."""
    transactions: list[Transaction] = []
    for selection in pick_events.draft_selections:
        if selection.is_todo:
            notes.append(
                f"draft selection {selection.player_name} ({selection.player_id}) on "
                f"{selection.date.isoformat()} skipped: pick_id is TODO"
            )
            continue
        parse_pick_id(selection.pick_id)
        transaction = Transaction(
            id=draft_transaction_id(selection),
            occurred_on=selection.date,
            kind=KIND_DRAFT_SELECTION,
            description=(
                f"Memphis Grizzlies selected {selection.player_name} with pick "
                f"{selection.pick_id}."
            ),
            group_key=None,
            counterparties=[],
            source_key=SOURCE_KEY_PICK_EVENTS,
        )
        transaction.movements.append(
            MovementSpec(
                asset_type="pick",
                asset_id=selection.pick_id,
                from_holder=MEM,
                to_holder=PICK_USED,
            )
        )
        transaction.movements.append(
            MovementSpec(
                asset_type="player",
                asset_id=str(selection.player_id),
                from_holder=DRAFT_POOL,
                to_holder=MEM,
            )
        )
        transactions.append(transaction)
    return transactions


def _expiry_transactions(transactions: list[Transaction]) -> list[Transaction]:
    """Synthesize an `expiry` transaction for every ten-day signing nothing else resolves.

    An NBA 10-day contract runs 10 days (or 3 games, whichever is longer); we approximate
    with a flat 10 days since the feed never records the expiration itself. A signing is
    skipped here when the same player has any other movement dated after the signing and
    on/before the would-be expiry date - a second 10-day, a rest-of-season deal, a waiver, a
    trade - since that movement already ends the 10-day strand (a movement dated exactly on
    the 10th day wins the tie). For a second consecutive 10-day, this naturally attaches the
    expiry to the second signing instead of the first, because each ten-day movement is
    checked independently against the real movements already in `transactions`.
    """
    expiries: list[Transaction] = []
    for transaction in transactions:
        for movement in transaction.movements:
            if (
                movement.asset_type != "player"
                or movement.contract_type != CONTRACT_TEN_DAY
                or movement.to_holder != MEM
            ):
                continue
            expiry_date = transaction.occurred_on + dt.timedelta(days=10)
            if _has_superseding_movement(
                transactions, movement.asset_id, transaction.occurred_on, expiry_date
            ):
                continue
            digits = transaction.group_key.split()[-1]
            expiry = Transaction(
                id=f"Expire-{digits}",
                occurred_on=expiry_date,
                kind=KIND_EXPIRY,
                description="10-day contract expired",
                group_key=None,
                counterparties=[],
                source_key=transaction.source_key,
            )
            expiry.movements.append(
                MovementSpec(
                    asset_type="player",
                    asset_id=movement.asset_id,
                    from_holder=MEM,
                    to_holder=FREE_AGENCY,
                )
            )
            expiries.append(expiry)
    return expiries


def _has_superseding_movement(
    transactions: list[Transaction],
    asset_id: str,
    signing_date: dt.date,
    expiry_date: dt.date,
) -> bool:
    """True if `asset_id` has a player movement after `signing_date` and up to `expiry_date`."""
    for other in transactions:
        if not (signing_date < other.occurred_on <= expiry_date):
            continue
        if any(
            spec.asset_type == "player" and spec.asset_id == asset_id
            for spec in other.movements
        ):
            return True
    return False


def _flatten_movements(transactions: list[Transaction]) -> list[Movement]:
    """Flatten, order and number every movement, then resolve holder placeholders."""
    flattened: list[Movement] = []
    for transaction in transactions:
        for spec in transaction.movements:
            flattened.append(
                Movement(
                    transaction_id=transaction.id,
                    occurred_on=transaction.occurred_on,
                    asset_type=spec.asset_type,
                    asset_id=spec.asset_id,
                    to_holder=spec.to_holder,
                    from_holder=spec.from_holder,
                    contract_type=spec.contract_type,
                    note=spec.note,
                    from_holder_placeholder=spec.from_holder_placeholder,
                    entering_holder=spec.entering_holder,
                )
            )

    flattened.sort(
        key=lambda movement: (
            movement.occurred_on,
            movement.transaction_id,
            movement.asset_type,
            movement.asset_id,
        )
    )
    _reject_duplicates(flattened)
    numbered = [
        Movement(**{**asdict(movement), "sequence": index})
        for index, movement in enumerate(flattened, start=1)
    ]
    return resolve_from_holders(numbered)


def _reject_duplicates(movements: list[Movement]) -> None:
    seen: set[tuple[str, str, str]] = set()
    for movement in movements:
        key = (movement.transaction_id, movement.asset_type, movement.asset_id)
        if key in seen:
            raise DeriveError(f"duplicate movement for {key}")
        seen.add(key)


def _player_rows(
    movements: list[Movement],
    identity: dict[int, PlayerRef],
    snapshot: Snapshot,
    person_ids: dict[str, int],
    pick_events: PickEvents,
) -> list[Player]:
    """One row per player that appears in a movement, named from the feed where possible."""
    snapshot_names = {person_id: name for name, person_id in person_ids.items()}
    curated_names = {
        selection.player_id: selection.player_name
        for selection in pick_events.draft_selections
    }

    players: list[Player] = []
    for person_id in sorted(
        {int(movement.asset_id) for movement in movements if movement.asset_type == "player"}
    ):
        ref = identity.get(person_id)
        if ref is not None:
            players.append(Player(id=person_id, full_name=ref.full_name, slug=ref.slug or None))
            continue
        full_name = snapshot_names.get(person_id) or curated_names.get(person_id)
        if full_name is None:
            raise DeriveError(f"no name available for player id {person_id}")
        players.append(Player(id=person_id, full_name=full_name, slug=None))
    return players


def _pick_rows(
    snapshot: Snapshot, pick_events: PickEvents, movements: list[Movement]
) -> list[Pick]:
    """Snapshot inventory plus any pick referenced in-window, parsed from its natural key."""
    picks: dict[str, Pick] = {}
    for snapshot_pick in snapshot.picks:
        picks[snapshot_pick.pick_id] = Pick(
            id=snapshot_pick.pick_id,
            draft_year=snapshot_pick.draft_year,
            round=snapshot_pick.round,
            original_team=snapshot_pick.original_team,
            protections=snapshot_pick.protections,
        )

    protections = {
        move.pick_id: move.protections
        for trade in pick_events.trades
        for move in trade.picks
    }
    for movement in movements:
        if movement.asset_type != "pick" or movement.asset_id in picks:
            continue
        draft_year, round_, original_team = parse_pick_id(movement.asset_id)
        picks[movement.asset_id] = Pick(
            id=pick_id_for(draft_year, round_, original_team),
            draft_year=draft_year,
            round=round_,
            original_team=original_team,
            protections=protections.get(movement.asset_id),
        )
    return [picks[pick_id] for pick_id in sorted(picks)]


def graph_to_dict(graph: DerivedGraph) -> dict[str, Any]:
    """Serialize a graph deterministically, for --dry-run output and equality checks."""
    return {
        "players": [asdict(player) for player in graph.players],
        "picks": [asdict(pick) for pick in graph.picks],
        "transactions": [
            {**asdict(transaction), "occurred_on": transaction.occurred_on.isoformat()}
            for transaction in graph.transactions
        ],
        "movements": [
            {
                "sequence": movement.sequence,
                "transaction_id": movement.transaction_id,
                "occurred_on": movement.occurred_on.isoformat(),
                "asset_type": movement.asset_type,
                "asset_id": movement.asset_id,
                "from_holder": movement.from_holder,
                "to_holder": movement.to_holder,
                "contract_type": movement.contract_type,
                "note": movement.note,
            }
            for movement in graph.movements
        ],
        "notes": list(graph.notes),
    }


def graph_to_json(graph: DerivedGraph) -> str:
    """Pretty, stable JSON for `lineage derive --dry-run`."""
    return json.dumps(graph_to_dict(graph), indent=2, sort_keys=True)


def load_graph(conn, graph: DerivedGraph, source_record_ids: dict[str, int]) -> None:
    """Truncate the derived tables and reinsert the whole graph in one DB transaction."""
    missing = sorted(
        {transaction.source_key for transaction in graph.transactions}
        - set(source_record_ids)
    )
    if missing:
        raise DeriveError(f"no source_record id for source key(s): {', '.join(missing)}")

    with conn.cursor() as cur:
        cur.execute(TRUNCATE_SQL)
        cur.executemany(
            INSERT_PLAYER_SQL,
            [(player.id, player.full_name, player.slug) for player in graph.players],
        )
        cur.executemany(
            INSERT_PICK_SQL,
            [
                (pick.id, pick.draft_year, pick.round, pick.original_team, pick.protections)
                for pick in graph.picks
            ],
        )
        cur.executemany(
            INSERT_TRANSACTION_SQL,
            [
                (
                    transaction.id,
                    transaction.occurred_on,
                    transaction.kind,
                    transaction.description,
                    transaction.group_key,
                    source_record_ids[transaction.source_key],
                    transaction.counterparties,
                    transaction.note,
                )
                for transaction in graph.transactions
            ],
        )
        cur.executemany(
            INSERT_MOVEMENT_SQL,
            [
                (
                    movement.transaction_id,
                    movement.asset_type,
                    movement.asset_id,
                    movement.from_holder,
                    movement.to_holder,
                    movement.contract_type,
                    movement.note,
                )
                for movement in graph.movements
            ],
        )
    conn.commit()


def select_feed_payload(conn) -> tuple[int, dict[str, Any]]:
    """Return (source_record id, payload) for the most recently fetched feed record."""
    with conn.cursor() as cur:
        cur.execute(
            "select id, payload from lineage.source_record where source = %s "
            "order by fetched_at desc, id desc limit 1",
            (SOURCE_FEED,),
        )
        row = cur.fetchone()
    if row is None:
        raise DeriveError(
            f"no source_record with source={SOURCE_FEED!r}; run `lineage fetch` first"
        )
    payload = row[1]
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    return row[0], payload


def load_inputs(data_dir: Path) -> tuple[Snapshot, PickEvents, Corrections]:
    """Read the three curated data files."""
    return (
        load_snapshot(data_dir / "opening_snapshot_2025_26.json"),
        load_pick_events(data_dir / "pick_events.json"),
        load_corrections(data_dir / "corrections.json"),
    )


def print_counts(graph: DerivedGraph) -> None:
    """Print the derived row counts, plus any notes validate should look at."""
    print(
        f"players={len(graph.players)} picks={len(graph.picks)} "
        f"transactions={len(graph.transactions)} movements={len(graph.movements)}"
    )
    for note in graph.notes:
        print(f"note: {note}")
