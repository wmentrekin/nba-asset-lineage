"""Validates a DerivedGraph against the invariants the whole pipeline depends on.

`validate_graph` is a pure function of (DerivedGraph, Snapshot, PickEvents) - offline,
deterministic, no database - so it can run against a feed fixture or against the DB inputs
`derive` itself would read. Each check produces zero or more `Finding`s; errors fail the load,
warnings are informational (or fail it too, under `--strict`).
"""

import json
import pathlib
from dataclasses import dataclass

from lineage.db import connect
from lineage.derive import (
    KIND_BASELINE,
    KIND_DRAFT_SELECTION,
    DerivedGraph,
    build_graph,
    load_inputs,
    select_feed_payload,
)
from lineage.parse import (
    DRAFT_POOL,
    FREE_AGENCY,
    KIND_SIGNING,
    KIND_TEN_DAY,
    KIND_TRADE,
    KIND_TWO_WAY_CONVERSION,
    KIND_TWO_WAY_SIGNING,
    KIND_WAIVER,
    PICK_USED,
)
from lineage.picks import PickEvents, UNCURATED_NOTE
from lineage.snapshot import Snapshot
from lineage.teams import MEM, TRICODES
from lineage.timeline import by_asset

LEVEL_ERROR = "error"
LEVEL_WARN = "warn"

ALLOWED_KINDS = frozenset(
    {
        KIND_BASELINE,
        KIND_TRADE,
        KIND_WAIVER,
        KIND_SIGNING,
        KIND_TWO_WAY_SIGNING,
        KIND_TWO_WAY_CONVERSION,
        KIND_TEN_DAY,
        KIND_DRAFT_SELECTION,
    }
)

# Holders a first (origin) movement may legitimately carry: the entering-holder pool plus
# any non-Memphis NBA team. MEM itself is never a valid origin - an asset cannot arrive at
# MEM without a movement that says so.
_ENTERING_HOLDERS = frozenset({FREE_AGENCY, DRAFT_POOL}) | (TRICODES - {MEM})


@dataclass(frozen=True)
class Finding:
    level: str  # 'error' | 'warn'
    code: str
    message: str


def load_graph_for_validation(
    feed_fixture: str | None, data_dir: pathlib.Path
) -> tuple[DerivedGraph, Snapshot, PickEvents]:
    """Build the graph to validate, offline from a fixture or from the DB inputs.

    Reuses derive's own input-loading helpers (`load_inputs`, `select_feed_payload`,
    `build_graph`) rather than re-reading the curated files or the feed a second way.
    """
    snapshot, pick_events, corrections = load_inputs(data_dir)
    if feed_fixture:
        feed_payload = json.loads(pathlib.Path(feed_fixture).read_text())
    else:
        with connect() as conn:
            _, feed_payload = select_feed_payload(conn)
    graph = build_graph(feed_payload, snapshot, pick_events, corrections)
    return graph, snapshot, pick_events


def validate_graph(
    graph: DerivedGraph, snapshot: Snapshot, pick_events: PickEvents
) -> list[Finding]:
    """Run every check and return all findings, errors before warnings."""
    findings: list[Finding] = []
    findings += _check_chain_continuity(graph)  # E1
    findings += _check_no_duplicate_movements(graph)  # E2
    findings += _check_kinds_and_asset_existence(graph)  # E3
    findings += _check_baseline(graph, snapshot)  # E4
    findings += _check_draft_selection_movements(graph)  # E5
    findings += _check_uncurated_draft_considerations(graph)  # W1
    findings += _check_todo_draft_selections(pick_events)  # W2
    findings += _check_unverified_snapshot_players(snapshot)  # W3
    return findings


def _check_chain_continuity(graph: DerivedGraph) -> list[Finding]:
    """E1: every asset's movement chain is continuous."""
    findings: list[Finding] = []
    for (asset_type, asset_id), movements in by_asset(graph.movements).items():
        previous_to_holder: str | None = None
        for index, movement in enumerate(movements):
            if index == 0:
                if movement.from_holder is not None and movement.from_holder not in (
                    _ENTERING_HOLDERS
                ):
                    findings.append(
                        Finding(
                            LEVEL_ERROR,
                            "E1",
                            f"{asset_type} {asset_id}: first movement ({movement.transaction_id}) "
                            f"has from_holder {movement.from_holder!r}, which is neither "
                            "baseline (null) nor an entering holder",
                        )
                    )
            elif movement.from_holder != previous_to_holder:
                findings.append(
                    Finding(
                        LEVEL_ERROR,
                        "E1",
                        f"{asset_type} {asset_id}: {movement.transaction_id} has from_holder "
                        f"{movement.from_holder!r}, but the prior movement left it at "
                        f"{previous_to_holder!r}",
                    )
                )
            previous_to_holder = movement.to_holder
    return findings


def _check_no_duplicate_movements(graph: DerivedGraph) -> list[Finding]:
    """E2: no asset has two movements in the same transaction."""
    findings: list[Finding] = []
    seen: set[tuple[str, str, str]] = set()
    for movement in graph.movements:
        key = (movement.transaction_id, movement.asset_type, movement.asset_id)
        if key in seen:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "E2",
                    f"duplicate movement for {movement.asset_type} {movement.asset_id} in "
                    f"transaction {movement.transaction_id}",
                )
            )
        seen.add(key)
    return findings


