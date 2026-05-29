# Future Pick Inventory Snapshots

This pass focuses on filling `foundation.roster_snapshot_pick`.

The goal is not to answer "which pick was involved in this one transaction?"
The goal is to answer, at each checkpoint date:

- which future pick assets Memphis controlled
- which own picks Memphis no longer controlled
- which swaps or protections affected those rights
- which source or curated assertion supports that state

## Current Status

`foundation.roster_snapshot_pick` is populated from the loaded obligation
ledger. Live verification on 2026-05-14 reported 980 projected snapshot-pick
rows across 40 roster checkpoints.

The current `foundation.pick` rows now include transaction-derived pick
mentions, draft-slot resolution rows, and inventory pick rows projected from the
obligation ledger. The active ledger is now source-backed enough to close the
reset-era pick-truth contract for realized Memphis-visible replay, while still
stopping short of a full hypothetical conditional-branch engine.

## Source Research

### Basketball-Reference team transactions

Repository status:

- already loaded as `foundation.source_record`
- already normalized into `foundation.source_event`
- already feeds canonical event and transition rows

Best use:

- primary dated event spine for historical reconstruction
- first source for when an incoming or outgoing pick obligation entered the
  Memphis timeline

Limitations:

- transaction text is prose, not a normalized pick-obligation table
- current parser sometimes collapses compound pick details into one broad text
  blob
- own future picks that are never traded do not appear as rows, so inventory
  generation needs a default own-pick baseline

### Pro Sports Transactions

Relevant pages:

- NBA Draft Pick Transactions yearly index:
  `https://www.prosportstransactions.com/basketball/DraftTrades/Years/index.htm`
- Memphis future pick status:
  `https://www.prosportstransactions.com/basketball/DraftTrades/Future/Grizzlies.htm`

Best use:

- high-value validation and curation source for pick obligations
- especially useful for conditional swaps, protections, and multi-team routing
- includes dated transaction chains in the visible text

Limitations:

- direct fetch returned HTTP 403 in this environment, so this should not be the
  first automated scraper target
- future-status pages are current-state pages, not historical snapshots
- uncertain/incomplete rows need manual review instead of automated trust

### RealGM future draft picks

Relevant page:

- `https://basketball.realgm.com/nba/teams/Memphis-Grizzlies/14/draft-picks`

Best use:

- current end-state validation
- detailed current incoming/outgoing pick summaries
- useful transaction-date breadcrumbs for curated obligations

Evidence from research:

- RealGM exposes current first- and second-round future pick summaries for
  Memphis and includes detailed incoming/outgoing pick descriptions with trade
  dates in brackets.

Limitations:

- current-state page, not a point-in-time historical source
- should validate the derived current inventory, not directly generate all
  historical checkpoint rows

### Spotrac draft / multi-year pages

Relevant pages:

- `https://www.spotrac.com/nba/memphis-grizzlies/draft`
- `https://www.spotrac.com/nba/memphis-grizzlies/yearly`

Best use:

- secondary current-state validation
- useful for draft-pick outlook and contract-adjacent context

Limitations:

- page is current projection oriented
- page shape is noisier than RealGM for pick-obligation parsing
- not sufficient for historical snapshots by itself

### Fanspo future picks

Relevant page:

- `https://fanspo.com/nba/teams/Grizzlies/15/draft-picks`

Best use:

- quick current-state cross-check
- readable protections/swaps display

Limitations:

- current-state page
- not authoritative enough to be the primary source for historical state

### NBA.com official releases / trade trackers

Relevant examples:

- Grizzlies/Magic Desmond Bane release:
  `https://www.nba.com/grizzlies/news/grizzlies-acquire-kentavious-caldwell-pope-cole-anthony-four-future-first-round-picks-and-one-first-round-pick-swap-from-magic/`
- NBA.com Magic/Grizzlies trade article:
  `https://www.nba.com/news/magic-grizzlies-trade-bane-caldwell-pope`
- NBA.com 2025 trade deadline tracker:
  `https://www.nba.com/news/2025-nba-trade-deadline-buzz`
