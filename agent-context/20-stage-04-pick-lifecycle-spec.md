# Stage 04 Pick Lifecycle Spec

## Purpose

Define how Stage 4 models the continuous Memphis pick lifecycle.

## Stage Objective

At the end of Stage 4, the system should be able to represent one continuous
pick asset across:

- future owned pick
- resolved draft slot
- drafted player stage

## In Scope

- `canonical.pick_asset`
- pick-stage state transitions
- pick provenance
- protection metadata storage
- resolved-slot data

## Out Of Scope

- full protection simulation
- full compound event asset flow
- presentation-layer rendering

## Core Modeling Decision

The pick remains one continuous asset through all stages.

There are not separate canonical assets for:

- future pick
- resolved slot
- drafted player outcome

Those are state transitions of the same underlying Memphis asset.

Reference contract:

- the graph-visible continuity ID is `canonical.asset.asset_id`
- the subtype record is `canonical.pick_asset`
- drafted-player state should add linkage to `player_id` without changing the
  graph-visible continuity ID

## Pick Asset Requirements

Each pick asset should support:

- stable asset identity
- origin team
- draft year
- round
- protection metadata
- current stage

Recommended fields:

- `pick_asset_id`
- `origin_team_code`
- `draft_year`
- `draft_round`
- `protection_summary`
- `protection_payload`
- `drafted_player_id`
- `current_pick_stage`
- `created_at`
- `updated_at`

Stage 4 must also create one `canonical.asset` row per pick continuity object
with:

- `asset_kind = pick_continuity`
- `pick_asset_id` populated

## Pick Stages

Recommended stage values:

- `future_pick`
- `resolved_pick`
- `drafted_player`
- `conveyed_away`

## Stage Transition Rules

### Rule 1: Ownership Creates Future Pick Presence

If Memphis owns a pick, it should exist as a future pick asset.

### Rule 2: Draft Order Resolution Updates Stage

Once the slot is known, the same pick asset moves into `resolved_pick`.

### Rule 3: Draft Selection Updates Stage

On draft night, the same asset moves into `drafted_player`.

### Rule 4: Traded Pick Remains Same Asset Until It Leaves Memphis

If a pick is traded away, the Memphis lineage for that asset ends at the
relevant trade event.

## Resolved Pick Requirements

When in resolved-pick stage, the asset should support:

- overall pick number
- lottery or order context
- effective date of resolution

This can be stored either:

- in a specialized `pick_resolution` table
- or in generic asset-state payloads

Stage 4 should pick one approach and keep it deterministic.

## Drafted Player Stage

The drafted-player stage is still the same underlying pick asset, but now its
state reflects the player outcome.

This stage should support:

- drafted player identity linkage
- draft event linkage
- transition date

This allows the later presentation layer to render a pick line that becomes a
player line.

Implementation reference:

- use the worked example in `26-canonical-identity-and-reference-contract.md`
  as the authoritative continuity model for
  `future pick -> resolved slot -> drafted player -> later trade`

## Protection Metadata

Stage 4 should store protection details as structured metadata, but not simulate
all future conditional outcomes.

Examples:

- top-4 protected
- second-round if not conveyed
- swap rights language

The goal is to preserve the information, not solve every edge case yet.

## Provenance Requirements

Every important pick-stage fact should trace back to:

- source records
- normalized claims
- overrides if used

Examples:

- pick origin
- protection metadata
- resolved slot number
- drafted player linkage

Typed provenance roles should include at minimum:

- `pick_identity_support`
- `pick_resolution_support`
- `drafted_player_linkage_support`

## Minimal Validation

Stage 4 should validate:

- a pick cannot become resolved before it exists
- a pick cannot become drafted_player before the draft event
- a conveyed-away pick cannot continue as a Memphis-owned pick afterward
- pick stage transitions are date-consistent

## Test Scenarios

Minimum useful tests:

- Memphis-owned future first-round pick
- acquired future pick from another team
- lottery/order resolution producing overall pick number
- draft selection moving pick to drafted-player stage
- draft-night traded pick exiting Memphis at trade event

## Deliverable Checklist

Stage 4 is complete when:

- pick assets persist across future/resolved/drafted stages
- resolved slot data is stored
- drafted-player transition is represented
- provenance and protection metadata are preserved

## Next Dependency

Stage 5 should connect both player and pick assets into the shared event-asset
flow model.
