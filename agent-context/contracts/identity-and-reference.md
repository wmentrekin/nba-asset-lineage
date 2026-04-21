# Canonical Identity And Reference Contract

## Purpose

Lock the identity and reference semantics that earlier planning docs described
but did not fully resolve.

This document exists to answer one implementation-critical question:

What object does each important ID represent, and what should downstream tables
reference?

## Status

This is a contract doc, not an exploratory draft.

Stage 3 through Stage 6 should be treated as dependent on this contract.

## Identity Layers

The redesigned system should use three distinct identity layers:

1. real-world identity
2. Memphis-visible continuity identity
3. rendered segment identity

Those layers should not be conflated.

## Real-World Identity

### `player_id`

Represents the stable real-world player identity.

Meaning:

- Ja Morant as a person
- independent of whether he is currently on Memphis
- independent of how many Memphis tenures he has

Primary home:

- `canonical.player_identity`

Should be referenced by:

- `canonical.player_tenure.player_id`
- player-related provenance rows
- drafted-player linkage from the pick lifecycle

Should not be used directly as the graph-visible lineage identity.

## Memphis-Visible Continuity Identity

### `graph_asset_id`

Represents the Memphis-visible continuity object used by:

- event flow
- presentation continuity
- lineage traversal

This is the critical identity that was previously under-specified.

Recommended rule:

- every graph-visible continuity object gets one `graph_asset_id`
- `graph_asset_id` is the object referenced by `event_asset_flow.asset_id`
- `graph_asset_id` is also the continuity identity referenced by presentation
  outputs

Primary home:

- `canonical.asset`

Recommended `asset_kind` values:

- `player_tenure`
- `pick_continuity`

This means `canonical.asset` is required for v1, not optional.

## Player Graph Identity

### `player_tenure_id`

Represents a Memphis-visible chapter of player presence.

Meaning:

- one continuous Memphis tenure
- starts when the player enters Memphis presence
- ends when the player exits Memphis presence

Primary home:

- `canonical.player_tenure`

Reference rule:

- every `player_tenure` must map to exactly one `graph_asset_id`
- that `graph_asset_id` should have `asset_kind = player_tenure`

Implication:

- if a player leaves and later returns, that is a new `player_tenure_id` and a
  new `graph_asset_id`
- the stable `player_id` remains the same across both tenures

## Pick Graph Identity

### `pick_continuity_id`

Represents one continuous Memphis-owned pick lifecycle.

Meaning:

- future owned pick
- resolved pick slot
- drafted-player stage

This remains one continuity object through those stages.

Primary home:

- `canonical.pick_asset`

Reference rule:

- every `pick_asset` must map to exactly one `graph_asset_id`
- that `graph_asset_id` should have `asset_kind = pick_continuity`

## Draft Transition Rule

The draft does not create a new graph-visible asset identity.

Instead:

- the same `graph_asset_id` continues across
  `future_pick -> resolved_pick -> drafted_player`

But the drafted-player stage must also link to a real-world `player_id`.

That means after draft selection:

- continuity identity remains the same `graph_asset_id`
- drafted-player identity references `player_id`

This is intentionally asymmetric with returning-player cases.

Why:

- the product requires a pick line that becomes a player line
- a returning player should not show false continuity through absence

## Rendered Segment Identity

### `presentation_edge_id`

Represents one rendered segment in the frontend contract.

Meaning:

- a display segment derived from one `graph_asset_id`
- bounded by dates and nodes

Primary home:

- `presentation.timeline_edges`

Reference rule:

- many rendered segments may belong to one `graph_asset_id`
- rendered segments are not canonical continuity identities

## Required Reference Targets

### `canonical.event_asset_flow.asset_id`

Must reference:

- `canonical.asset.asset_id`

This is the graph-visible continuity object, not the real-world `player_id`.

### `presentation.timeline_edges.asset_id`

Must reference:

- `canonical.asset.asset_id`

The frontend should render continuity using the graph asset identity.

### `presentation.timeline_edges.player_id`

Optional but recommended as payload metadata when the current stage refers to a
known player identity.

### `canonical.asset.player_tenure_id`

Present when:

- `asset_kind = player_tenure`

### `canonical.asset.pick_asset_id`

Present when:

- `asset_kind = pick_continuity`

## Required `canonical.asset` Shape

The schema draft left this open. It should now be treated as locked for v1.

Required fields:

- `asset_id`
- `asset_kind`
- `player_tenure_id`
- `pick_asset_id`
- `asset_label`
- `created_at`
- `updated_at`

Invariants:

- exactly one of `player_tenure_id` or `pick_asset_id` is populated
- `asset_kind` must match the populated subtype reference

## Identity Example

### Example: Future Pick To Drafted Player To Later Trade

Objects:

- `pick_asset_id = pick_mem_2023_1st`
- `graph_asset_id = asset_pick_mem_2023_1st`

Stages:

1. future pick
   - `graph_asset_id = asset_pick_mem_2023_1st`
   - no `player_id` yet
2. resolved slot
   - same `graph_asset_id`
   - still no `player_id`
3. drafted player stage
   - same `graph_asset_id`
   - now linked to `player_id = player_gg_jackson`
4. later trade away
   - same `graph_asset_id` flows into the trade event

This preserves visual continuity from pick line to player line.

### Example: Player Leaves And Returns

Objects:

- `player_id = player_tyus_jones`
- first tenure: `player_tenure_id = tenure_tyus_1`
- first graph asset: `asset_id = asset_tyus_1`
- second tenure after return: `player_tenure_id = tenure_tyus_2`
- second graph asset: `asset_id = asset_tyus_2`

This preserves stable real-world identity without false Memphis continuity.

## Consequences For Downstream Stages

### Stage 3

Must create:

- `player_identity`
- `player_tenure`
- corresponding `canonical.asset` rows for each tenure

### Stage 4

Must create:

- `pick_asset`
- corresponding `canonical.asset` row for each pick continuity object

### Stage 5

Must treat `event_asset_flow.asset_id` as a foreign key to `canonical.asset`
only.

### Stage 6

Must derive timeline continuity from `canonical.asset.asset_id`, not from
`player_id` or subtype IDs directly.

## Recommendation

This contract should be treated as required before implementation of Stage 3
through Stage 6.
