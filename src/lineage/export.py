"""Builds graph.json: the deterministic, servable projection of a DerivedGraph.

`build_export` is pure - it takes a DerivedGraph plus the snapshot's `as_of` date and returns
the plain dict described in docs/mvp-one-season-reset/plan.yaml's `graph.json` contract.
`run_export` is the thin I/O half: build the same way `derive`/`validate` do, then write the
file.
"""

import datetime as dt
import json
import pathlib
from typing import Any

from lineage.db import connect
from lineage.derive import DerivedGraph, Pick, build_graph, load_inputs, select_feed_payload
from lineage.snapshot import Snapshot
from lineage.timeline import Segment, build_timelines


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


def _assets(graph: DerivedGraph) -> list[dict[str, Any]]:
    players = sorted(
        (
            {"id": str(player.id), "type": "player", "label": player.full_name}
            for player in graph.players
        ),
        key=lambda asset: asset["label"],
    )
    picks = sorted(
        ({"id": pick.id, "type": "pick", "label": pick_label(pick)} for pick in graph.picks),
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


def build_export(graph: DerivedGraph, as_of: dt.date) -> dict[str, Any]:
    """Return the graph.json dict for `graph`, windowed from `as_of` to its last transaction.

    `end` is simply the max `occurred_on` over every transaction, `expiry` ones included, even
    though a 10-day expiry can land after the last real feed transaction.
    """
    end = max((t.occurred_on for t in graph.transactions), default=as_of)
    assets = _assets(graph)
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
    return build_export(graph, snapshot.as_of), snapshot


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
