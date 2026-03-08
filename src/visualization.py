from __future__ import annotations

import csv
import json
from pathlib import Path

from settings import DEFAULT_EXPORTS_DIR


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def _event_date_bounds(nodes: list[dict[str, str]]) -> tuple[str, str]:
    event_dates = sorted(
        {
            n.get("event_date", "")
            for n in nodes
            if n.get("node_type") == "event" and n.get("event_date", "")
        }
    )
    if not event_dates:
        return "", ""
    return event_dates[0], event_dates[-1]


def _event_types(nodes: list[dict[str, str]]) -> list[str]:
    return sorted({n.get("event_type", "") for n in nodes if n.get("event_type", "")})


def _html(nodes: list[dict[str, str]], edges: list[dict[str, str]], start: str, end: str, types: list[str]) -> str:
    payload = json.dumps(
        {
            "nodes": nodes,
            "edges": edges,
            "start": start,
            "end": end,
            "types": types,
        }
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Grizzlies Asset Lineage</title>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: #f7f3ec;
      color: #1f2933;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 12px;
      padding: 12px;
      height: 100vh;
    }}
    .panel {{
      border: 1px solid #d5c7ad;
      border-radius: 10px;
      background: #fffaf2;
      padding: 12px;
      overflow: auto;
    }}
    .panel h1 {{
      margin: 0 0 8px;
      font-size: 18px;
    }}
    .control {{
      margin-bottom: 8px;
    }}
    input, select, button {{
      width: 100%;
      padding: 8px;
      border-radius: 8px;
      border: 1px solid #d5c7ad;
      background: #fff;
    }}
    .row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 8px;
    }}
    #detail {{
      margin-top: 8px;
      font-family: "IBM Plex Mono", Menlo, monospace;
      font-size: 11px;
      white-space: pre-wrap;
      border: 1px dashed #d5c7ad;
      border-radius: 8px;
      background: #fff;
      padding: 8px;
      min-height: 140px;
    }}
    #graph {{
      border: 1px solid #d5c7ad;
      border-radius: 10px;
      background: #fff;
    }}
    @media (max-width: 1000px) {{
      .layout {{
        grid-template-columns: 1fr;
        grid-template-rows: auto 1fr;
        height: auto;
      }}
      #graph {{ height: 70vh; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="panel">
      <h1>Asset Lineage</h1>
      <div class="control"><input id="start" type="date" /></div>
      <div class="control"><input id="end" type="date" /></div>
      <div class="control"><select id="types" multiple size="8"></select></div>
      <div class="row">
        <button id="apply">Apply</button>
        <button id="reset">Reset</button>
      </div>
      <div id="stats" style="margin-top:8px;font-size:12px;"></div>
      <div id="detail">Click node/edge for attributes.</div>
    </aside>
    <main id="graph"></main>
  </div>
<script>
const payload = {payload};
const startEl = document.getElementById("start");
const endEl = document.getElementById("end");
const typeEl = document.getElementById("types");
const statsEl = document.getElementById("stats");
const detailEl = document.getElementById("detail");

startEl.value = payload.start || "";
endEl.value = payload.end || "";
payload.types.forEach((t) => {{
  const opt = document.createElement("option");
  opt.value = t;
  opt.textContent = t;
  opt.selected = true;
  typeEl.appendChild(opt);
}});

const allNodes = payload.nodes.map((n) => ({{
  ...n,
  id: n.node_id,
  label: n.label || n.node_id,
  shape: n.node_type === "state_boundary" ? "box" : "dot",
  color: n.node_type === "state_boundary" ? "#264653" : "#2a9d8f",
  title: JSON.stringify(n, null, 2),
}}));
const allEdges = payload.edges.map((e) => ({{
  ...e,
  id: e.edge_id,
  from: e.source_node_id,
  to: e.target_node_id,
  label: e.player_name || e.asset_key || e.asset_id,
  arrows: "to",
  title: JSON.stringify(e, null, 2),
}}));
const nodesById = Object.fromEntries(allNodes.map((n) => [n.id, n]));
const edgesById = Object.fromEntries(allEdges.map((e) => [e.id, e]));

const nodeDS = new vis.DataSet([]);
const edgeDS = new vis.DataSet([]);
const net = new vis.Network(document.getElementById("graph"), {{nodes: nodeDS, edges: edgeDS}}, {{
  interaction: {{hover: true}},
  physics: {{stabilization: false}},
}});

function selectedTypes() {{
  return new Set(Array.from(typeEl.selectedOptions).map((o) => o.value));
}}

function inRange(edgeStart, edgeEnd, start, end) {{
  const s = edgeStart || "";
  const e = edgeEnd || "9999-12-31";
  return s <= end && e >= start;
}}

function applyFilters() {{
  const start = startEl.value || payload.start;
  const end = endEl.value || payload.end;
  const types = selectedTypes();

  const visibleNodeIds = new Set();
  const nodes = allNodes.filter((n) => {{
    if (n.node_type !== "event") {{
      visibleNodeIds.add(n.id);
      return true;
    }}
    const okDate = n.event_date >= start && n.event_date <= end;
    const okType = types.size === 0 || types.has(n.event_type);
    if (okDate && okType) visibleNodeIds.add(n.id);
    return okDate && okType;
  }});
  const edges = allEdges.filter((e) => (
    inRange(e.start_date, e.end_date, start, end) &&
    visibleNodeIds.has(e.source_node_id) &&
    visibleNodeIds.has(e.target_node_id)
  ));

  nodeDS.clear(); edgeDS.clear();
  nodeDS.add(nodes); edgeDS.add(edges);
  statsEl.textContent = `Nodes: ${{nodes.length}} | Edges: ${{edges.length}}`;
  net.fit({{animation: true}});
}}

document.getElementById("apply").addEventListener("click", applyFilters);
document.getElementById("reset").addEventListener("click", () => {{
  startEl.value = payload.start || "";
  endEl.value = payload.end || "";
  Array.from(typeEl.options).forEach((o) => o.selected = true);
  applyFilters();
}});

net.on("click", (params) => {{
  if (params.nodes.length) {{
    detailEl.textContent = nodesById[params.nodes[0]].title;
    return;
  }}
  if (params.edges.length) {{
    detailEl.textContent = edgesById[params.edges[0]].title;
    return;
  }}
  detailEl.textContent = "Click node/edge for attributes.";
}});

applyFilters();
</script>
</body>
</html>
"""


def write_visualization_html(
    output_path: Path,
    nodes_path: Path | None = None,
    edges_path: Path | None = None,
) -> Path:
    nodes_path = nodes_path or (DEFAULT_EXPORTS_DIR / "nodes.csv")
    edges_path = edges_path or (DEFAULT_EXPORTS_DIR / "edges.csv")
    nodes = _read_csv(nodes_path)
    edges = _read_csv(edges_path)
    start, end = _event_date_bounds(nodes)
    html = _html(nodes, edges, start, end, _event_types(nodes))
    _ensure_dir(output_path.parent)
    output_path.write_text(html, encoding="utf-8")
    return output_path

