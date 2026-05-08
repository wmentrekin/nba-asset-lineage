# Data Foundation

This document freezes the first reset-era foundation for the Memphis asset
lineage rebuild.

It defines:

1. the core objects
2. which source areas supply their fields
3. which fields are required in v1
4. the ingest flow from source records to canonical lineage truth

It does **not** yet choose the final external source vendors. That comes after
the semantic contract is stable.

## Scope

This foundation is for the minimum base output only:

- Memphis-only
- 10-year asset evolution graph
- transactions as nodes
- asset continuity as strands
- no chaptering
- no editorial overlays
- no narrative-specific schema

## Core Model

The data model is split into four conceptual layers:

1. source intake
2. canonical lineage
3. reference entities
4. frontend export

The frontend export is derived later. The durable truth lives in the first
three layers.

## Object Definitions

### `player`

Represents a real-world player identity used for display and reference.

This is not the graph strand itself. The strand is represented by `asset`.

Proposed fields:

- `player_id`
  - stable internal player identity
- `display_name`
  - normalized display name for UI and labels
- `nba_player_ref`
  - optional external source key
- `birth_date`
  - optional
- `position_text`
  - optional

### `pick`

Represents a real-world draft pick definition.

This is not the graph strand itself. The strand is represented by `asset`.

Proposed fields:

- `pick_id`
  - stable internal pick identity
- `draft_year`
- `round_number`
- `original_team`
- `protection_text`
  - normalized text summary
- `swap_text`
  - normalized text summary
- `resolution_status`
  - e.g. `future`, `conveyed`, `used`, `expired`, `swapped`

### `asset`

Represents a graph-visible continuity identity.

This is the object that persists across time in the lineage graph.

For players, the asset points at one player identity.
For picks, the asset points at one pick identity.

Proposed fields:

- `asset_id`
  - stable graph continuity id
- `asset_kind`
  - `player` or `pick`
- `player_id`
  - nullable, required when `asset_kind = player`
- `pick_id`
  - nullable, required when `asset_kind = pick`
- `start_canonical_event_id`
  - nullable for pre-scope continuity
- `end_canonical_event_id`
  - nullable while continuity remains active

### `source_record`

Represents one fetched raw source payload plus fetch metadata.

This is provenance infrastructure, not graph truth.

Proposed fields:

- `source_record_id`
- `source_system`
- `source_type`
- `source_locator`
  - URL, endpoint key, or other source handle
- `fetched_at`
- `raw_payload`

### `source_event`

Represents one normalized event row extracted from one or more source records.

This is the inclusive event layer and may be broader than the final graph event
set.

Proposed fields:

- `source_event_id`
- `source_record_id`
- `event_date`
- `event_type`
  - inclusive set:
    - `trade`
    - `draft`
    - `waiver`
    - `signing`
    - `re_signing`
    - `extension`
    - `conversion`
    - `release`
- `label`
- `team_scope`
  - should be Memphis-scoped in this repo
- `source_group_hint`
  - optional grouping hint for same-day compounds
- `normalized_payload`

### `canonical_event`

Represents one Memphis lineage event used by the graph truth model.

Many `source_event` rows may map into one `canonical_event`.

Proposed fields:

- `canonical_event_id`
- `event_date`
- `event_type`
  - narrower graph-facing set:
    - `trade`
    - `draft`
    - `signing`
    - `waiver`
- `label`
- `sequence_on_date`
- `is_grouped_event`
- `notes`

### `canonical_event_member`

Represents the membership mapping from inclusive source events to grouped
canonical events.

Proposed fields:

- `canonical_event_id`
- `source_event_id`

### `event_asset_transition`

Represents how one asset changed at one canonical event.

This is the most important lineage table in the system.

Proposed fields:

- `transition_id`
- `canonical_event_id`
- `asset_id`
- `transition_type`
  - e.g. `acquired`, `departed`, `retained`, `pick_to_player`
- `direction`
  - `in`, `out`, `internal`, or similar normalized set
- `from_state`
- `to_state`
- `display_text`
  - optional normalized text for diagnostics/debugging

### `roster_snapshot`

Represents Memphis-held current state after an event or at a checkpoint.

This is current-state only. It does not need to retain assets already gone.

Proposed fields:

- `roster_snapshot_id`
- `as_of_date`
- `canonical_event_id`
  - nullable for non-event checkpoints

Recommended child rows:

- `roster_snapshot_player_asset`
  - `roster_snapshot_id`
  - `asset_id`
- `roster_snapshot_pick_asset`
  - `roster_snapshot_id`
  - `asset_id`

These should be normalized child tables rather than arrays in the base schema.

## Source Areas

This section maps each object's fields to source areas, not vendors.

### Source areas

1. transaction chronology
2. player reference
3. pick reference / obligation interpretation
4. roster state
5. manual curation

### `player` field sources

- `player_id`
  - internal identity generation from player reference
- `display_name`
  - player reference
- `nba_player_ref`
  - player reference
- `birth_date`
  - player reference
- `position_text`
  - player reference

### `pick` field sources

- `pick_id`
  - internal identity generation from pick reference
- `draft_year`
  - pick reference
- `round_number`
  - pick reference
- `original_team`
  - pick reference
- `protection_text`
  - pick reference and manual curation
- `swap_text`
  - pick reference and manual curation
- `resolution_status`
  - pick reference plus event interpretation

### `asset` field sources

- `asset_id`
  - internal continuity assignment
- `asset_kind`
  - derived from linked entity type
