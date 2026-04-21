# Stage 05 Event-Asset Flow Spec

## Purpose

Define how Stage 5 builds the lineage core by connecting canonical assets to
canonical events.

## Stage Objective

At the end of Stage 5, the system should be able to express:

- which assets flow into an event
- which assets flow out of an event
- how compound trades work from the Memphis perspective
- how draft events connect pick continuity to player continuity

## In Scope

- `canonical.event_asset_flow`
- event-to-asset directionality
- player and pick participation in a common flow model
- lineage integrity checks

## Out Of Scope

- final frontend rendering
- editorial overlays

## Core Flow Model

Each flow row represents a directed relationship between:

- one canonical event
- one canonical asset

Required semantics:

- `in` means the asset flows into the event
- `out` means the asset flows out of the event

Reference contract:

- `event_asset_flow.asset_id` must reference `canonical.asset.asset_id`
- it must not reference `player_id`, `player_tenure_id`, or `pick_asset_id`
  directly

## Required Fields

Recommended fields:

- `event_asset_flow_id`
- `event_id`
- `asset_id`
- `flow_direction`
- `flow_role`
- `flow_order`
- `effective_date`
- `created_at`

## Flow Roles

Useful initial flow roles:

- `incoming_player`
- `outgoing_player`
- `incoming_pick`
- `outgoing_pick`
- `pick_consumed`
- `player_emerges`

## Compound Trade Rules

### Rule 1: One Trade, One Event

A trade is one canonical event.

### Rule 2: Memphis Outgoing Assets Flow In

Assets Memphis gives up flow `in` to the trade event.

### Rule 3: Memphis Incoming Assets Flow Out

Assets Memphis receives flow `out` from the trade event.

### Rule 4: Multiple Assets Per Side Are Allowed

Trades may involve many players and picks on either side.

### Rule 5: Memphis-Side Accuracy Matters Most

Stage 5 does not need full league-side decomposition for multi-team deals if
Memphis in/out lineage remains correct.

## Draft Flow Rules

### Rule 1: Pick Stage Flows Into Draft Event

The pick asset flows `in` to the draft event.

### Rule 2: Same Asset Emerges In Drafted-Player Stage

The same asset flows `out` with drafted-player semantics.

### Rule 3: Draft-Night Trades Use Trade Rules

If a draft-night trade occurs, represent it with the same trade flow semantics
as any other compound trade.

## Signing And Exit Flow Rules

### Signing

- player asset flows `out` from a signing event into Memphis presence

### Waiver / Buyout / Exit

- player asset flows `in` to the exit event as it leaves Memphis presence

## Flow Ordering

`flow_order` is useful when:

- multiple outgoing assets need stable display ordering
- multiple incoming assets need deterministic ordering

It should be deterministic even if not heavily used in v1.

## Interaction With Tenure And Pick State

Stage 5 should not replace:

- `player_tenure`
- `asset_state`
- `pick_stage`

Instead, it should link them through events.

In practice:

- flow rows express transformation participation
- tenure and state tables express time-bounded conditions

Stage dependency:

- this stage should not be treated as implementation-ready unless
  `agent-context/contracts/identity-and-reference.md` is accepted as locked

## Minimal Validation

Stage 5 should validate:

- every flow references a valid event and asset
- trade events with Memphis activity have at least one flow row
- no asset appears to both enter and exit Memphis incorrectly in the same event
  without explicit design support
- draft events connect pick continuity correctly

## Test Scenarios

Minimum useful tests:

- simple signing
- waiver / buyout exit
- one-for-one trade
- multi-asset trade
- pick used in draft
- draft-night traded pick

## Deliverable Checklist

Stage 5 is complete when:

- event-asset flow rows exist
- compound trade semantics are working
- player and pick continuity can be traversed through events
- integrity checks catch basic flow inconsistencies

## Next Dependency

Stage 6 should derive frontend-ready nodes, edges, and lanes from this lineage
structure.
