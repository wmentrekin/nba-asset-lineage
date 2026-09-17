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

## Commands

| `mise run` task | What it does |
| --- | --- |
| `setup` | `uv sync` the project dependencies |
| `check_db` | Confirm the app can connect to `DATABASE_URL` |
| `migrate` | Apply the `lineage` schema |
| `fetch` | Pull the raw player-movement feed and store it |
| `derive` | Rebuild transaction/asset rows from raw payloads + data files |
| `validate` | Check the derived data against graph invariants |
| `export` | Write `graph.json` |
| `render` | Draw `graph.svg` from `graph.json` |
| `load` | Run fetch, derive, validate, export, render in sequence |
| `test` | Run the offline pytest suite |

## Data files

- `data/opening_snapshot_2025_26.json` — curated opening-night roster plus
  every Memphis-owned future draft pick, as of 2025-26 opening night.
- `data/corrections.json` — declarative overrides for feed rows the parser
  can't handle on its own.

## Environment

Locally, set `DATABASE_URL` in a `.env` file. In CI it is a repo secret. This
development sandbox cannot reach NBA hosts, so live fetches only run in
GitHub Actions or on a machine with real network access.

The previous multi-season implementation lives in git history on `main`
before this reset.