- `player_id`
  - player reference
- `pick_id`
  - pick reference
- `start_canonical_event_id`
  - canonical lineage build
- `end_canonical_event_id`
  - canonical lineage build

### `source_record` field sources

- all fields come directly from fetched source payloads and fetch metadata

### `source_event` field sources

- `source_event_id`
  - internal normalized event identity
- `source_record_id`
  - source intake
- `event_date`
  - transaction chronology
- `event_type`
  - transaction chronology
- `label`
  - transaction chronology
- `team_scope`
  - repo scope plus transaction chronology
- `source_group_hint`
  - transaction chronology plus manual curation
- `normalized_payload`
  - normalized source output

### `canonical_event` field sources

- `canonical_event_id`
  - canonical lineage build
- `event_date`
  - source event grouping
- `event_type`
  - canonical lineage selection rules
- `label`
  - canonical lineage build from grouped source events
- `sequence_on_date`
  - canonical lineage ordering
- `is_grouped_event`
  - canonical lineage grouping result
- `notes`
  - manual curation only when needed

### `canonical_event_member` field sources

- derived from canonical grouping logic and manual curation where needed

### `event_asset_transition` field sources

- `transition_id`
  - canonical lineage build
- `canonical_event_id`
  - canonical lineage build
- `asset_id`
  - asset continuity assignment
- `transition_type`
  - canonical lineage interpretation
- `direction`
  - canonical lineage interpretation
- `from_state`
  - roster state plus event interpretation
- `to_state`
  - roster state plus event interpretation
- `display_text`
  - optional canonical lineage output

### `roster_snapshot` field sources

- `roster_snapshot_id`
  - internal
- `as_of_date`
  - roster state source
- `canonical_event_id`
  - canonical lineage alignment when snapshot is event-driven
- child rows
  - roster state source plus asset matching

## Required Fields In V1

These are the minimum required fields for the first permanent system.

### `player`

Required:

- `player_id`
- `display_name`

Optional in v1:

- `nba_player_ref`
- `birth_date`
- `position_text`

### `pick`

Required:

- `pick_id`
- `draft_year`
- `round_number`
- `original_team`

Optional but desirable in v1:

- `protection_text`
- `swap_text`
- `resolution_status`

### `asset`

Required:

- `asset_id`
- `asset_kind`
- `player_id` or `pick_id`

Optional but desirable in v1:

- `start_canonical_event_id`
- `end_canonical_event_id`

### `source_record`

Required:

- `source_record_id`
- `source_system`
- `source_type`
- `fetched_at`
- `raw_payload`

Optional in v1:

- `source_locator`

### `source_event`

Required:

- `source_event_id`
- `source_record_id`
- `event_date`
- `event_type`
- `label`
- `team_scope`

Optional but desirable in v1:

- `source_group_hint`
- `normalized_payload`

### `canonical_event`

Required:

- `canonical_event_id`
- `event_date`
- `event_type`
- `label`
- `sequence_on_date`

Optional but desirable in v1:

- `is_grouped_event`
- `notes`

### `canonical_event_member`

Required:

- `canonical_event_id`
- `source_event_id`

### `event_asset_transition`

Required:

- `transition_id`
- `canonical_event_id`
- `asset_id`
- `transition_type`
- `direction`

Optional but desirable in v1:

- `from_state`
- `to_state`
- `display_text`

### `roster_snapshot`

Required:

- `roster_snapshot_id`
- `as_of_date`

Strongly recommended in v1:

- normalized child rows for rostered player assets
- normalized child rows for owned pick assets

Optional in v1:

- `canonical_event_id`

## Ingest Flow

The ingest flow should remain simple and staged.

### Step 1: fetch raw source records

Connectors fetch raw source payloads from the selected source systems.

Write:

- `source_record`

No lineage semantics are decided here.

### Step 2: normalize source events

Normalizers transform raw source payloads into the inclusive event layer.

Write:

- `source_event`

This layer stays broader than the graph.

### Step 3: build reference entities

Reference builders normalize player and pick identities.

Write:

- `player`
- `pick`

### Step 4: assign asset continuity

Lineage builders create graph continuity identities for players and picks.

Write:

- `asset`

This is where continuity identity is created.

### Step 5: group source events into canonical events

Canonical grouping logic maps many source events into one graph-facing event.

Write:

- `canonical_event`
- `canonical_event_member`

This is where same-day compound trade grouping belongs.

### Step 6: build asset transitions

For each canonical event, determine the effect on every affected asset.

Write:

- `event_asset_transition`

This is the core lineage output.

### Step 7: build roster snapshots

Build current-state Memphis snapshots after events or at chosen checkpoints.

Write:

- `roster_snapshot`
- `roster_snapshot_player_asset`
- `roster_snapshot_pick_asset`

This is the validation/state layer, not the primary graph layer.

### Step 8: validate lineage truth

Validation should confirm:

- every canonical event is backed by source events
- every transition points at a valid asset
- every asset points at exactly one player or pick identity
- grouped canonical events preserve their member source events
- roster snapshots align with transition results

### Step 9: derive frontend export

Only after lineage truth is stable should we derive:

- graph nodes
- graph strands
- graph labels
- graph render metadata

This export should not become the source of truth.

## Deferred Items

These are explicitly deferred for now:

- chaptering
- editorial overlays
- minimaps
- graph layout semantics in the DB schema
- rich player metadata
- structured protections/swaps beyond normalized text
- final source-vendor selection
