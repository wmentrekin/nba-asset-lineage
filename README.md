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
Pick `sort_key` is `[draft_year, round, own_first, original_team]` (`own_first` is 0
for Memphis's own pick, 1 otherwise), so 2027 reads MEM R1, LAL R1, MEM R2. Teams
may trade picks up to 7 drafts out, so the day after each draft in
`curated_events.json`'s `drafts[]`, derive adds a `pick_horizon` node
(`Horizon-<year+7>`) that brings Memphis's own R1 and R2 for that year in from `NEW`.
Player assets and nodes also carry `hidden`: a player is hidden when every Memphis
segment is a 10-day contract and he first arrived by signing (not trade or draft), and a
node is hidden when every movement in it touches a hidden player. It is an export-level
flag only; data, derive, validate and the database are unchanged.

## The rendered graph

`graph.svg` is 2400px wide on a linear calendar, hand-written (no plotting
library), and drawn as a *compacting stack*. Time runs left to right and a row
is a **rank**, not a fixed slot: only Memphis tenure is drawn, so a strand's y
is a step function of x and every rank change is a horizontal-tangent S-curve.
Players `graph.json` marks `hidden` (10-day-only signings) and their nodes are
not drawn at all and never take a row.

It is styled to sit on the Grizzlies page of the owner's personal site: the
project's navy band (`#1b2a5c`) as the canvas, pale blue (`#aebfe8`) strands
and text, the gold accent (`#f6b61c`) for trades and one highlighted lineage,
and the site's red (`#ef6b5e`) for exits. Titles, band captions and years are
set in Newsreader and names and the legend in Instrument Sans (both with
system fallbacks, since an offline SVG cannot load web fonts), in Title Case
with tabular numerals. There are no grid or lane lines, badges or shadows:
bands are separated by space and one faint hairline, and every strand has
round caps like the project artwork.

Three bands stack top to bottom. The **roster** band holds every player on a
standard, 10-day or draft-rights contract, ordered by tenure with the
longest-serving on top — which is why an arrival (signing, trade, draft,
conversion) always lands at the bottom of the stack. The **two-way** band is
the three rows the NBA rules allow, ordered the same way. A strand's own
transaction is drawn at its node; the *knock-on* re-rank a departure causes
(everyone below sliding up) starts a fixed gap (1.5× the S-curve width) past
the node that caused it, whatever else is nearby, so the stack closes within
about two weeks. Each date's holes close in their own shift; when two shifts
overlap, a strand caught by both runs one curve from the first start to the
later finish. The two-way band never draws a fourth row: a same-day two-way
swap closes its hole at the node.

The **picks** band is a column of fixed **per-draft-year blocks** with the
year at the left (and at the right edge for years still held). A year's block
exists from the first day Memphis holds one of its picks — or the day the year
becomes tradeable at its `pick_horizon` node (2033 on 2026-06-25) — until its
last pick is used or traded. Every pick of that year Memphis holds at any
point in the window owns one fixed slot, labelled by round and team ("R1
LAL"), in `sort_key` order (round, then Memphis's own, then original team), so
a traded-in pick fills an empty slot and nothing else moves. When a block
disappears after its draft, every block below shifts up together, once, the
same fixed gap past that draft.

Two things cross bands, and both are drawn as one continuous strand curving up
into the bottom of the roster band at their node: a **two-way conversion**
(the player's tenure clock restarts there) and a **draft selection**, where
the pick strand leaves its slot and continues as the drafted player. Every
strand is the same thickness; contract type is a *shade* of the palette, not a
new hue: standard is full pale blue, 10-day and two-way are progressively
fainter, picks fainter still, and draft rights are a faint gold.

One **lineage is highlighted** in full gold and drawn on top:
`lineage render --highlight <asset_id>` (default `1628991`, Jaren Jackson Jr.;
`--highlight none` turns it off). The lineage is the seed asset plus,
transitively, everything Memphis received in a trade a highlighted asset left
in, plus the player a highlighted pick was used on. The title area names it in
one sentence.

Markers are colored by kind: a trade is a gold dot (it also converges its
departing strands into the dot and fans the arriving ones back out), a signing
or conversion a pale blue dot, a waiver, contract void or expiry a red dot,
and a draft selection a hollow gold ring. The opening-night baseline and
`pick_horizon` nodes get no marker. An asset that leaves Memphis ends in a
filled dot in its strand's own shade (destination is in the `<title>`
tooltip, not drawn as text). A name sits at the left edge of its strand when
it fits and otherwise on the strand's roomiest flat stretch; when it fits
nowhere the strand gets a small numeral keyed to a numbered list at the bottom
of the image, below the legend. Two runs over the same `graph.json` produce
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
| `render` | Draw `graph.svg` from `graph.json` (`--in PATH`, `--out PATH`, `--highlight ASSET_ID\|none`) |
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
  (`-(draft_year * 100 + pick_no)`); once the feed names them, set
  `player_id` in the draft selection to the real id.
- `data/corrections.json` — declarative overrides for feed rows the parser
  can't handle on its own.

`lineage derive --feed-fixture PATH` derives from a saved feed payload without
touching the database, and `--dry-run` prints the derived rows as JSON instead
of loading them. The feed omits training-camp signings but lists the camp cuts, so
`derive` skips any waiver of a player Memphis does not hold at that date (noting each
one) and `validate` reports every skip as a W7 warning; any other kind of move for a
non-held player still fails E1.

The feed never records a contract simply running out. When a player Memphis still holds
next appears in the feed on another team, `derive` ends his Memphis strand with an `expiry`
node (`Expire-Contract-<person id>-<year>`) on the latest June 30 before that row; with no
June 30 in between it uses the other team's date and `validate` reports a W8 warning.
`contract_expirations[]` in `data/curated_events.json` adds expiries by hand and wins over
the automatic rule for the same player and year. `validate` E8 fails any date on which MEM
holds more than three two-way contracts.

## Environment

Locally, set `DATABASE_URL` in a `.env` file. In CI it is a repo secret. This
development sandbox cannot reach NBA hosts, so live fetches only run in
GitHub Actions or on a machine with real network access.

The Lineage Load workflow is `workflow_dispatch`-only (manual trigger from the
Actions tab), and that only works once the workflow file is on the default
branch. On a feature branch, run `mise run load` locally instead.

The previous multi-season implementation lives in git history on `main`
before this reset.
