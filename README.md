# nba-asset-lineage

## What this is

A Memphis Grizzlies asset-lineage graph. Scoped to the 2025-26 season only:
opening night through today. Transactions are nodes; players and
Memphis-owned future draft picks are strands running between them.

## How it works

A raw NBA player-movement JSON feed is fetched and stored verbatim in a
`lineage` schema in Supabase (5 tables: `source_record`, `player`, `pick`,
`transaction`, `asset_movement`). A deterministic `derive` step turns the raw
payloads plus curated data files into transaction and asset-movement rows.
`validate` checks the result for graph invariants, then `export` writes
`graph.json` and `render` draws `graph.svg` from it.

## The rendered graph

`graph.svg` is 1600px wide, hand-written (no plotting library), and drawn as
slot lanes with node hubs. Time runs left to right. A lane is a *roster slot*,
not an asset: only Memphis tenure is drawn, so when an asset leaves the team its
lane frees and the next asset arriving at that transaction takes it over —
players in a top band, Memphis-owned picks in a band below. Every transaction
that starts or ends a Memphis tenure is a hub: a marker on the transaction's
date with one curve per departing asset flowing into it and one per arriving
asset flowing out, so a trade reads as convergence then divergence. Bar
thickness is the contract type (standard, two-way, 10-day); an asset that leaves
Memphis ends in an arrow capped with its destination (`UTA`, `FA`, `USED`); the
opening-night baseline and 10-day `expiry` nodes are plain end-caps rather than
hubs. Two runs over the same `graph.json` produce byte-identical SVG.

## Commands

| `mise run` task | What it does |
| --- | --- |
| `setup` | `uv sync` the project dependencies |
| `check_db` | Confirm the app can connect to `DATABASE_URL` |
| `migrate` | Apply the `lineage` schema |
| `fetch` | Pull the raw player-movement feed and store it (`--payload-file PATH` to read a saved payload instead of the network, `--save-to PATH` to also write the raw bytes to disk) |
| `derive` | Rebuild transaction/asset rows from raw payloads + data files (`--feed-fixture PATH`, `--dry-run`) |
| `validate` | Check the derived data against graph invariants (`--feed-fixture PATH`, `--strict`) |
| `export` | Write `graph.json` (`--feed-fixture PATH`, `--out PATH`) |
| `render` | Draw `graph.svg` from `graph.json` (`--in PATH`, `--out PATH`) |
| `load` | Run fetch, derive, validate, export, render in sequence (`--feed-fixture PATH`) |
| `test` | Run the offline pytest suite |

## Data files

- `data/opening_snapshot_2025_26.json` — curated opening-night roster plus
  every Memphis-owned future draft pick, as of 2025-26 opening night.
- `data/pick_events.json` — curated pick movements per trade and draft
  selections. The feed marks pick movement only as an unlabelled "draft
  consideration" leg, so pick truth is curated rather than parsed.
- `data/corrections.json` — declarative overrides for feed rows the parser
  can't handle on its own.

`lineage derive --feed-fixture PATH` derives from a saved feed payload without
touching the database, and `--dry-run` prints the derived rows as JSON instead
of loading them.

## Environment

Locally, set `DATABASE_URL` in a `.env` file. In CI it is a repo secret. This
development sandbox cannot reach NBA hosts, so live fetches only run in
GitHub Actions or on a machine with real network access.

The Lineage Load workflow is `workflow_dispatch`-only (manual trigger from the
Actions tab), and that only works once the workflow file is on the default
branch. On a feature branch, run `mise run load` locally instead.

The previous multi-season implementation lives in git history on `main`
before this reset.
