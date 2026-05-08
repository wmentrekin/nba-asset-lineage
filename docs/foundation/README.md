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
- export sections for `events`, `player_assets`, `pick_assets`, `transitions`,
  and `roster_snapshots`
- `player_assets` may carry roster-baseline metadata like `baseline_order` and
  `years_experience` to support slot ordering in the frontend
- `roster_snapshots` present but empty for the first pass
- no roster-state validation yet
- no frontend layout semantics yet

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
- a checked-in derivation path from `foundation.source_event` into:
  - `foundation.player`
  - `foundation.pick`
  - `foundation.asset`
- a documented first-pass canonical contract for:
  - `canonical_event`
  - `canonical_event_member`
  - `event_asset_transition`
- a first graph-ready export contract defined around current foundation tables:
  - reads from `foundation.player`
  - reads from `foundation.pick`
  - reads from `foundation.asset`
  - reads from `foundation.canonical_event`
  - reads from `foundation.event_asset_transition`
  - enriches `player_assets` from `foundation.roster_baseline_player` when
    baseline data exists
  - emits empty `roster_snapshots` until roster-state truth is added
- a roster-baseline layer for filling in current-team player presence even when
  the transaction baseline alone would miss long-tenured incumbents
- checked-in inspection commands for:
  - overall schema state
  - active `foundation` table row counts

## Related Paths

- [`src/foundation/`](../../src/foundation)
- [`src/redesign_cli.py`](../../src/redesign_cli.py)
- [`docs/frontend/`](../frontend)
