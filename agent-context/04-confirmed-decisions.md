# Confirmed Decisions

This document records redesign decisions that are already agreed and should be
treated as constraints for future planning docs and implementation work.

## Product Direction

- The project is a public-facing storytelling product.
- The end result should support data journalism and editorial presentation, not
  just technical graph inspection.
- The first public release target is a polished standalone experience.
- The first public release should include scrollytelling or chaptering, not only
  exploratory interaction.

## Scope

- Scope is Memphis Grizzlies only.
- There is no requirement to generalize the first implementation to other
  franchises.

## Redesign Approach

- The project can replace the current implementation aggressively.
- Existing code and database contents are reference material and potentially
  reusable data inputs, but not architectural constraints.

## Canonical Modeling Decisions

### Player Asset

- The player is the canonical asset.
- Contract details are not separate canonical assets.
- Contract details are attributes that may change after events such as signings,
  extensions, waivers, or other transaction outcomes.
- A player should only appear in the Memphis lineage graph during Memphis roster
  tenure.
- If a player leaves Memphis and later returns, the graph should show distinct
  Memphis tenure chapters separated by absence.
- It is acceptable for the data model to preserve a broader persistent player
  identity underneath those Memphis-visible intervals.
- The recommended modeling split is:
  - persistent `player_identity`
  - graph-visible `player_tenure` intervals for Memphis presence

### Trades

- A trade is one compound transaction event.
- Multiple outgoing assets flow into the event.
- Multiple incoming assets flow out of the event.

### Draft Pick Complexity

- Draft pick protections and conveyance conditions should be captured as
  structured metadata in v1.
- Full protection/conveyance simulation can be deferred until later.
- All picks owned by Memphis should be represented, including Memphis-origin
  picks and picks acquired from other teams.
- The intended pick lifecycle is:
  - future owned pick
  - resolved draft slot
  - drafted player
- This pick lifecycle should remain one continuous asset through each stage,
  with state transitions rather than separate canonical assets.
- Draft-night trades should be modeled using the same compound trade semantics as
  other trades.

## Temporal Semantics

- Date precision is the key temporal unit.
- The final visualization should be organized around days on the x-axis.
- The system should support daily overlays such as games, key league calendar
  days, and narrative notes.
- If multiple events share a date and exact ordering is ambiguous, use:
  - manual curation when needed
  - source order as fallback

## Scope Boundaries For v1

- Sign-and-trades and multi-team trades should be handled in a Memphis-simplified
  way for v1, as long as Memphis-side in/out asset flow is accurate.
- Buyouts can behave like waivers for lineage purposes.
- If buyout metadata is available, preserve it, but salary-cap modeling is not a
  current priority.
- If available, buyout metadata should remain distinguishable from standard
  waiver metadata.
- Waived-and-stretched and non-guaranteed contract decisions are in scope for
  the first implementation.

## Immediate Planning Implication

The next design bottleneck is the canonical domain model, especially:

- player tenure and state semantics
- pick-to-player transformation semantics
- event ordering semantics
- evidence and override model

## Evidence And Curation

- The redesigned system should explicitly preserve:
  - raw source claims
  - manual curator overrides
- Initial evidence sources should include Spotrac and `nba_api`.
- Manual editorial data entry is expected eventually for annotations and
  corrections.

## Visualization And Layout

- Roster lane assignment should start with a deterministic algorithm.
- Manual layout overrides can be added later if needed.
- The frontend implementation is still open technically.
- It must work within an Astro website.
