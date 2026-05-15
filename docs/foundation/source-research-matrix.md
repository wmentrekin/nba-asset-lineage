# Source Research Matrix

This document evaluates source areas against the reset-era foundation defined in
[`data-foundation.md`](./data-foundation.md).

It does not freeze final vendor selection yet. Its purpose is to narrow the
source strategy to a realistic stack for the permanent rebuild.

## Reset-Era Source-Role Contract

The active B1 contract is schema-free. It defines recognized provider roles and
corroboration vocabulary for downstream audit/reporting code, but it does not
add a source-corroboration table or migration.

Planned or recognized providers are not loaded evidence. A provider role counts
as `loaded_evidence`, `supports_event`, or `conflicts_event` only after matching
rows exist in the current ingest path:

`canonical_event -> canonical_event_member -> source_event -> source_record`

### First-Pass Fact Types

| fact type | minimum required roles | target roles | purpose |
| --- | --- | --- | --- |
| `transaction_chronology` | `chronology_spine` | `structured_player_movement`, `official_confirmation` | Prove that an event date/type exists in a transaction chronology. |
| `player_movement` | `chronology_spine` | `structured_player_movement`, `official_confirmation` | Corroborate player movement details with structured NBA movement data or official text. |
| `roster_snapshot` | `roster_snapshot` | `identity_roster` | Support roster-state assertions with explicit roster snapshot evidence. |
| `pick_right_detail` | `secondary_pick_detail` | `official_confirmation` | Support pick obligations, protections, swaps, and via chains. |
| `player_identity` | `identity_roster` | `structured_player_movement` | Join player/team references to durable identity data. |

Deferred fact types for this pass:

- `contract_terms_beyond_base_status`
- `daily_roster_state`
- `conditional_pick_branch_resolution`
- `narrative/editorial events`

### Provider Roles

| provider role | recognized source systems | first-pass state |
| --- | --- | --- |
| `chronology_spine` | `basketball_reference` | Loaded BRef rows are baseline chronology evidence, but BRef-only canonical events still need visible corroboration status. |
| `structured_player_movement` | `nba_player_movement`, `nba_official` | Recognized provider until matching source records/events are loaded. |
| `official_confirmation` | `nba_official`, `team_official` | Recognized provider until official league/team release evidence is loaded. |
| `roster_snapshot` | `nba_stats`, `basketball_reference` | Recognized provider until explicit roster snapshot source records are loaded. |
| `secondary_pick_detail` | `realgm`, `curated_fixture` | Recognized provider for pick-detail support; loaded evidence must still be event-linked or clearly documented. |
| `identity_roster` | `nba_stats`, `basketball_reference` | Recognized provider for identity and season roster reference. |

Allowed evidence states:

- `recognized_provider`
- `loaded_evidence`
- `supports_event`
- `conflicts_event`
- `missing_required_evidence`

Allowed corroboration statuses:

- `meets_minimum`
- `bref_only`
- `missing_required_evidence`
- `recognized_provider_not_loaded`
- `out_of_scope`

Allowed conflict statuses:

- `not_evaluated`
- `no_conflict_detected`
- `conflict_suspected`

The first report contract is canonical-event-level and should expose:

- `canonical_event_id`
- `event_date`
- `event_type`
- `fact_type`
- `loaded_source_systems`
- `loaded_source_types`
- `recognized_provider_roles`
- `required_source_roles`
- `missing_roles`
- `evidence_states`
- `corroboration_status`
- `conflict_status`
- `notes`

## Source Areas

The foundation currently needs five source areas:

1. transaction chronology
2. player reference
3. pick reference / obligation interpretation
4. roster state
5. manual curation fallback

## Evaluation Criteria

Each source area is judged by:

- historical depth
- structuredness
- Memphis relevance
- pick / trade detail quality
- repeatability
- likely ingestion complexity

## Candidate Matrix

### 1. Transaction chronology

#### Candidate: Basketball-Reference team transaction pages

Strengths:

- strong season-by-season historical coverage
- Memphis team-scoped pages are easy to reason about
- includes many day-to-day signings, waivers, and trades
- useful human-readable labels for normalized source events

Weaknesses:

- not an official structured API
- page scraping would be required
- same-day grouped event semantics would still need canonical logic

Fit:

- strong candidate for the baseline chronology spine

#### Candidate: NBA.com trade tracker / team news / official releases

Strengths:

- official confirmation layer for completed trades
- helpful for validating grouped transaction membership and official framing
- especially useful for major trades and draft-night moves

Weaknesses:

- not a complete all-event historical transaction ledger by itself
- more article-oriented than ingestion-oriented
- weaker for everyday roster churn than team transaction pages

Fit:

- good verification / enrichment layer, not likely the sole chronology source

#### Candidate: Spotrac transactions / contracts pages

Strengths:

- strong coverage of contract actions, two-way moves, and signing details
- often captures contract context the graph may later want
- team-specific transaction views exist

Weaknesses:

- not official league source
- scraping likely required
- trade grouping semantics still need normalization

Fit:

- strong enrichment layer, especially for signings, conversions, and two-way
  details

### 2. Player reference

#### Candidate: NBA stats endpoints via `nba_api`

Strengths:

