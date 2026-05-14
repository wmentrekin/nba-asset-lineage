# Ingest Tables

These are the first permanent ingest tables for the reset-era rebuild.

They intentionally stop before canonical grouping and transition truth.

Current schema:

- `foundation.source_record`
- `foundation.source_event`
- `foundation.player`
- `foundation.player_alias`
- `foundation.pick`
- `foundation.asset`
- `foundation.pick_inventory_obligation`
- `foundation.roster_snapshot`
- `foundation.roster_snapshot_player`
- `foundation.roster_snapshot_pick`
- `foundation.draft_selection`
- `foundation.draft_pick_resolution`
- `foundation.draft_lottery_result`

These tables are fed by the normalization workbench shapes and are meant to be
the durable landing zone before canonical event grouping is introduced.

## Design Intent

`source_record`
- raw fetched payload and fetch metadata

`source_event`
- normalized, inclusive Memphis event rows

`player`
- stable player reference identities

`player_alias`
- source and manual aliases that resolve alternate names to one player identity

`pick`
- stable pick reference identities with normalized text semantics. A nullable
  `pick_overall` column exists for slot-backed draft picks when exact overall
  pick identity is known.

`asset`
- graph continuity identities that point to either a player or a pick

`pick_inventory_obligation`
- source-backed, dated pick-rights ledger. This is the durable truth source for
  Memphis-perspective future pick inventory and separates perspective, owner,
  and original-team semantics. It stores direction, holding status, obligation
  type, confidence, source URLs/labels, retrieval timestamp, optional source and
  canonical event links, condition/protection/swap text, notes, and loadability.

`roster_snapshot`
- current-state roster checkpoints for post draft, season opening, post
  deadline, and season closing views

`roster_snapshot_player`
- player membership in a checkpoint, including two-way versus standard status
  fields. The roster snapshot builder writes standard defaults; the bounded
  two-way status loader resets covered rows to standard and applies curated
  high-confidence intervals after snapshot rebuilds.

`roster_snapshot_pick`
- derived pick membership in a checkpoint. Rows should be projected from
  `pick_inventory_obligation` plus own-pick baseline rules, not authored as the
  source of obligation truth. Projection rows preserve `holding_status`,
  `source_obligation_id`, `confidence`, and `notes` so the graph can distinguish
  owned, owed-out, swap-right, encumbered, and conditional picks.

`draft_selection`
- draft results for Memphis selections

`draft_pick_resolution`
- provenance-backed links from Memphis draft selections to slot-based pick assets

`draft_lottery_result`
- contextual lottery result metadata. `team_code` remains the perspective or
  team-scope code for compatibility, while nullable `owner_team_code` and
  `original_team_code` carry explicit ownership/origin semantics for rows such
  as Memphis-origin picks owned by another team.

## Current Limitation

These tables do not yet include:

- canonical grouped events
- event-to-asset transitions
- full real-source coverage
- official roster-source validation for reconstructed checkpoint snapshots
- complete historical two-way contract sourcing
- complete historical future-pick obligation replay coverage beyond the current
  source-backed seed ledger

## First Canonical Pass

The next layer is intentionally narrow and now directly feeds the first
graph-ready export.

The first canonical build should assume:

- non-trade `source_event` rows remain one-to-one `canonical_event` rows
- same-day `trade` `source_event` rows group into one `canonical_event`
- `canonical_event_member` records every contributing `source_event`
- `event_asset_transition` is derived directly from member
  `normalized_payload` inbound and outbound assets
- no narrative, editorial, or chapter-specific fields belong in this layer

## First Export Boundary

The first graph-ready export should read across:

- `foundation.player`
- `foundation.pick`
- `foundation.asset`
- `foundation.canonical_event`
- `foundation.event_asset_transition`
- `foundation.draft_pick_resolution`

It should emit:

- `events`
- `player_assets`
- `pick_assets`
- `transitions`
- `roster_snapshots`

For this pass:

- `roster_snapshots` is emitted when checkpoint rows exist
- `draft_pick_resolution` emits graph-facing `pick_to_player` transitions
- `pick_inventory_obligation` is upstream source truth for future
  `roster_snapshot_pick` projection; projected snapshot rows remain the graph
  boundary for pick inventory state
- `draft_lottery_result` is not consumed by the base graph export
- no roster-state validation is expected
- no frontend layout semantics are part of the export

The repo now includes:

- sample ingest row builders for all five base tables
- a checked-in normalization workbench
- a checked-in derivation pass that can build:
  - `player`
  - `pick`
  - `asset`
  from the current `source_event` baseline
- first live loader commands for:
  - Basketball-Reference transactions
  - Basketball-Reference roster baselines
  - Basketball-Reference draft results
  - NBA stats player / roster references
  - curated draft lottery result preview/load for contextual seed metadata
  - future pick obligation preview/load from
    `configs/data/memphis_future_pick_obligations_2016_2026.json`
  - guarded `roster_snapshot_pick` replacement from the loaded obligation
    ledger
  - two-way status preview and guarded load from
    `configs/data/memphis_two_way_status_2017_2026.json`

What still comes next:

- broader real-source loading coverage
- official roster snapshot validation
- broader two-way status fixture coverage beyond `seed_v1`
- broader historical future pick obligation replay beyond the current seed
  ledger
