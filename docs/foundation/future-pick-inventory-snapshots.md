# Future Pick Inventory Snapshots

This pass focuses on filling `foundation.roster_snapshot_pick`.

The goal is not to answer "which pick was involved in this one transaction?"
The goal is to answer, at each checkpoint date:

- which future pick assets Memphis controlled
- which own picks Memphis no longer controlled
- which swaps or protections affected those rights
- which source or curated assertion supports that state

## Current Gap

`foundation.roster_snapshot_pick` is empty.

That means roster snapshots can currently show players, but they cannot show the
future pick inventory that should live below the player slots in the base graph.

The current `foundation.pick` rows are transaction-derived pick mentions and
draft-slot resolution rows. They are useful, but they are not yet a complete
inventory ledger because they mostly represent picks explicitly mentioned in
loaded transactions rather than all future picks Memphis owned by default.

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

## Proposed Ledger Shape

This should start as a checked fixture or workbench output before any live DB
write path.

Suggested fixture path:

`configs/data/memphis_future_pick_obligations_2016_2026.json`

Suggested row shape:

```json
{
  "obligation_id": "mem-pick-obligation:2027:1:lal-to-mem",
  "effective_date": "2026-02-03",
  "team_code": "MEM",
  "draft_year": 2027,
  "round_number": 1,
  "original_team": "LAL",
  "direction": "incoming",
  "holding_status": "owned",
  "obligation_type": "conditional_pick",
  "protection_text": "protected top 4; conveys as 2027 second if protected",
  "swap_text": null,
  "source_event_id": "canonical-or-source-event-id-if-known",
  "source_urls": [
    "https://basketball.realgm.com/nba/teams/Memphis-Grizzlies/14/draft-picks"
  ],
  "confidence": "curated",
  "notes": "Validated against current future-picks pages; exact historical source row still needs source_event link."
}
```

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
6. Keep conditional fallback rows when a protected pick may become a second-round
   pick or may extinguish.
7. Mark uncertain rows but do not silently drop them.

## Database Fit

The existing table can support a first pass:

- `roster_snapshot_pick.snapshot_id`
- `roster_snapshot_pick.pick_id`
- `roster_snapshot_pick.asset_id`
- `roster_snapshot_pick.holding_status`
- `roster_snapshot_pick.display_order`

However, a durable version likely needs a source/provenance table before we
trust it long term.

Recommended next table before live writes:

`foundation.pick_inventory_obligation`

Suggested purpose:

- stores the dated obligation ledger
- supports `source_record_id` or source URL provenance
- preserves confidence and notes
- keeps projection logic repeatable

`roster_snapshot_pick` should be a derived table from this ledger, not the only
place where obligation truth is stored.

## Implementation Recommendation

Next implementation pass should be:

1. Add a local fixture with a small curated sample of Memphis obligations that
   are already visible in current sources and existing source events.
2. Add Python models for pick-obligation fixture rows.
3. Add a read-only preview command that:
   - loads current `roster_snapshot` rows
   - builds default own-pick baselines
   - applies fixture obligations
   - outputs projected `roster_snapshot_pick` counts and sample rows
   - validates the latest snapshot against current-source expectations
4. Add tests around projection rules before adding a DB write command.
5. Only after preview output is coherent, add guarded write loading into
   `roster_snapshot_pick`.

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