- NBA.com 2025 offseason trade tracker:
  `https://www.nba.com/news/2025-offseason-trade-tracker`
- NBA.com Cedric Coward draft trade report:
  `https://www.nba.com/news/reports-grizzlies-acquire-rights-to-no-11-pick-cedric-coward-from-blazers/`

Best use:

- official corroboration for major pick-moving trades
- useful for final source notes on curated ledger rows

Limitations:

- not complete enough for every historic pick obligation
- often omits exact protection/swap mechanics

## Recommended Strategy

Build future pick inventory from a dated obligation ledger, then project that
ledger onto snapshot dates.

Do not scrape a current future-picks page and backfill it over the full
timeline.

The ledger should combine:

- default Memphis own-pick baseline
- transaction-derived incoming/outgoing pick obligations from existing
  `source_event` rows
- curated corrections for protections, swaps, and ambiguous compound picks
- current-state validation against RealGM, Spotrac, Fanspo, and Pro Sports
  Transactions
- official NBA.com releases for major trade corroboration when available

Current high-confidence correction:

- the ORL 2028 first acquired in the Desmond Bane trade was sent out in the
  Cedric Coward draft trade, and NBA.com reports Portland received that 2028
  first via Orlando

## Current Ledger Fixture

The checked fixture is now an object-shaped source-backed seed before any live
DB write path.

Fixture path:

`configs/data/memphis_future_pick_obligations_2016_2026.json`

Top-level shape:

```json
{
  "fixture_id": "memphis_future_pick_obligations_2016_2026_seed_v1",
  "team_code": "MEM",
  "description": "Source-backed Memphis future pick obligation fixture...",
  "source_summary": {
    "retrieved_at": "2026-05-14T00:00:00Z"
  },
  "rows": []
}
```

Loadable row shape:

```json
{
  "obligation_id": "mem-pick-obligation:2027:1:lal-to-mem",
  "effective_date": "2026-02-03",
  "perspective_team_code": "MEM",
  "owner_team_code": "MEM",
  "original_team_code": "LAL",
  "draft_year": 2027,
  "round_number": 1,
  "direction": "incoming",
  "holding_status": "owned",
  "obligation_type": "traded_pick",
  "protection_text": "protected top 4; conveys as 2027 second if protected",
  "swap_text": null,
  "condition_text": "Memphis holds the Lakers 2027 first-round pick if it lands 5-30.",
  "source_event_id": "bref:mem:2026:2026-02-03:1:1",
  "source_urls": [
    "https://basketball.realgm.com/nba/teams/Memphis-Grizzlies/14/draft-picks"
  ],
  "source_labels": [
    "RealGM Memphis Grizzlies future draft picks, retrieved 2026-05-14"
  ],
  "retrieved_at": "2026-05-14T00:00:00Z",
  "confidence": "validated",
  "loadable": true,
  "notes": "Source-backed row ready for obligation preview."
}
```

Fixture requirements:

- loadable rows must carry explicit `perspective_team_code`,
  `owner_team_code`, and `original_team_code`
- loadable rows must carry same-length `source_urls` and `source_labels`
- loadable rows must carry `retrieved_at`
- `source_event_id` must reference loaded source events, not canonical event IDs
- bounded fallback rows should use `confidence=uncertain` and `loadable=false`;
  they are durably stored in `foundation.pick_inventory_obligation` but remain
  non-projectable

Recommended enums:

- `direction`: `incoming`, `outgoing`, `own`, `swap_right`, `swap_obligation`
- `holding_status`: `owned`, `owed_out`, `swap_right`, `encumbered`, `conditional`
- `obligation_type`: `own_pick`, `traded_pick`, `swap`, `conditional_fallback`
- `confidence`: `derived`, `curated`, `validated`, `uncertain`

## Snapshot Projection Rules

For each `roster_snapshot` date:

1. Seed all own Memphis future first- and second-round picks that are still
   legally future picks on that snapshot date.
