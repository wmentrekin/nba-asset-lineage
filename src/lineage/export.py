"""Builds graph.json: the deterministic, servable projection of a DerivedGraph.

`build_export` is pure - it takes a DerivedGraph plus the curated Snapshot (for `as_of` and
each player's `mem_since`) and returns the plain dict described in
docs/mvp-one-season-reset/plan.yaml's `graph.json` contract. Player assets carry a
`tenure_start` (and any `tenure_tier_changes`); pick assets carry a `sort_key`. `run_export`
is the thin I/O half: build the same way `derive`/`validate` do, then write the file.
"""

import datetime as dt
import json
import pathlib
from typing import Any

from lineage.db import connect
from lineage.derive import (
    KIND_BASELINE,
    DerivedGraph,
    Pick,
    build_graph,
    load_inputs,
    select_feed_payload,
)
from lineage.parse import CONTRACT_TWO_WAY
from lineage.snapshot import Snapshot
from lineage.teams import MEM
from lineage.timeline import Movement, Segment, build_timelines, by_asset


def pick_label(pick: Pick) -> str:
    """A pick's display label, e.g. '2030 R1 (ORL)'."""
    return f"{pick.draft_year} R{pick.round} ({pick.original_team})"


def _nodes(graph: DerivedGraph) -> list[dict[str, Any]]:
    ordered = sorted(graph.transactions, key=lambda t: (t.occurred_on, t.id))
    return [
        {
            "id": t.id,
            "date": t.occurred_on.isoformat(),
            "kind": t.kind,
            "description": t.description,
            "counterparties": list(t.counterparties),
            "note": t.note,
        }
        for t in ordered
    ]


def _snapshot_mem_since_by_person_id(snapshot: Snapshot) -> dict[int, dt.date]:
    """Map resolved snapshot player person_id -> mem_since (only players with an id)."""
    return {
        player.person_id: player.mem_since
        for player in snapshot.players
        if player.person_id is not None
    }


def _baseline_player_ids(graph: DerivedGraph) -> set[int]:
    """Person ids of every player the opening-night baseline transaction placed at MEM."""
    baseline_id = next(t.id for t in graph.transactions if t.kind == KIND_BASELINE)
    return {
        int(movement.asset_id)
        for movement in graph.movements
        if movement.transaction_id == baseline_id and movement.asset_type == "player"
    }


def _first_mem_tenure_start(player_movements: list[Movement]) -> dt.date:
    """First movement into MEM on a contract that counts (anything but two-way);
    the first MEM movement at all when the player has only ever been two-way."""
    mem_moves = [movement for movement in player_movements if movement.to_holder == MEM]
    if not mem_moves:
        raise ValueError("player has no movement into MEM to derive a tenure_start from")
    non_two_way = [
        movement for movement in mem_moves if movement.contract_type != CONTRACT_TWO_WAY
    ]
    return (non_two_way or mem_moves)[0].occurred_on


def _tenure_tier_changes(player_movements: list[Movement]) -> list[dict[str, Any]]:
    """MEM->MEM movements where contract_type changes, e.g. a two-way conversion or a
    drafted player's rookie signing, so the renderer can restart tenure without recomputing.
    """
    changes: list[dict[str, Any]] = []
    current_type: str | None = None
    for movement in player_movements:
        if movement.to_holder != MEM:
            current_type = None
            continue
        if (
            movement.from_holder == MEM
            and current_type is not None
            and movement.contract_type != current_type
        ):
            changes.append(
                {
                    "node": movement.transaction_id,
                    "date": movement.occurred_on.isoformat(),
                    "to_contract_type": movement.contract_type,
                }
            )
        current_type = movement.contract_type
    return changes