- structured player identity surface
- `CommonAllPlayers` supports historical season-scoped player identity lookup
- `CommonPlayerInfo` and related endpoints support normalized player metadata
- already familiar to the repo

Weaknesses:

- depends on stats.nba.com behavior and access patterns
- not a complete transaction layer

Fit:

- strongest player-reference candidate

### 3. Pick reference / obligation interpretation

#### Candidate: Spotrac trade / contract / pick-related transaction text

Strengths:

- frequently includes readable protection and swap descriptions
- helpful for normalization into `protection_text` / `swap_text`

Weaknesses:

- text-oriented rather than canonical pick-asset structured data
- may still require manual interpretation

Fit:

- useful enrichment source, not likely sufficient alone

#### Candidate: Basketball-Reference transaction text

Strengths:

- often includes the incoming/outgoing pick description in trade text
- historically broad

Weaknesses:

- protection/swap semantics are often too text-heavy for direct trust
- likely insufficient as the only pick obligation source

Fit:

- useful baseline text feed for pick event extraction

#### Candidate: manual curation

Strengths:

- can resolve ambiguous historical pick protections and swaps accurately
- can encode Memphis-perspective interpretation once and keep it stable

Weaknesses:

- labor-intensive
- should be exception handling, not the whole system

Fit:

- necessary fallback for pick obligations in v1

### 4. Roster state

#### Candidate: NBA stats `CommonTeamRoster`

Strengths:

- structured team roster by season
- stable enough for player reference and roster snapshots
- official stats-backed shape

Weaknesses:

- seasonal roster endpoint is not by itself a complete day-by-day state log
- may need event-derived reconstruction for exact post-event snapshots

Fit:

- best baseline roster-state reference

#### Candidate: event-derived roster reconstruction

Strengths:

- can generate post-event current-state snapshots from canonical transitions
- aligns directly with the lineage truth model

Weaknesses:

- only trustworthy if transaction completeness is high
- needs validation against an external roster reference

Fit:

- should likely be the primary snapshot builder, with roster endpoints as
  validation/reference

## Recommended Source Strategy

The most realistic current stack looks like this:

### A. Chronology spine

Use Basketball-Reference team transaction pages as the broad transaction
chronology spine.

Why:

- it appears to have the best practical season-by-season Memphis transaction
  coverage for a broad event table
- it naturally supports the inclusive `source_event` layer

### B. Official verification layer

Use NBA.com trade tracker and official team / league transaction announcements
as a verification layer for grouped trades and major moves.

Why:

- official sources are useful for validating the grouped canonical event model
- they help distinguish reported chatter from official completed events

### C. Player reference layer

Use NBA stats endpoints through `nba_api` for player identity and metadata.

Why:

- strongest structured player-reference option in the current likely stack
- already aligned with the repo's Python environment

### D. Roster-state reference layer

Use NBA stats `CommonTeamRoster` as the reference roster layer.

Why:

- structured
- season-scoped
- useful for validating player identity and season roster membership

### E. Secondary pick-detail layer

Use RealGM selectively for pick obligations, protections, swaps, and via-chain
support.

Why:

- it provides useful secondary pick-right descriptions, especially where BRef
  transaction text is too thin for durable pick continuity

### F. Curated fixture fallback

Use checked-in curated fixtures only for explicitly documented gaps.

Why:

- the current foundation only needs normalized text in v1
- trying to fully automate pick obligations from messy historical prose too
  early would likely slow the rebuild

## Recommended Ownership By Table

### `player`

Primary source:

- NBA stats / `nba_api`

### `pick`

Primary source:

- transaction text extraction

Enrichment / fallback:

- RealGM text
- checked-in curated fixtures

### `source_record`

Primary source:

- all fetched source payloads

### `source_event`

Primary source:

- Basketball-Reference transaction chronology

Verification / enrichment:

- NBA.com official trade tracker and official release pages
- NBA.com player movement feed where available
- RealGM for secondary pick-detail support

### `canonical_event`

Primary source:

- internal grouping logic over `source_event`

Verification:

- official NBA.com trade releases when available

### `event_asset_transition`

Primary source:

- internal canonical lineage builder

Dependencies:

- `source_event`
- `asset`
- roster-state validation logic

### `roster_snapshot`

Primary source:

- event-derived reconstruction

Validation / reference:

- NBA stats `CommonTeamRoster`

## Current Recommendation

The active first-pass source-role stack is:

1. Basketball-Reference for the broad transaction chronology
2. NBA.com player movement for structured player-movement corroboration
3. NBA.com and team official releases for authoritative confirmation when
   discoverable
4. RealGM for secondary pick-right detail
5. NBA stats / `nba_api` for player identity and season roster reference

Checked-in curated fixtures may document gaps, but they are not a substitute for
loaded source evidence unless the downstream report marks that state explicitly.

## Open Questions Before Final Lock

These still need direct research / testing:

1. How far back and how cleanly can Basketball-Reference Memphis transaction
   pages be scraped and normalized across seasons?
2. How much of the required roster-state validation can be derived from events
   versus needing more direct roster sources?
3. How complete is NBA.com player movement coverage around July-September 2016?
4. How many Memphis pick obligations over the target scope will require curated
   fixture documentation after RealGM and official sources are checked?
