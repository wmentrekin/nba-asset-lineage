from __future__ import annotations

import xml.etree.ElementTree as ET

from nba_asset_lineage.files import read_csv, write_csv
from nba_asset_lineage.settings import EXPORTS_DIR, PROCESSED_DIR


def _write_graphml(nodes: list[dict[str, str]], edges: list[dict[str, str]]) -> None:
    node_attrs = [
        "node_type",
        "label",
        "event_type",
        "event_date",
        "description",
        "source_name",
        "source_url",
    ]
    edge_attrs = [
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
    ]

    graphml_ns = "http://graphml.graphdrawing.org/xmlns"
    ET.register_namespace("", graphml_ns)
    root = ET.Element(f"{{{graphml_ns}}}graphml")

    for attr in node_attrs:
        ET.SubElement(
            root,
            f"{{{graphml_ns}}}key",
            attrib={
                "id": f"n_{attr}",
                "for": "node",
                "attr.name": attr,
                "attr.type": "string",
            },
        )
    for attr in edge_attrs:
        ET.SubElement(
            root,
            f"{{{graphml_ns}}}key",
            attrib={
                "id": f"e_{attr}",
                "for": "edge",
                "attr.name": attr,
                "attr.type": "string",
            },
        )

    graph = ET.SubElement(
        root,
        f"{{{graphml_ns}}}graph",
        attrib={"id": "memphis_asset_lineage", "edgedefault": "directed"},
    )

    for node in nodes:
        node_element = ET.SubElement(
            graph,
            f"{{{graphml_ns}}}node",
            attrib={"id": node["node_id"]},
        )
        for attr in node_attrs:
            data = ET.SubElement(
                node_element,
                f"{{{graphml_ns}}}data",
                attrib={"key": f"n_{attr}"},
            )
            data.text = node.get(attr, "")

    for edge in edges:
        edge_element = ET.SubElement(
            graph,
            f"{{{graphml_ns}}}edge",
            attrib={
                "id": edge["edge_id"],
                "source": edge["source_node_id"],
                "target": edge["target_node_id"],
            },
        )
        for attr in edge_attrs:
            data = ET.SubElement(
                edge_element,
                f"{{{graphml_ns}}}data",
                attrib={"key": f"e_{attr}"},
            )
            data.text = edge.get(attr, "")

    tree = ET.ElementTree(root)
    tree.write(EXPORTS_DIR / "memphis_asset_lineage.graphml", encoding="utf-8", xml_declaration=True)


def run_export(context: dict[str, str]) -> None:
    del context

    nodes = read_csv(PROCESSED_DIR / "graph_nodes.csv")
    edges = read_csv(PROCESSED_DIR / "graph_edges.csv")

    _write_graphml(nodes, edges)

    write_csv(
        EXPORTS_DIR / "nodes.csv",
        nodes,
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
        EXPORTS_DIR / "edges.csv",
        edges,
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
