# nba-asset-lineage

This repository is being redesigned into a public-facing Memphis Grizzlies asset
lineage and storytelling system.

The long-term goal is not the current checked-in pipeline. The target system is
a time-indexed model of franchise evolution that can drive a high-quality,
interactive editorial visualization.

## Status

The current codebase is not representative of the intended final architecture.

What exists today is a legacy prototype:

- a Grizzlies-focused Python/Postgres medallion pipeline
- heuristic source ingestion
- normalized lineage tables
- graph exports and a simple visualization

That implementation is useful as:

- reference material
- a source of historical data already captured
- proof that deterministic lineage exports are feasible

It should not be treated as the final product design.

## Future Direction

The redesign is centered on:

- Memphis-only franchise scope
- player-centric asset lineage
- continuous pick lifecycle modeling
- compound transaction events
- explicit evidence and override layers
- frontend-ready timeline lineage data
- editorial overlays for games, eras, and annotations

## Current Repo Contents

Today’s repo still contains the legacy implementation:

- `src/pipeline/`
  - Bronze/Silver/Gold pipeline logic
- `src/claims_live_ingest.py`
  - current live-source ingestion prototype
- `sql/`
  - legacy Bronze/Silver bootstrap scripts
- `exports/`
  - generated graph artifacts from the legacy model

Expect these to be replaced over time by a new architecture organized around:

- evidence
- canonical lineage
- presentation outputs
- editorial overlays

## Legacy Pipeline

The current legacy pipeline models:

- `bronze`
  - raw ingestion tables
- `silver`
  - normalized lineage tables
- `gold`
  - export artifacts in `exports/`

This is still useful for reference, but it is not the planned final system.

## Setup

Use local `.env` only (gitignored). Current legacy code expects:

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

## Running The Legacy Prototype

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

## Legacy SQL Bootstrap

The current destructive reset script for the legacy Bronze/Silver model is:

- `sql/0001_bootstrap_bronze_silver.sql`

Run:

```bash
mise run db_bootstrap
```

Clear data only:

```bash
mise run db_clear_data
```

## Near-Term Plan

The next implementation work is expected to focus on:

1. new evidence-layer schema and ingestion
2. canonical event timeline construction
3. player tenure modeling
4. pick lifecycle modeling
5. presentation-layer exports for the new timeline visualization

Until that replacement path exists, assume:

- the legacy pipeline is operational but transitional
- the redesign architecture is still being defined internally
