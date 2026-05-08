# Foundation Reset

This folder captures the reset-era foundation for the repo.

The current objective is to define the smallest trustworthy lineage system
before reintroducing higher-order concerns like narrative structure, chaptering,
or editorial overlays.

## Base Output

The base output is a graph-ready data model for a Memphis-only, 10-year asset
lineage page:

- transactions as nodes
- player and pick continuity as strands
- roster state used to validate continuity

## Planned Work Areas

1. define the minimum export contract
2. define the source systems needed for each field
3. define a durable ingestion/storage model in Supabase
4. ingest real source data into the `foundation` schema
5. add canonical grouping and transition truth
6. rebuild the frontend from the smaller contract

## Current State

The repo now has:

- a normalization workbench for representative Memphis transaction samples
- a permanent `foundation` ingest schema in Supabase
- fixture-backed sample row builders for:
  - `source_record`
  - `source_event`
  - `player`
  - `pick`
  - `asset`
- first live-source loader scaffolding for:
  - Basketball-Reference transactions
  - NBA stats player and roster references
- checked-in inspection commands for:
  - overall schema state
  - active `foundation` table row counts

## Related Paths

- [`src/foundation/`](../../src/foundation)
- [`src/redesign_cli.py`](../../src/redesign_cli.py)
- [`docs/frontend/`](../frontend)
