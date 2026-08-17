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
mise run foundation_test
```

These are temporary scaffolding commands, not the long-term workflow.

## Safe Refresh Tooling

The next live offseason refresh is deliberately blocked behind the reviewed
safe-refresh tooling described in
[`docs/foundation/safe-refresh-tooling/`](docs/foundation/safe-refresh-tooling).
It is designed to make an eventual refresh reproducible, previewable, and
recoverable; this repository has not used it to capture sources or change a
database yet.

The safety boundary is intentionally strict:

- source capture writes raw response bytes only to a restricted local
  `tmp/<refresh-id>/` artifact directory; later normalization, preview, and
  execution must consume the locked bundle and its reviewed SHA-256 digest;
- projection starts from one read-only foundation baseline and produces
  sanitized counts, IDs, changed-field names, blockers, and checksums. It does
  not write a database;
- a human-supplied, closed approval record binds the exact payload, fixture,
  projection, snapshot, code, environment, dirty-tree, schema, database, plan,
  and prefix fingerprints before a future write-capable runner can start;
- the runner is a Python safety seam with a fixed approved step order and
  resumable prefix checks. It is not currently exposed as a general-purpose
  live CLI command;
- restore is destructive and always needs a separate
  `action=restore_snapshot` approval. An `execute_refresh` approval cannot
  authorize it.

The one checked-in operational CLI command is intentionally narrow:

```bash
uv --cache-dir /tmp/uv-cache run python -m redesign_cli record-refresh-approval --help
```

It validates and records a reviewed `refresh_approval_v1` JSON document in an
already-private artifact directory; it cannot manufacture approval metadata or
run a refresh. See the safety-tooling documentation before using even this
command.

The checked-in Python CLI now also supports reset-era foundation tasks such as:

- DB inspection and reset
- foundation table row-count inspection
- read-only foundation data coverage audit
- read-only draft-selection to pick-asset resolution preview
- read-only curated draft-slot resolution preview
- guarded curated draft-slot resolution write path
- guarded future pick obligation and snapshot-pick inventory load paths
- foundation ingest bootstrap
- foundation context bootstrap for aliases, roster snapshots, draft selections,
  and lottery context
- normalization workbench preview
- sample ingest bundle build
- derived entity preview/load from the live `source_event` baseline
- live Basketball-Reference transaction preview/load
- live Basketball-Reference roster and draft preview/load
- live NBA stats reference preview/load
- full-span foundation load orchestration from summer 2016 to present

The first graph-ready export contract is intentionally narrow:

- it reads from current `foundation.player`, `foundation.pick`,
  `foundation.asset`, `foundation.canonical_event`, and
  `foundation.event_asset_transition` tables
- it can enrich `player_assets` from `foundation.roster_baseline_player`
  when baseline roster data exists
- it emits `events`, `player_assets`, `pick_assets`, `transitions`, and
  `roster_snapshots`
- `roster_snapshots` is populated when checkpoint rows have been built
- roster snapshots include `future_pick_asset_ids` plus richer `future_picks`
  metadata when `foundation.roster_snapshot_pick` has been projected
- it does not yet include roster-state validation or frontend layout semantics

Current source mechanics:

- Basketball-Reference transactions, rosters, and drafts are ingested by HTML
  scraping.
- NBA stats player/roster reference data is ingested through JSON endpoints.
- Future pick inventory is loaded from a curated, source-backed fixture into a
  durable obligation ledger, then projected into roster checkpoints.
- Draft lottery is contextual for now and is not required for the base graph; it
  now stores explicit owner/original-team semantics for Memphis-perspective
  rows.
- Two-way versus standard contract status is modeled, but still needs stronger
  source coverage than the current BRef roster loader.

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
