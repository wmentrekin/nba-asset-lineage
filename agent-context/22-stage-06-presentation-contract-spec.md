# Stage 06 Presentation Contract Spec

## Purpose

Define the derived data contract that the frontend should consume from the
canonical lineage model.

## Stage Objective

At the end of Stage 6, the system should be able to generate deterministic,
frontend-ready timeline structures without requiring the frontend to interpret
lineage semantics itself.

## In Scope

- `presentation.timeline_nodes`
- `presentation.timeline_edges`
- `presentation.asset_lanes`
- exported JSON contract for the frontend

## Out Of Scope

- final visual design
- polished interaction design
- narrative polish

## Core Principle

The frontend should render lineage, not infer lineage.

That means the presentation contract must already express:

- event nodes
- asset line segments
- lane placement
- hover/detail payloads
- ordering and time bounds

## Render-Driving Canonical Facts

Stage 6 should only consume lane decisions from canonical facts that are already
explicitly available. It should not invent new eligibility logic in the
presentation layer.

Required upstream facts:

- player roster lane eligibility intervals
- player two-way eligibility intervals
- pick lane eligibility intervals
- pick-to-player transition semantics
- transition dates between lane groups

## Timeline Nodes

Each node should represent a renderable event or boundary point.

Recommended fields:

- `node_id`
- `event_id`
- `event_date`
- `event_order`
- `node_type`
- `label`
- `payload`

Potential `node_type` values:

- `event`
- `state_boundary`
- `calendar_marker`

## Timeline Edges

Each edge should represent a renderable lineage segment.

Recommended fields:

- `edge_id`
- `asset_id`
- `source_node_id`
- `target_node_id`
- `start_date`
- `end_date`
- `edge_type`
- `lane_group`
- `lane_index`
- `payload`

Potential `edge_type` values:

- `player_line`
- `pick_line`
- `transition_line`

## Asset Lane Assignment

Lane assignment must be deterministic in v1.

Recommended fields:

- `asset_lane_id`
- `asset_id`
- `lane_group`
- `lane_index`
- `effective_start_date`
- `effective_end_date`
- `assignment_method`

Recommended `lane_group` values:

- `main_roster`
- `two_way`
- `future_picks`

Lane assignment inputs must come from canonical state, not frontend inference.

## Payload Expectations

The frontend should have direct access to useful metadata for:

- event hover cards
- asset hover cards
- narrative selection states
- debugging and validation

Examples of payload contents:

- player name
- pick identity metadata
- event type
- event description
- counterparties
- contract metadata when relevant

## Required Contract Guarantees

Stage 6 output should guarantee:

- stable IDs
- explicit date bounds
- explicit same-day order
- explicit lane placement
- no need for frontend-side event clustering
- no need for frontend-side asset continuity inference

## Node/Edge Generation Rules

### Rule 1: Date Order Must Match Canonical Order

The presentation contract cannot reorder events differently from canonical.

### Rule 2: Asset Continuity Must Be Explicit

Player and pick continuity should be represented directly in edge segments.

### Rule 3: Pick To Player Transition Must Be Renderable

The contract must support a line that begins as a pick and continues as a player
without frontend guesswork.

### Rule 4: Memphis Absence Should Not Produce False Continuity

Returning players should appear as separate rendered tenure chapters.

## Export Shape

The first export format can be JSON-first.

Recommended top-level payload groups:

- `nodes`
- `edges`
- `lanes`
- `meta`

Optional:

- `annotations`
- `calendar_markers`
- `games`

## Minimal Validation

Stage 6 should validate:

- every edge connects valid nodes
- lane assignment is deterministic
- overlapping lane usage is controlled or intentional
- node ordering matches canonical ordering
- pick-to-player transitions render as expected in data

## Test Scenarios

Minimum useful tests:

- player tenure line across simple signing
- player leave and return rendering as separate segments
- future pick to resolved pick to drafted-player continuity
- compound trade creating multiple simultaneous lines
- same-day ordered events rendering correctly

## Deliverable Checklist

Stage 6 is complete when:

- presentation tables or derived exports exist
- lane assignment is deterministic
- JSON export can feed a frontend without semantic reinterpretation

## Next Dependency

Stage 7 should layer editorial context on top of this contract without altering
the core lineage semantics.
