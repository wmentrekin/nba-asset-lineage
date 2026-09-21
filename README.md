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
`graph.json` and `render` draws `graph.svg` from it. In `graph.json`, each
player asset carries a `tenure_start` (and, on a two-way conversion or a
drafted rookie's signing, `tenure_tier_changes`) and each pick asset carries
a `sort_key`, so the renderer can order strands without recomputing tenure.

## The rendered graph

`graph.svg` is 1600px wide, hand-written (no plotting library), and drawn as a
*compacting stack*. Time runs left to right and a row is a **rank**, not a fixed
slot: only Memphis tenure is drawn, and at every transaction date the assets
Memphis currently holds are re-ranked, so a strand's y is a step function of x
and every rank change is a short cubic S-curve just after the transaction that
caused it.

Three bands stack top to bottom. The **roster** band holds every player on a
standard, 10-day or draft-rights contract, ordered by tenure with the
longest-serving on top — which is why an arrival (signing, trade, draft,
conversion) always lands at the bottom of the stack, and why everyone below a
departing player slides up one row when he leaves. The **two-way** band is the
three rows the NBA rules allow, ordered the same way. The **picks** band is
compact — only picks Memphis currently owns, ordered by round, then draft year,
then original team, with a half-row gap between draft years, so a pick acquired
in a trade is inserted at its sorted position rather than appended.

Two things cross bands, and both are drawn as one continuous strand curving up
into the bottom of the roster band while its color changes: a **two-way
conversion** (the player's tenure clock restarts there) and a **draft
selection**, where the pick strand leaves its row and continues as the drafted
player. Every strand is the same thickness; color carries the contract type
(standard, two-way, 10-day, draft rights, and a fifth muted color for pick
strands). Each transaction gets a marker colored by its kind (trade, a signing
family, a waiver family, or a draft selection); a trade additionally converges
its departing strands into that marker and diverges the arriving ones back out
to their new rows. An asset that leaves Memphis ends in a plain end-cap marker
(destination is in the `<title>` tooltip, not drawn as text); the opening-night
baseline and 10-day `expiry` nodes are plain end-caps rather than markers. A
name sits at the left edge of its strand when it fits and otherwise on the
strand's roomiest flat stretch; when it fits nowhere the strand gets a small
numbered marker keyed to a numbered legend block at the bottom of the image,
below the color legend. Two runs over the same `graph.json` produce
byte-identical SVG.

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
- `data/curated_events.json` — curated truth the feed can't supply: trade
  `picks_in`/`picks_out` (the feed marks pick movement only as an
  unlabelled "draft consideration" leg, so pick truth is curated rather
  than parsed), `draft_selections` (a pick strand ends and a player strand
  begins, `contract_type=draft_rights`, until a later signing re-signs it
  standard), and standalone `events` such as a contract void. A drafted
  player with no NBA person id yet (unsigned, so the feed has never named
  them) gets a deterministic synthetic negative id
  (`-(draft_year * 100 + pick_no)`), replaced automatically once a real
  signing resolves the same slot.
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
