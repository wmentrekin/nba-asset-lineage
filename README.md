# nba-asset-lineage

Deterministic Python pipeline for modeling Memphis Grizzlies asset evolution as a directed multigraph.

## Scope

- Team scope: Memphis-owned assets only (`MEM`)
- Time window: `2022-05-14` through `2026-02-26` (inclusive)
- Asset types: `player`, `full_roster`, `two_way`, `future_draft_pick`
- Event types: `trade`, `draft_pick`, `contract_signing`, `extension`, `re_signing`, `conversion`, `waiver`

## Repository Structure

```
nba-asset-lineage/
├── data/
│   ├── raw/
│   │   ├── manual/
│   │   └── ingested/
│   ├── processed/
│   └── exports/
├── schemas/
├── pipelines/
│   ├── ingest/
│   ├── normalize/
│   ├── build_graph/
│   └── visualize/
├── src/
│   └── nba_asset_lineage/
├── run_pipeline.py
├── mise.toml
├── pyproject.toml
└── README.md
```

## Data Source Policy

Approved sources:

- NBA.com transaction logs
- Basketball-Reference
- Spotrac
- RealGM trade/draft pick trackers

Automated non-API scraping is **not enabled** in this initial implementation. Populate `data/raw/manual/*.csv` using approved, validly licensed source data. This enforces explicit review before any free-data scraping path is added.

## Raw Input Contract

Fill these files in `data/raw/manual/`:

- `initial_assets.csv`
- `events.csv`
- `event_assets.csv`
- `sources.csv`

Column requirements are documented in:

- `schemas/raw_manual_schema.yaml`

## Pipeline Stages

1. `ingest`: validates/copies manual raw files into `data/raw/ingested/`
2. `normalize`: builds deterministic IDs and asset segments in `data/processed/`
3. `build_graph`: emits graph-shaped node/edge tables in `data/processed/`
4. `export`: writes final GraphML and CSV artifacts in `data/exports/`

Each stage is independently runnable and idempotent.

## Run With Mise

```bash
mise run setup
mise run pipeline
```

Stage-by-stage:

```bash
mise run ingest
mise run normalize
mise run build_graph
mise run visualize
```

## Run Without Mise

```bash
python -m pip install -e .
python run_pipeline.py --start-date 2022-05-14 --end-date 2026-02-26 --team-code MEM
```

## Outputs

Mandatory outputs are written to `data/exports/`:

- `memphis_asset_lineage.graphml`
- `nodes.csv`
- `edges.csv`
- `graph_view.html` (interactive visualization)

## Quick Visualization

Generate an interactive HTML graph:

```bash
mise run visualize
```

Then open:

- `data/exports/graph_view.html`

The HTML viewer supports:

- date-range filtering
- event-type filtering
- click-to-inspect node and edge attributes

## Assumptions Implemented

- Date-level cadence only (no timezone or intraday ordering)
- End date is inclusive (`2026-02-26`)
- Voided/rescinded transactions excluded
- Cash/exceptions/overseas rights excluded
- Pick protections/swaps stored as both raw text and structured text fields
- Asset IDs are deterministic and stable across modifications
