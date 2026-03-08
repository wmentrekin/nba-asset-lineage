from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from db_config import load_db_config
from settings import DEFAULT_EXPORTS_DIR


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _serialize_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _resolve_date_str(value: str, fallback: str) -> str:
    candidate = (value or "").strip().lower()
    if candidate in {"", "rolling", "today", "present"}:
        return fallback
    return value


def _write_graphml(path: Path, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    ns = "http://graphml.graphdrawing.org/xmlns"
    ET.register_namespace("", ns)

    root = ET.Element(f"{{{ns}}}graphml")

    node_keys = [
        ("node_type", "string"),
        ("label", "string"),
        ("event_date", "string"),
        ("event_type", "string"),
        ("source_system", "string"),
    ]
    edge_keys = [
        ("asset_id", "string"),
        ("asset_key", "string"),
        ("asset_type", "string"),
        ("subtype", "string"),
        ("start_date", "string"),
        ("end_date", "string"),
        ("is_active_at_end", "string"),
        ("player_name", "string"),
        ("action_raw", "string"),
        ("direction_raw", "string"),
    ]

    for index, (name, attr_type) in enumerate(node_keys, start=1):
        ET.SubElement(
            root,
            f"{{{ns}}}key",
            id=f"n{index}",
            **{"for": "node", "attr.name": name, "attr.type": attr_type},
        )
    for index, (name, attr_type) in enumerate(edge_keys, start=1):
        ET.SubElement(
            root,
            f"{{{ns}}}key",
            id=f"e{index}",
            **{"for": "edge", "attr.name": name, "attr.type": attr_type},
        )

    graph = ET.SubElement(root, f"{{{ns}}}graph", id="asset_lineage", edgedefault="directed")

    for node in nodes:
        node_elem = ET.SubElement(graph, f"{{{ns}}}node", id=str(node["node_id"]))
        for index, (name, _) in enumerate(node_keys, start=1):
            value = node.get(name, "")
            ET.SubElement(node_elem, f"{{{ns}}}data", key=f"n{index}").text = str(value)

    for edge in edges:
        edge_elem = ET.SubElement(
            graph,
            f"{{{ns}}}edge",
            id=str(edge["edge_id"]),
            source=str(edge["source_node_id"]),
            target=str(edge["target_node_id"]),
        )
        for index, (name, _) in enumerate(edge_keys, start=1):
            value = edge.get(name, "")
            ET.SubElement(edge_elem, f"{{{ns}}}data", key=f"e{index}").text = str(value)

    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def run_gold_publish(context: dict[str, str]) -> dict[str, object]:
    exports_dir = DEFAULT_EXPORTS_DIR
    _ensure_dir(exports_dir)

    config = load_db_config()
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for gold export.") from exc

    with psycopg.connect(config.dsn) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                select
                    event_id, source_system, source_event_ref, event_date, event_type,
                    event_label, description, source_url, team_id, event_order,
                    franchise_id, operating_team_id
                from silver.events
                where franchise_id = %s
                order by event_date, event_order, event_id
                """,
                (context["franchise_id"],),
            )
            events = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                select
                    edge_id, asset_id, asset_key, source_system, source_asset_ref, asset_type,
                    subtype, start_date, end_date, is_active_at_end, player_name,
                    contract_expiry_year, average_annual_salary, acquisition_method,
                    prior_transactions, original_team, pick_year, pick_round, pick_number,
                    protections_raw, swap_conditions_raw, owner_team_id, franchise_id,
                    operating_team_id
                from silver.assets
                where franchise_id = %s
                order by start_date, edge_id
                """,
                (context["franchise_id"],),
            )
            assets = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                select
                    lineage_id, event_id, asset_id, action_raw, direction_raw, effective_date,
                    source_system, source_event_ref, source_asset_ref, source_link_id, franchise_id
                from silver.event_asset_lineage
                where franchise_id = %s
                order by effective_date, lineage_id
                """,
                (context["franchise_id"],),
            )
            lineage = [dict(row) for row in cur.fetchall()]

    if not events and not assets and not lineage:
        manifest = {
            "stage": "gold_publish",
            "status": "no_new_data",
            "franchise_id": context["franchise_id"],
            "run_mode": context["run_mode"],
            "as_of_date": context["as_of_date"],
            "notes": "No Silver records found.",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(manifest, sort_keys=True))
        return manifest

    start_date_str = _resolve_date_str(context["start_date"], context["as_of_date"])
    end_date_str = _resolve_date_str(context["end_date"], context["as_of_date"])

    assets_by_id: dict[str, dict[str, Any]] = {}
    for asset in assets:
        asset_id = str(asset["asset_id"])
        if asset_id not in assets_by_id:
            assets_by_id[asset_id] = asset

    start_node_id = "state_start"
    end_node_id = "state_end"
    nodes_csv: list[dict[str, Any]] = [
        {
            "node_id": start_node_id,
            "node_type": "state_boundary",
            "label": "State Start",
            "event_date": start_date_str,
            "event_type": "state_boundary",
            "source_system": "pipeline",
        },
        {
            "node_id": end_node_id,
            "node_type": "state_boundary",
            "label": "State End",
            "event_date": end_date_str,
            "event_type": "state_boundary",
            "source_system": "pipeline",
        },
    ]

    for event in events:
        nodes_csv.append(
            {
                "node_id": event["event_id"],
                "node_type": "event",
                "label": str(event.get("event_label") or event.get("event_type") or event["event_id"]),
                "event_date": _serialize_date(event.get("event_date")),
                "event_type": str(event.get("event_type") or ""),
                "source_system": str(event.get("source_system") or ""),
            }
        )

    by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in lineage:
        by_asset[str(row["asset_id"])].append(row)
    for asset_id in by_asset:
        by_asset[asset_id].sort(
            key=lambda row: (
                _serialize_date(row.get("effective_date")) or "0001-01-01",
                str(row.get("event_id") or ""),
                str(row.get("lineage_id") or ""),
            )
        )

    edges_csv: list[dict[str, Any]] = []
    for asset_id, asset_links in by_asset.items():
        if not asset_links:
            continue
        asset = assets_by_id.get(asset_id, {})
        asset_key = str(asset.get("asset_key") or asset_id)
        asset_type = str(asset.get("asset_type") or "unknown")
        subtype = str(asset.get("subtype") or "")
        player_name = str(asset.get("player_name") or "")

        first = asset_links[0]
        edges_csv.append(
            {
                "edge_id": f"{asset_id}_0",
                "asset_id": asset_id,
                "asset_key": asset_key,
                "asset_type": asset_type,
                "subtype": subtype,
                "source_node_id": start_node_id,
                "target_node_id": first["event_id"],
                "start_date": start_date_str,
                "end_date": _serialize_date(first.get("effective_date")),
                "is_active_at_end": "false",
                "player_name": player_name,
                "action_raw": str(first.get("action_raw") or ""),
                "direction_raw": str(first.get("direction_raw") or ""),
            }
        )

        for index in range(len(asset_links) - 1):
            current_link = asset_links[index]
            next_link = asset_links[index + 1]
            edges_csv.append(
                {
                    "edge_id": f"{asset_id}_{index + 1}",
                    "asset_id": asset_id,
                    "asset_key": asset_key,
                    "asset_type": asset_type,
                    "subtype": subtype,
                    "source_node_id": current_link["event_id"],
                    "target_node_id": next_link["event_id"],
                    "start_date": _serialize_date(current_link.get("effective_date")),
                    "end_date": _serialize_date(next_link.get("effective_date")),
                    "is_active_at_end": "false",
                    "player_name": player_name,
                    "action_raw": str(next_link.get("action_raw") or ""),
                    "direction_raw": str(next_link.get("direction_raw") or ""),
                }
            )

        last = asset_links[-1]
        edges_csv.append(
            {
                "edge_id": f"{asset_id}_end",
                "asset_id": asset_id,
                "asset_key": asset_key,
                "asset_type": asset_type,
                "subtype": subtype,
                "source_node_id": last["event_id"],
                "target_node_id": end_node_id,
                "start_date": _serialize_date(last.get("effective_date")),
                "end_date": end_date_str,
                "is_active_at_end": "true",
                "player_name": player_name,
                "action_raw": str(last.get("action_raw") or ""),
                "direction_raw": str(last.get("direction_raw") or ""),
            }
        )

    nodes_path = exports_dir / "nodes.csv"
    edges_path = exports_dir / "edges.csv"
    graphml_path = exports_dir / "graph.graphml"
    events_json_path = exports_dir / "events.json"
    assets_json_path = exports_dir / "assets.json"
    lineage_json_path = exports_dir / "event_asset_lineage.json"
    graph_json_path = exports_dir / "graph.json"

    _write_csv(
        nodes_path,
        ["node_id", "node_type", "label", "event_date", "event_type", "source_system"],
        nodes_csv,
    )
    _write_csv(
        edges_path,
        [
            "edge_id",
            "asset_id",
            "asset_key",
            "asset_type",
            "subtype",
            "source_node_id",
            "target_node_id",
            "start_date",
            "end_date",
            "is_active_at_end",
            "player_name",
            "action_raw",
            "direction_raw",
        ],
        edges_csv,
    )
    _write_graphml(graphml_path, nodes_csv, edges_csv)

    _write_json(events_json_path, events)
    _write_json(assets_json_path, assets)
    _write_json(lineage_json_path, lineage)
    _write_json(graph_json_path, {"nodes": nodes_csv, "edges": edges_csv})

    manifest = {
        "stage": "gold_publish",
        "status": "success",
        "franchise_id": context["franchise_id"],
        "run_mode": context["run_mode"],
        "as_of_date": context["as_of_date"],
        "exports": {
            "nodes_csv": str(nodes_path),
            "edges_csv": str(edges_path),
            "graphml": str(graphml_path),
            "events_json": str(events_json_path),
            "assets_json": str(assets_json_path),
            "lineage_json": str(lineage_json_path),
            "graph_json": str(graph_json_path),
        },
        "counts": {
            "events": len(events),
            "assets": len(assets),
            "lineage": len(lineage),
            "nodes": len(nodes_csv),
            "edges": len(edges_csv),
        },
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(manifest, sort_keys=True))
    return manifest
