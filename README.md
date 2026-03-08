# nba-asset-lineage

Franchise-wide Grizzlies medallion pipeline (`bronze -> silver -> gold`) with deterministic IDs and time-indexed lineage.

## Scope

- Franchise: `grizzlies` (Vancouver + Memphis eras)
- Start date: `1995-06-23`
- End date: rolling (`configs/lineage_scope.yaml`)

## Current Architecture

- `bronze` (raw ingestion tables)
  - `bronze.ingest_runs`
  - `bronze.raw_events`
  - `bronze.raw_assets`
  - `bronze.raw_event_asset_links`
- `silver` (normalized lineage)
  - `silver.events`
  - `silver.assets`
  - `silver.event_asset_lineage`
  - `silver.franchise_team_eras`
- `gold` (export artifacts in `exports/`)
  - `nodes.csv`
  - `edges.csv`
  - `graph.graphml`
  - `events.json`
  - `assets.json`
  - `event_asset_lineage.json`
  - `graph.json`

## Setup

Use local `.env` only (gitignored). Required:

- `NBA_ASSET_DB_HOST`
- `NBA_ASSET_DB_PORT`
- `NBA_ASSET_DB_NAME`
- `NBA_ASSET_DB_USER`
- `NBA_ASSET_DB_PASSWORD`
- `NBA_ASSET_DB_SSLMODE`

Install dependencies:

```bash
mise run setup
```

## Run Pipeline

Full pipeline:

```bash
mise run pipeline
```

Full pipeline with live Bronze adapters:

```bash
mise run pipeline_live
```

Stage-by-stage:

```bash
mise run bronze_live
mise run silver
mise run gold
mise run visualize
```

Dry-run examples:

```bash
mise run bronze_live_dry_run
mise run silver_dry_run
```

## SQL Bootstrap

`sql/0001_bootstrap_bronze_silver.sql` is the canonical destructive reset script for Bronze/Silver.

Run:

```bash
mise run db_bootstrap
```
