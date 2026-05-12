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
- `roster_snapshots` populated from checkpoint snapshot tables when available
- roster-state validation remains separate from the base export
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
  - Basketball-Reference season roster pages
  - Basketball-Reference draft pages
  - NBA stats player and roster references
- identity-alias scaffolding for source-name drift such as nickname/full-name
  variants
- roster checkpoint tables for:
  - post draft
  - season opening
  - post trade deadline
  - season closing
- draft selection and contextual draft lottery tables
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
  - emits `roster_snapshots` when checkpoint data has been built
- a roster-baseline layer for filling in current-team player presence even when
  the transaction baseline alone would miss long-tenured incumbents
- checked-in inspection commands for:
  - overall schema state
  - active `foundation` table row counts
  - read-only foundation coverage and gap audit
  - read-only draft-selection to pick-asset resolution preview

## Current Caveats

- Basketball-Reference transaction, roster, and draft sources are HTML pages, so
  these loaders are scrapers.
- NBA stats reference loading uses JSON endpoints.
- Basketball-Reference season roster pages are useful roster references, but they
  are not date-exact opening/deadline/closing roster snapshots.
- Two-way versus standard contract status is represented in the schema, but it
  still needs a stronger source than the current BRef roster loader.
- Draft selections are collected as context, but pick-to-player resolution is not
  fully linked to pick assets yet.
- Draft lottery results are contextual for now and are not required for the base
  graph export.
- `audit-foundation-data` is the current command for turning these caveats into
  live database evidence.
- `preview-draft-pick-resolution` is the current read-only command for checking
  whether loaded draft selections can be linked to existing pick assets before
  adding any write-path resolver.

## Related Paths

- [`src/foundation/`](../../src/foundation)
- [`src/redesign_cli.py`](../../src/redesign_cli.py)
- [`docs/frontend/`](../frontend)
- [`full-span-load-notes.md`](full-span-load-notes.md)
