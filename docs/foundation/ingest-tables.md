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

The repo now includes:

- sample ingest row builders for all five base tables
- a checked-in normalization workbench
- first live loader commands for:
  - Basketball-Reference transactions
  - NBA stats player / roster references

What still comes next:

- broader real-source loading coverage
- canonical grouping tables
- transition truth tables
- roster snapshot tables