2. Apply every ledger row with `effective_date <= snapshot_date`.
3. Exclude picks from snapshot inventory after their draft date or after a
   resolved `pick_to_player` transition.
4. Keep own picks visible as `owned` unless an outgoing obligation changes them
   to `owed_out` or `encumbered`.
5. Keep swap rights as separate inventory rows when Memphis controls optionality,
   even if the eventual pick identity is unresolved.
6. Persist conditional fallback facts as non-projectable obligation rows when a
   protected first or swap may become a fallback second.
7. Do not project fallback rows into concrete snapshot ownership; expose them
   only through bounded conditional-family export surfaces so mutually exclusive
   primary and fallback assets never appear simultaneously owned.

## Database Fit

The durable source table is now `foundation.pick_inventory_obligation`.
It stores the dated Memphis-perspective obligation ledger with explicit
`perspective_team_code`, `owner_team_code`, `original_team_code`, direction,
holding status, source URLs/labels, retrieval timestamp, confidence, optional
source/canonical event links, condition/protection/swap text, and loadability.

`foundation.roster_snapshot_pick` is a derived projection target. It preserves:

- `snapshot_id`
- `pick_id`
- `asset_id`
- `holding_status`
- `display_order`
- `source_obligation_id`
- `confidence`
- `notes`

The table should be rebuilt from the obligation ledger, not hand-authored as
the source of pick truth.

## Implemented Commands

Read-only projection from the fixture:

```bash
.venv/bin/python -m redesign_cli preview-pick-inventory-snapshots --team-code MEM --max-draft-year 2032
```

Obligation fixture validation:

```bash
.venv/bin/python -m redesign_cli preview-pick-inventory-obligations --team-code MEM
```

Guarded ledger load:

```bash
.venv/bin/python -m redesign_cli load-pick-inventory-obligations --team-code MEM --dry-run
.venv/bin/python -m redesign_cli load-pick-inventory-obligations --team-code MEM
```

Guarded snapshot projection:

```bash
.venv/bin/python -m redesign_cli load-pick-inventory-snapshots --team-code MEM --dry-run --max-draft-year 2032
.venv/bin/python -m redesign_cli load-pick-inventory-snapshots --team-code MEM --max-draft-year 2032
```

Current behavior:

- reads existing `foundation.roster_snapshot` rows
- reads either the local obligation fixture or the loaded obligation ledger,
  depending on the command
- seeds default Memphis own first- and second-round future picks
- applies dated source-backed obligation rows
- writes only after preview/dry-run validation has zero blocked rows
- replaces covered `roster_snapshot_pick` rows to avoid stale projection state

Live verification on 2026-05-28 loaded 26 obligation rows and projected 980
`roster_snapshot_pick` rows across 40 roster checkpoints. The graph export now
emits both backward-compatible `future_pick_asset_ids` and richer `future_picks`
metadata for every projected snapshot pick.

The active fixture now includes bounded historical selection-day replay rows in
addition to the forward-looking obligation ledger. That is enough to support the
current Memphis-visible replay contract used by the graph export and the draft
prior-owner proof surface. It is still not a full hypothetical branch engine.
Non-projectable fallback rows now persist in the obligation ledger without
allowing the loader to project both a primary obligation and its fallback at the
same time. The Lakers 2027 second applies only if the protected Lakers first
does not convey, and the Orlando 2029 second applies only if Orlando's protected
2029 first-round swap right cannot convey. The export emits those two bounded
cases as synthetic conditional-family branch candidates rather than as concrete
pick assets.

## Risks

- Current future-pick pages are not historical snapshots.
- Current source pages may disagree on complex multi-team swap mechanics.
- Basketball-Reference transaction text is not normalized enough to derive every
  pick obligation automatically.
- Compound swaps can represent optionality rather than a single concrete pick.
- Own-pick baselines require careful draft-year windows; a pick should disappear
  after the draft or after conversion to a selected player.
- `roster_snapshot_pick` alone is too thin to preserve source confidence and
  should remain a projection target, not the source of truth.
