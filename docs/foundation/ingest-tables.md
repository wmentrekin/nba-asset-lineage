# Ingest Tables

These are the first permanent ingest tables for the reset-era rebuild.

They intentionally stop before canonical grouping and transition truth.

Current schema:

- `foundation.source_record`
- `foundation.source_event`
- `foundation.player`
- `foundation.pick`
- `foundation.asset`

These tables are fed by the normalization workbench shapes and are meant to be
the durable landing zone before canonical event grouping is introduced.

## Design Intent

`source_record`
- raw fetched payload and fetch metadata

`source_event`
- normalized, inclusive Memphis event rows

`player`
- stable player reference identities

`pick`
- stable pick reference identities with normalized text semantics

`asset`
- graph continuity identities that point to either a player or a pick

## Current Limitation

These tables do not yet include:

- canonical grouped events
- event-to-asset transitions
- roster snapshots
- full real-source coverage

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

It should emit:

- `events`
- `player_assets`
- `pick_assets`
- `transitions`
- `roster_snapshots`

For this pass:

- `roster_snapshots` is intentionally empty
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
  - NBA stats player / roster references

What still comes next:

- broader real-source loading coverage
- roster snapshot tables
