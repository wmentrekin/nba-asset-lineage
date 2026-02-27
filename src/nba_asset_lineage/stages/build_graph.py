from __future__ import annotations

from nba_asset_lineage.files import read_csv, write_csv
from nba_asset_lineage.settings import PROCESSED_DIR


def run_build_graph(context: dict[str, str]) -> None:
    del context

    events = read_csv(PROCESSED_DIR / "events.csv")
    state_nodes = read_csv(PROCESSED_DIR / "state_nodes.csv")
    asset_segments = read_csv(PROCESSED_DIR / "asset_segments.csv")

    nodes: list[dict[str, str]] = []
    for row in state_nodes:
        nodes.append(
            {
                "node_id": row["node_id"],
                "node_type": row["node_type"],
                "label": row["label"],
                "event_type": "",
                "event_date": row["event_date"],
                "description": "",
                "source_name": "",
                "source_url": "",
            }
        )

    for row in events:
        nodes.append(
            {
                "node_id": row["event_id"],
                "node_type": "event",
                "label": row["event_label"] or row["event_type"],
                "event_type": row["event_type"],
                "event_date": row["event_date"],
                "description": row["description"],
                "source_name": row["source_name"],
                "source_url": row["source_url"],
            }
        )

    edges = [
        {
            "edge_id": row["edge_id"],
            "source_node_id": row["source_node_id"],
            "target_node_id": row["target_node_id"],
            "asset_id": row["asset_id"],
            "asset_key": row["asset_key"],
            "asset_type": row["asset_type"],
            "subtype": row["subtype"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "is_active_at_end": row["is_active_at_end"],
            "player_name": row["player_name"],
            "contract_expiry_year": row["contract_expiry_year"],
            "average_annual_salary": row["average_annual_salary"],
            "acquisition_method": row["acquisition_method"],
            "original_team": row["original_team"],
            "pick_year": row["pick_year"],
            "pick_number": row["pick_number"],
            "protections_raw": row["protections_raw"],
            "protections_structured": row["protections_structured"],
            "swap_conditions_raw": row["swap_conditions_raw"],
            "swap_conditions_structured": row["swap_conditions_structured"],
            "prior_transactions": row["prior_transactions"],
        }
        for row in asset_segments
    ]

    write_csv(
        PROCESSED_DIR / "graph_nodes.csv",
        sorted(nodes, key=lambda row: (row["event_date"], row["node_id"])),
        [
            "node_id",
            "node_type",
            "label",
            "event_type",
            "event_date",
            "description",
            "source_name",
            "source_url",
        ],
    )

    write_csv(
        PROCESSED_DIR / "graph_edges.csv",
        sorted(edges, key=lambda row: (row["asset_id"], row["start_date"], row["edge_id"])),
        [
            "edge_id",
            "source_node_id",
            "target_node_id",
            "asset_id",
            "asset_key",
            "asset_type",
            "subtype",
            "start_date",
            "end_date",
            "is_active_at_end",
            "player_name",
            "contract_expiry_year",
            "average_annual_salary",
            "acquisition_method",
            "original_team",
            "pick_year",
            "pick_number",
            "protections_raw",
            "protections_structured",
            "swap_conditions_raw",
            "swap_conditions_structured",
            "prior_transactions",
        ],
    )
