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
  - read-only future pick obligation validation
  - guarded future pick obligation load
  - guarded snapshot-pick inventory replacement
- graph-facing `pick_to_player` export rows derived from
  `foundation.draft_pick_resolution`
- a source-backed future pick obligation ledger and guarded projection path for
  `foundation.roster_snapshot_pick`
- a `seed_v1` two-way status fixture for high-confidence Memphis intervals and
  a guarded loader that resets covered snapshot-player rows to standard before
  applying current loadable intervals
- a `seed_v1` draft lottery result fixture for high-confidence
  Memphis-perspective lottery outcomes in 2018, 2019, 2020, 2024, and 2026

## Current Caveats

### Safe refresh boundary

The planned 2026 offseason refresh is blocked until the reviewed safe-refresh
tooling is verified and explicitly approved for a later live pass. The tooling
is documented in [`safe-refresh-tooling/`](safe-refresh-tooling/) and is
code-only at this point: no bundle capture, database snapshot, runner, or
restore has been performed from this branch.

Its operator contract has five distinct operations; do not collapse them into a
single “refresh” action:

1. **Capture** injects a fetcher into `foundation.source_payloads` and stores
   immutable raw-byte bundles below restricted `tmp/<refresh-id>/` storage.
   It is the only layer permitted to perform network I/O. There is no generic
   capture CLI command yet.
2. **Sealed request/plan assembly** materializes fixed source-bundle slots,
   four tracked fixture slots, `refresh-request.json`,
   `refresh-reconciliation.json`, and `refresh-plan.json` in that same leaf.
   These are closed, canonical, digest-linked artifacts. There is deliberately
   no generic CLI for arbitrary JSON, SQL, tables, or plan steps.
3. **Preview/projection** runs
   `preview-refresh-projection --artifact-directory <leaf>`. It validates the
   complete sealed chain before opening one read-only baseline, writes no
   database rows, and writes a single immutable sanitized
   `projection-report.json` in the leaf.
4. **Approval and runner** require a human-created closed
   `refresh_approval_v1` payload. `record-refresh-approval` can validate and
   record that payload, but never invents consent. The runner takes only
   `--artifact-directory <leaf> --execute`, validates every binding before a
   write-capable connection, and supports recovery only at an approved prefix;
   no caller may choose, skip, or reorder steps.
5. **Restore** replays the full 21-table preimage in fixed FK-safe order only
   after separate `action=restore_snapshot` approval and explicit `--execute`.
   It is destructive, is never automatic, and is not authorized by an
   `execute_refresh` approval.

Restricted operational artifacts can contain raw source bodies or full database
preimages. They must stay in the ignored repo-local `tmp/<refresh-id>/` root,
with private `0700` directories and `0600` files. Do not commit, upload, or
attach them to a PR. Retain them only through the live refresh review and any
required recovery window, then remove them using an explicitly reviewed local
cleanup action. Sanitized projection reports may be shared only when they
contain counts, IDs, field names, and digests—not source bodies, credentials,
or full database rows.

Known operational limitations: the advisory lock coordinates the approved
runner only; direct legacy writers are outside that lock. A changed payload,
fixture, code/dependency/environment/dirty-tree fingerprint, schema/database,
or prefix state invalidates approval and requires a fresh projection and human
approval.

Read the complete [safe refresh operator guide](safe-refresh-tooling/README.md)
before any later live pass. This branch has performed no source capture,
database snapshot, runner, or restore operation.

- Basketball-Reference transaction, roster, and draft sources are HTML pages, so
  these loaders are scrapers.
- NBA stats reference loading uses JSON endpoints.
- Roster checkpoint rows are capped, date-aware reconstructions from
  Basketball-Reference season roster pages plus loaded transaction events.
- Two-way versus standard contract status is represented in the schema and now
  has complete source-backed Memphis interval coverage across the in-scope span
  through the checked-in fixture plus guarded loader.
- Draft selections are linked to curated Memphis draft-slot pick assets and now
  export as pick-to-player graph transitions.
- Draft lottery results now export as additive pick context linked by durable
  first-round pick provenance. They still do not become graph events or
  transitions. `team_code` is the Memphis perspective scope, while
  `owner_team_code` and `original_team_code` carry pick semantics.
- Future pick inventory snapshots are built from a dated obligation ledger, not
  from a current-state future-picks page alone. The active ledger now closes the
  reset-era pick-truth contract for realized Memphis-visible replay. Draft
  prior-owner lineage now derives from loaded selection-day truth without live
  override reliance, and the two documented fallback-second cases export as
  bounded conditional-family data while staying out of concrete snapshot
  ownership.
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
  Memphis-perspective rows in one transaction.
  Loaded lottery rows now emit through the additive `draft_lottery_results`
  export surface while staying outside graph-state-changing event/transition
  logic.
- `preview-pick-inventory-obligations` validates the future-pick obligation
  fixture without writing.
- `load-pick-inventory-obligations --dry-run` reports the guarded ledger write
  plan; without `--dry-run`, it upserts source-backed obligation rows, including
  non-projectable conditional fallback rows, while creating concrete pick
  assets only for projectable rows.
- `load-pick-inventory-snapshots --dry-run` reports projected
  `roster_snapshot_pick` rows from the loaded ledger; without `--dry-run`, it
  replaces covered snapshot-pick rows so projection state does not go stale.

## Related Paths

- [`src/foundation/`](../../src/foundation)
- [`src/redesign_cli.py`](../../src/redesign_cli.py)
- [`docs/frontend/`](../frontend)
- [`full-span-load-notes.md`](full-span-load-notes.md)
- [`future-pick-inventory-snapshots.md`](future-pick-inventory-snapshots.md)
