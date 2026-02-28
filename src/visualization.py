from __future__ import annotations

import argparse
import json
from pathlib import Path

from files import ensure_dir, read_csv
from settings import DEFAULT_EXPORTS_DIR


def _sorted_event_types(nodes: list[dict[str, str]]) -> list[str]:
    values = sorted({node.get("event_type", "") for node in nodes if node.get("event_type", "")})
    return values


def _event_date_bounds(nodes: list[dict[str, str]]) -> tuple[str, str]:
    dates = sorted(
        {
            node.get("event_date", "")
            for node in nodes
            if node.get("event_date", "") and node.get("node_type") == "event"
        }
    )
    if not dates:
        return "", ""
    return dates[0], dates[-1]


def _html_template(
    nodes: list[dict[str, str]],
    edges: list[dict[str, str]],
    default_start: str,
    default_end: str,
    event_types: list[str],
) -> str:
    payload = {
        "nodes": nodes,
        "edges": edges,
        "defaultStart": default_start,
        "defaultEnd": default_end,
        "eventTypes": event_types,
    }
    payload_json = json.dumps(payload)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Memphis Asset Lineage Graph</title>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    :root {{
      --bg: #f4efe8;
      --panel: #fffaf2;
      --ink: #1d232b;
      --muted: #5f6670;
      --line: #d5c7ad;
      --accent: #0b5563;
      --accent-2: #a1432a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at top right, #f7dcc2 0%, var(--bg) 42%, #e9e3d7 100%);
      min-height: 100vh;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 330px minmax(0, 1fr);
      gap: 14px;
      padding: 14px;
      height: 100vh;
    }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel);
      padding: 12px;
      overflow: auto;
      box-shadow: 0 8px 30px rgba(15, 25, 35, 0.08);
    }}
    .panel h1 {{
      margin: 0 0 8px;
      font-size: 20px;
      line-height: 1.2;
    }}
    .small {{
      color: var(--muted);
      font-size: 12px;
      margin: 0 0 10px;
    }}
    .control {{ margin-bottom: 10px; }}
    label {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    input[type="date"], select, button {{
      width: 100%;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      padding: 8px;
      font-size: 13px;
    }}
    select {{ min-height: 96px; }}
    .button-row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 10px;
    }}
    button {{ cursor: pointer; font-weight: 600; }}
    button.primary {{
      background: var(--accent);
      color: white;
      border-color: transparent;
    }}
    button.secondary {{
      background: #f8f6f2;
    }}
    .stats {{
      margin-top: 10px;
      font-size: 12px;
      color: var(--muted);
      display: grid;
      grid-template-columns: 1fr;
      gap: 4px;
    }}
    #detail {{
      margin-top: 10px;
      font-family: "IBM Plex Mono", "Menlo", monospace;
      font-size: 11px;
      white-space: pre-wrap;
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 8px;
      background: #fff;
      min-height: 180px;
    }}
    #graph {{
      border: 1px solid var(--line);
      border-radius: 10px;
      background: linear-gradient(180deg, #fffdf9 0%, #f8f3ea 100%);
      height: calc(100vh - 28px);
      box-shadow: 0 8px 30px rgba(15, 25, 35, 0.08);
    }}
    @media (max-width: 1000px) {{
      .layout {{
        grid-template-columns: 1fr;
        grid-template-rows: auto minmax(480px, 1fr);
        height: auto;
      }}
      #graph {{ height: 72vh; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="panel">
      <h1>Memphis Asset Lineage</h1>
      <p class="small">Interactive view from exported CSVs. Select event types in the list (multi-select supported).</p>

      <div class="control">
        <label for="start-date">Start Date</label>
        <input id="start-date" type="date" />
      </div>
      <div class="control">
        <label for="end-date">End Date</label>
        <input id="end-date" type="date" />
      </div>
      <div class="control">
        <label for="event-types">Event Types</label>
        <select id="event-types" multiple></select>
      </div>
      <div class="button-row">
        <button id="apply" class="primary">Apply Filters</button>
        <button id="reset" class="secondary">Reset</button>
      </div>

      <div class="stats">
        <div id="stat-nodes"></div>
        <div id="stat-edges"></div>
      </div>

      <div id="detail">Click a node or edge to inspect attributes.</div>
    </aside>

    <main id="graph"></main>
  </div>

<script>
const payload = {payload_json};

const nodePalette = {{
  state_boundary: '#264653',
  event: '#2a9d8f'
}};

const eventTypePalette = {{
  trade: '#e76f51',
  draft_pick: '#f4a261',
  contract_signing: '#2a9d8f',
  extension: '#264653',
  re_signing: '#3a86ff',
  conversion: '#8338ec',
  waiver: '#6c757d'
}};

const assetTypePalette = {{
  player: '#1f77b4',
  full_roster: '#2ca02c',
  two_way: '#9467bd',
  future_draft_pick: '#ff7f0e'
}};

function nodeColor(node) {{
  if (node.node_type === 'event') {{
    return eventTypePalette[node.event_type] || '#577590';
  }}
  return nodePalette[node.node_type] || '#6d6875';
}}

function edgeColor(edge) {{
  return assetTypePalette[edge.asset_type] || '#374151';
}}

function fmt(obj) {{
  const filtered = {{}};
  Object.keys(obj).forEach((k) => {{
    const v = obj[k];
    if (v !== null && v !== undefined && v !== '') filtered[k] = v;
  }});
  return JSON.stringify(filtered, null, 2);
}}

function overlaps(edgeStart, edgeEnd, filterStart, filterEnd) {{
  const start = edgeStart || '';
  const end = edgeEnd || '9999-12-31';
  return start <= filterEnd && end >= filterStart;
}}

const allNodes = payload.nodes.map((n) => {{
  const isBoundary = n.node_type === 'state_boundary';
  return {{
    ...n,
    id: n.node_id,
    label: n.label || n.node_id,
    shape: isBoundary ? 'box' : 'dot',
    size: isBoundary ? 26 : 13,
    color: {{
      background: nodeColor(n),
      border: '#1f2937',
      highlight: {{ background: '#e63946', border: '#111827' }}
    }},
    font: {{ color: '#111827', size: 12, face: 'IBM Plex Sans' }},
    title: fmt(n)
  }};
}});

const allEdges = payload.edges.map((e) => {{
  const edgeLabel = e.player_name || e.asset_key || e.asset_id;
  return {{
    ...e,
    id: e.edge_id,
    from: e.source_node_id,
    to: e.target_node_id,
    label: edgeLabel,
    arrows: 'to',
    color: {{ color: edgeColor(e), opacity: 0.85 }},
    width: e.asset_type === 'future_draft_pick' ? 1.5 : 2.5,
    font: {{ size: 10, align: 'middle', strokeWidth: 2, strokeColor: '#fffaf2' }},
    smooth: {{ enabled: true, type: 'curvedCW', roundness: 0.08 }},
    title: fmt(e)
  }};
}});

const nodesById = Object.fromEntries(allNodes.map((n) => [n.id, n]));
const edgesById = Object.fromEntries(allEdges.map((e) => [e.id, e]));

const nodeDS = new vis.DataSet([]);
const edgeDS = new vis.DataSet([]);

const network = new vis.Network(
  document.getElementById('graph'),
  {{ nodes: nodeDS, edges: edgeDS }},
  {{
    interaction: {{ hover: true, tooltipDelay: 120 }},
    physics: {{
      stabilization: false,
      barnesHut: {{ gravitationalConstant: -22000, springLength: 170, springConstant: 0.018 }}
    }},
    edges: {{ selectionWidth: 3 }},
    nodes: {{ borderWidth: 1.2 }}
  }}
);

const startInput = document.getElementById('start-date');
const endInput = document.getElementById('end-date');
const eventSelect = document.getElementById('event-types');
const detail = document.getElementById('detail');
const statNodes = document.getElementById('stat-nodes');
const statEdges = document.getElementById('stat-edges');

startInput.value = payload.defaultStart || '';
endInput.value = payload.defaultEnd || '';

payload.eventTypes.forEach((eventType) => {{
  const option = document.createElement('option');
  option.value = eventType;
  option.textContent = eventType;
  option.selected = true;
  eventSelect.appendChild(option);
}});

function selectedEventTypes() {{
  return new Set(Array.from(eventSelect.selectedOptions).map((opt) => opt.value));
}}

function applyFilters() {{
  const start = startInput.value || payload.defaultStart;
  const end = endInput.value || payload.defaultEnd;
  const eventTypes = selectedEventTypes();

  const visibleNodeIds = new Set();
  const visibleNodes = allNodes.filter((node) => {{
    if (node.node_type !== 'event') {{
      visibleNodeIds.add(node.id);
      return true;
    }}
    const inDateRange = node.event_date >= start && node.event_date <= end;
    const inType = eventTypes.size === 0 || eventTypes.has(node.event_type);
    const keep = inDateRange && inType;
    if (keep) visibleNodeIds.add(node.id);
    return keep;
  }});

  const visibleEdges = allEdges.filter((edge) => (
    overlaps(edge.start_date, edge.end_date, start, end)
      && visibleNodeIds.has(edge.source_node_id)
      && visibleNodeIds.has(edge.target_node_id)
  ));

  nodeDS.clear();
  edgeDS.clear();
  nodeDS.add(visibleNodes);
  edgeDS.add(visibleEdges);

  statNodes.textContent = `Visible nodes: ${{visibleNodes.length}}`;
  statEdges.textContent = `Visible edges: ${{visibleEdges.length}}`;

  network.fit({{ animation: {{ duration: 350, easingFunction: 'easeInOutCubic' }} }});
}}

document.getElementById('apply').addEventListener('click', applyFilters);
document.getElementById('reset').addEventListener('click', () => {{
  startInput.value = payload.defaultStart || '';
  endInput.value = payload.defaultEnd || '';
  Array.from(eventSelect.options).forEach((opt) => {{ opt.selected = true; }});
  applyFilters();
}});

network.on('click', (params) => {{
  if (params.nodes.length > 0) {{
    const node = nodesById[params.nodes[0]];
    detail.textContent = fmt(node || {{}});
    return;
  }}
  if (params.edges.length > 0) {{
    const edge = edgesById[params.edges[0]];
    detail.textContent = fmt(edge || {{}});
    return;
  }}
  detail.textContent = 'Click a node or edge to inspect attributes.';
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
    resolved_nodes_path = nodes_path or (DEFAULT_EXPORTS_DIR / "nodes.csv")
    resolved_edges_path = edges_path or (DEFAULT_EXPORTS_DIR / "edges.csv")

    nodes = read_csv(resolved_nodes_path)
    edges = read_csv(resolved_edges_path)
    event_types = _sorted_event_types(nodes)
    default_start, default_end = _event_date_bounds(nodes)

    html = _html_template(
        nodes=nodes,
        edges=edges,
        default_start=default_start,
        default_end=default_end,
        event_types=event_types,
    )

    ensure_dir(output_path.parent)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate interactive HTML visualization from exported CSV graph files")
    parser.add_argument("--nodes", type=Path, default=DEFAULT_EXPORTS_DIR / "nodes.csv")
    parser.add_argument("--edges", type=Path, default=DEFAULT_EXPORTS_DIR / "edges.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_EXPORTS_DIR / "graph_view.html")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    write_visualization_html(output_path=args.output, nodes_path=args.nodes, edges_path=args.edges)
    print(f"Wrote visualization HTML: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