def _check_kinds_and_asset_existence(graph: DerivedGraph) -> list[Finding]:
    """E3: every transaction kind is allowed; every movement asset exists."""
    findings: list[Finding] = []
    for transaction in graph.transactions:
        if transaction.kind not in ALLOWED_KINDS:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "E3",
                    f"transaction {transaction.id} has unknown kind {transaction.kind!r}",
                )
            )

    player_ids = {str(player.id) for player in graph.players}
    pick_ids = {pick.id for pick in graph.picks}
    for movement in graph.movements:
        known_ids = player_ids if movement.asset_type == "player" else pick_ids
        if movement.asset_id not in known_ids:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "E3",
                    f"transaction {movement.transaction_id} moves {movement.asset_type} "
                    f"{movement.asset_id}, which does not exist",
                )
            )
    return findings


def _check_baseline(graph: DerivedGraph, snapshot: Snapshot) -> list[Finding]:
    """E4: exactly one baseline transaction, dated as_of, one movement per snapshot row."""
    findings: list[Finding] = []
    baselines = [t for t in graph.transactions if t.kind == KIND_BASELINE]
    if len(baselines) != 1:
        findings.append(
            Finding(
                LEVEL_ERROR, "E4", f"expected exactly one baseline transaction, found {len(baselines)}"
            )
        )
        return findings

    baseline = baselines[0]
    if baseline.occurred_on != snapshot.as_of:
        findings.append(
            Finding(
                LEVEL_ERROR,
                "E4",
                f"baseline {baseline.id} is dated {baseline.occurred_on}, expected "
                f"snapshot as_of {snapshot.as_of}",
            )
        )

    movements = [m for m in graph.movements if m.transaction_id == baseline.id]
    player_count = sum(1 for m in movements if m.asset_type == "player")
    pick_count = sum(1 for m in movements if m.asset_type == "pick")
    if player_count != len(snapshot.players):
        findings.append(
            Finding(
                LEVEL_ERROR,
                "E4",
                f"baseline has {player_count} player movements, expected "
                f"{len(snapshot.players)} (one per snapshot player)",
            )
        )
    if pick_count != len(snapshot.picks):
        findings.append(
            Finding(
                LEVEL_ERROR,
                "E4",
                f"baseline has {pick_count} pick movements, expected {len(snapshot.picks)} "
                "(one per snapshot pick)",
            )
        )
    return findings


def _check_draft_selection_movements(graph: DerivedGraph) -> list[Finding]:
    """E5: every draft_selection transaction has exactly its pick-used + player-drafted pair."""
    findings: list[Finding] = []
    for transaction in graph.transactions:
        if transaction.kind != KIND_DRAFT_SELECTION:
            continue
        movements = [m for m in graph.movements if m.transaction_id == transaction.id]
        pick_used = [
            m
            for m in movements
            if m.asset_type == "pick" and m.from_holder == MEM and m.to_holder == PICK_USED
        ]
        player_drafted = [
            m
            for m in movements
            if m.asset_type == "player" and m.from_holder == DRAFT_POOL and m.to_holder == MEM
        ]
        if len(movements) != 2 or len(pick_used) != 1 or len(player_drafted) != 1:
            findings.append(
                Finding(
                    LEVEL_ERROR,
                    "E5",
                    f"draft selection {transaction.id} does not have exactly one MEM->USED "
                    "pick movement and one DRAFT->MEM player movement",
                )
            )
    return findings


def _check_uncurated_draft_considerations(graph: DerivedGraph) -> list[Finding]:
    """W1: a trade with draft-consideration markers but no curated pick movements."""
    return [
        Finding(LEVEL_WARN, "W1", f"{transaction.id}: {UNCURATED_NOTE}")
        for transaction in graph.transactions
        if transaction.note == UNCURATED_NOTE
    ]


def _check_todo_draft_selections(pick_events: PickEvents) -> list[Finding]:
    """W2: a draft_selections entry with pick_id == 'TODO'."""
    return [
        Finding(
            LEVEL_WARN,
            "W2",
            f"draft selection of {selection.player_name} ({selection.player_id}) on "
            f"{selection.date.isoformat()} has pick_id TODO",
        )
        for selection in pick_events.draft_selections
        if selection.is_todo
    ]


def _check_unverified_snapshot_players(snapshot: Snapshot) -> list[Finding]:
    """W3: a snapshot row with verified: false."""
    return [
        Finding(LEVEL_WARN, "W3", f"snapshot player {player.name!r} is not verified")
        for player in snapshot.players
        if not player.verified
    ]


def format_report(findings: list[Finding]) -> str:
    """A readable report grouped by level, ordered and counted."""
    errors = [f for f in findings if f.level == LEVEL_ERROR]
    warnings = [f for f in findings if f.level == LEVEL_WARN]

    lines = [f"Errors ({len(errors)}):"]
    lines += [f"  [{f.code}] {f.message}" for f in errors] or ["  (none)"]
    lines.append(f"Warnings ({len(warnings)}):")
    lines += [f"  [{f.code}] {f.message}" for f in warnings] or ["  (none)"]
    return "\n".join(lines)


def run_validate(feed_fixture: str | None, data_dir: pathlib.Path, strict: bool) -> int:
    """Build, validate and print a report; return the process exit code."""
    graph, snapshot, pick_events = load_graph_for_validation(feed_fixture, data_dir)
    findings = validate_graph(graph, snapshot, pick_events)
    print(format_report(findings))

    has_errors = any(f.level == LEVEL_ERROR for f in findings)
    has_warnings = any(f.level == LEVEL_WARN for f in findings)
    if has_errors or (strict and has_warnings):
        return 1
    return 0
