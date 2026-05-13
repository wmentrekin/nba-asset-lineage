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
  - read-only curated draft-slot resolution preview
  - guarded curated draft-slot resolution load
  - read-only two-way status preview
  - guarded two-way status reset/apply load
  - read-only draft lottery result preview
  - guarded draft lottery result load
- graph-facing `pick_to_player` export rows derived from
  `foundation.draft_pick_resolution`
- a source strategy for future pick inventory snapshots and the next
  obligation-ledger workbench
- a read-only `preview-pick-inventory-snapshots` command for projecting future
  pick inventory rows before any DB write path
- a `seed_v1` two-way status fixture for high-confidence Memphis intervals and
  a guarded loader that resets covered snapshot-player rows to standard before
  applying current loadable intervals
- a `seed_v1` draft lottery result fixture for high-confidence Memphis-owned
  lottery outcomes in 2018, 2019, 2024, and 2026

## Current Caveats

- Basketball-Reference transaction, roster, and draft sources are HTML pages, so
  these loaders are scrapers.
- NBA stats reference loading uses JSON endpoints.
- Roster checkpoint rows are capped, date-aware reconstructions from
  Basketball-Reference season roster pages plus loaded transaction events.
- Two-way versus standard contract status is represented in the schema and can
  be seed-loaded from curated high-confidence intervals, but nonzero two-way
  rows do not prove complete historical two-way coverage.
- Draft selections are linked to curated Memphis draft-slot pick assets and now
  export as pick-to-player graph transitions.
- Draft lottery results are contextual for now and are not required for or
  consumed by the base graph export. The `seed_v1` fixture deliberately excludes
  2020 Boston-from-Memphis because the current table has no separate owner-team
  and original-team fields.
- Future pick inventory snapshots should be built from a dated obligation ledger,
  not from a current-state future-picks page alone.
- `audit-foundation-data` is the current command for turning these caveats into
  live database evidence.
- `preview-draft-pick-resolution` is the current read-only command for checking
  whether loaded draft selections can be linked to existing pick assets before
  adding any write-path resolver.
- `preview-curated-draft-pick-resolution` compares the tracked curated
  Memphis draft-slot fixture against live `draft_selection` rows and reports
  which rows would be safe for a later create/link write path.
- `load-curated-draft-pick-resolution --dry-run` reports the guarded write plan;
  without `--dry-run`, it bootstraps `foundation.draft_pick_resolution`, creates
  slot-based pick assets, links `draft_selection.pick_id`, and records
  provenance only when every fixture row remains safe.
- `preview-two-way-status` reports identity blocks, projected snapshot-player
  updates, and non-matching interval warnings without writing to the database.
- `load-two-way-status --dry-run` reports the same guarded plan; without
  `--dry-run`, it refuses blocking fixture rows, resets covered Memphis
  snapshot-player rows to standard, and applies only current high-confidence
  loadable intervals. Run it after `load-roster-snapshots-from-baselines`.
- `preview-draft-lottery-results` reports loadable rows, blocked rows, source
  metadata validation, and existing `(draft_year, team_code)` DB matches without
  writing.
- `load-draft-lottery-results --dry-run` reports the same guarded plan; without
  `--dry-run`, it refuses blocking fixture rows and conflicting existing
  `(draft_year, team_code)` IDs, then upserts only high-confidence loadable
  Memphis-owned rows in one transaction. Rows with `loadable=false` are never
  written.

## Related Paths

- [`src/foundation/`](../../src/foundation)
- [`src/redesign_cli.py`](../../src/redesign_cli.py)
- [`docs/frontend/`](../frontend)
- [`full-span-load-notes.md`](full-span-load-notes.md)
- [`future-pick-inventory-snapshots.md`](future-pick-inventory-snapshots.md)