def _player_tenure(
    player_id: int,
    label: str,
    baseline_ids: set[int],
    mem_since_by_id: dict[int, dt.date],
    player_movements: list[Movement],
) -> tuple[dt.date, list[dict[str, Any]]]:
    if player_id in baseline_ids:
        mem_since = mem_since_by_id.get(player_id)
        if mem_since is None:
            raise ValueError(f"snapshot player {label!r} has no mem_since")
        tenure_start = mem_since
    else:
        tenure_start = _first_mem_tenure_start(player_movements)
    return tenure_start, _tenure_tier_changes(player_movements)


def _assets(graph: DerivedGraph, snapshot: Snapshot) -> list[dict[str, Any]]:
    baseline_ids = _baseline_player_ids(graph)
    mem_since_by_id = _snapshot_mem_since_by_person_id(snapshot)
    movements_by_asset = by_asset(graph.movements)

    players = []
    for player in graph.players:
        player_movements = movements_by_asset.get(("player", str(player.id)), [])
        tenure_start, tier_changes = _player_tenure(
            player.id, player.full_name, baseline_ids, mem_since_by_id, player_movements
        )
        players.append(
            {
                "id": str(player.id),
                "type": "player",
                "label": player.full_name,
                "tenure_start": tenure_start.isoformat(),
                "tenure_tier_changes": tier_changes,
            }
        )
    players.sort(key=lambda asset: asset["label"])

    picks = sorted(
        (
            {
                "id": pick.id,
                "type": "pick",
                "label": pick_label(pick),
                "sort_key": [pick.round, pick.draft_year, pick.original_team],
            }
            for pick in graph.picks
        ),
        key=lambda asset: asset["label"],
    )
    return players + picks


def _segment_dict(segment: Segment) -> dict[str, Any]:
    return {
        "from_node": segment.from_node,
        "to_node": segment.to_node,
        "holder": segment.holder,
        "contract_type": segment.contract_type,
    }


def _strands(graph: DerivedGraph, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timelines = build_timelines(graph.movements)
    strands = []
    for asset in assets:
        segments = timelines.get((asset["type"], asset["id"]), [])
        strands.append(
            {
                "asset_id": asset["id"],
                "asset_type": asset["type"],
                "segments": [_segment_dict(segment) for segment in segments],
            }
        )
    return strands


def build_export(graph: DerivedGraph, snapshot: Snapshot) -> dict[str, Any]:
    """Return the graph.json dict for `graph`, windowed from `snapshot.as_of` to the last
    transaction. Player assets carry `tenure_start` (and any `tenure_tier_changes`), pick
    assets carry `sort_key`, both computed from `graph` plus `snapshot`'s `mem_since` data.

    `end` is simply the max `occurred_on` over every transaction, `expiry` ones included, even
    though a 10-day expiry can land after the last real feed transaction.
    """
    as_of = snapshot.as_of
    end = max((t.occurred_on for t in graph.transactions), default=as_of)
    assets = _assets(graph, snapshot)
    return {
        "window": {"start": as_of.isoformat(), "end": end.isoformat()},
        "nodes": _nodes(graph),
        "assets": assets,
        "strands": _strands(graph, assets),
    }


def build_export_from_inputs(
    feed_fixture: str | None, data_dir: pathlib.Path
) -> tuple[dict[str, Any], Snapshot]:
    """Build the graph the same way `derive`/`validate` do, then export it."""
    snapshot, curated, corrections = load_inputs(data_dir)
    if feed_fixture:
        feed_payload = json.loads(pathlib.Path(feed_fixture).read_text())
    else:
        with connect() as conn:
            _, feed_payload = select_feed_payload(conn)
    graph = build_graph(feed_payload, snapshot, curated, corrections)
    return build_export(graph, snapshot), snapshot


def run_export(feed_fixture: str | None, data_dir: pathlib.Path, out_path: pathlib.Path) -> dict:
    """Build graph.json, write it to `out_path`, print counts, and return the dict."""
    export, _ = build_export_from_inputs(feed_fixture, data_dir)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(export, indent=2) + "\n")

    print(
        f"nodes={len(export['nodes'])} assets={len(export['assets'])} "
        f"strands={len(export['strands'])} -> {out_path}"
    )
    return export
