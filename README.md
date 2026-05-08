# nba-asset-lineage

This repository is being rebuilt from scratch around a smaller and more
trustworthy goal:

- one Memphis-only Astro page
- one 10-year asset evolution graph
- transactions as graph nodes
- asset continuity as graph strands
- no narrative, chaptering, or editorial layer in the base product

The repo is intentionally in a reset phase. The previous staged redesign and
frontend prototype were not discarded, but they are no longer the active target
architecture.

## Current Objective

The current build order is:

1. define the minimum graph output we actually need
2. define the source systems required for that output
3. define the durable Supabase storage model
4. ingest and validate the source data
5. group events and build lineage truth
6. export a graph-ready lineage dataset
7. render that dataset in Astro

The important constraint is that schema and frontend work should follow the data
truth, not get ahead of it.

## Active Repo Structure

- [`src/foundation/`](src/foundation)
  - reset-era data models and scaffolding for the smaller lineage system
- [`src/redesign_cli.py`](src/redesign_cli.py)
  - minimal reset-era CLI
- [`src/db_config.py`](src/db_config.py)
  - local `.env` database configuration loader
- [`frontend/`](frontend)
  - Astro shell for the next graph implementation
- [`docs/foundation/`](docs/foundation)
  - reset-era architecture notes
- [`docs/frontend/`](docs/frontend)
  - current frontend reset notes
- [`configs/data/`](configs/data)
  - reserved for active reset-era tracked config/data inputs

## Archived Material

Earlier implementation material is preserved in [`legacy/`](legacy/README.md):

- staged redesign source code
- staged SQL bootstrap files
- old tests tied to the staged implementation
- old frontend reset/readiness docs
- the previous Astro prototype
- earlier config bundles and overrides

That material is available for reference and logic-mining only.

## Temporary Command Surface

The current `mise` tasks are deliberately minimal while the repo is being
redefined:

```bash
mise run setup
mise run db_check
mise run frontend_setup
mise run frontend_dev
mise run frontend_check
mise run frontend_test
mise run frontend_build
```

These are temporary scaffolding commands, not the long-term workflow.

The checked-in Python CLI now also supports reset-era foundation tasks such as:

- DB inspection and reset
- foundation table row-count inspection
- foundation ingest bootstrap
- normalization workbench preview
- sample ingest bundle build
- derived entity preview/load from the live `source_event` baseline
- live Basketball-Reference transaction preview/load
- live NBA stats reference preview/load

The first graph-ready export contract is intentionally narrow:

- it reads from current `foundation.player`, `foundation.pick`,
  `foundation.asset`, `foundation.canonical_event`, and
  `foundation.event_asset_transition` tables
- it can enrich `player_assets` from `foundation.roster_baseline_player`
  when baseline roster data exists
- it emits `events`, `player_assets`, `pick_assets`, `transitions`, and
  `roster_snapshots`
- `roster_snapshots` remains empty for now
- it does not yet include roster-state validation or frontend layout semantics

## Environment

Use local `.env` only.

Database connectivity is currently still expected through the existing Postgres
variables consumed by [`src/db_config.py`](src/db_config.py).

## Working Rule

Until the new source/data model is settled:

- prefer defining smaller contracts over implementing bigger systems
- prefer preserving old work in `legacy/` over deleting potentially useful logic
- do not reintroduce narrative/editorial/frontend complexity into the base graph
- do not freeze new SQL or Supabase schema prematurely
