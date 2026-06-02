# Visualization Model

## Purpose

This document defines the reset-era visualization model for the Memphis-only
asset-lineage page.

The key architectural decision is that the frontend should not derive lane
truth, slot behavior, or transaction geometry from raw foundation data at
render time. Instead, the system should produce a derived visualization export
that contains render-ready visual structure.

This model sits between:

- the foundation export and database truth
- the Astro rendering layer

## Status

This is the first locked draft based on interactive requirements review.

It is intended to be used as the input contract for a future implementation
pass that builds:

- a derived visualization export
- precomputed lane and strand logic
- frontend rendering against that export

## Core Decision

Use a derived visualization export.

The frontend should not compute:

- lane assignment
- slot movement
- event staging windows
- pick-family handling
- continuity truth

The frontend should only handle:

- drawing
- responsive scaling
- hover/focus interaction
- animation of already-known state

## Base Goal

The first real page should be a Memphis-only, graph-first, scrollable lineage
visual covering roughly 10 years.

The base output should support:

- transactions as nodes
- player and pick continuity as strands
- fixed player-slot behavior
- readable grouped trade geometry
- compact linear time

It should not yet require:

- editorial narrative
- chapters
- scroll-story overlays
- minimap complexity
- lottery storytelling

## Source Surfaces

The visualization model should be built from foundation truth, with these roles:

- `daily_roster_state`: slot occupancy continuity truth
- `events`: canonical node placement and event semantics
- `transitions`: continuity and event transition truth
- `player_assets`: player identity
- `pick_assets`: pick identity

Supporting but not required to drive the first render:

- `roster_snapshots`
- `draft_prior_owner_lineages`
- `conditional_pick_families`
- `draft_lottery_results`

## Lane Model

### Player Lanes

Player lanes are sacred slots, not asset-owned tracks.

- slots `1-15`: main roster band
- slots `16-18`: two-way band
- slots below `18`: temporary overflow band

Implications:

- long-tenured players should feel visually stable
- players move through slots
- slots persist even as occupants change
- two-way players do not displace the main top-15 visual band
- short-term temporary players should not destabilize the core roster bands

### Pick Lanes

Pick lanes are a separate lower band.

- they are distinct from player lanes
- they may grow dynamically as needed
- they should not reorder or destabilize player-slot continuity

## Slot Allocation Rules

### Initial Ordering

The initial left-edge ordering of players should use team tenure as the primary
ranking factor.

This is the default visual ordering rule, not a permanent editorial rule.
Future manual override capability may be added later for narrative or editorial
purposes.

### Sacred Slot Behavior

Slot ownership is sacred.

This means:

- a player should not jump above another already-occupied player slot
- a player keeps the assigned slot until that slot is vacated

### Vacancy and Reflow

When a player leaves:

- lower occupied slots generally shift up one
- the highest available open eligible slot becomes the insertion point for a
  new arrival in that band

### Band Rules

Standard behavior by band:

- main roster players occupy slots `1-15`
- two-way players occupy slots `16-18`
- temporary short-term players occupy the overflow band below `18`

Temporary overflow is intended for cases like:

- 10-day signings
- hardship signings
- short-lived temporary roster noise

This avoids unnecessary wobble in the core visual hierarchy.

## Time Model

Time should remain strictly linear by day.

The timeline should not use a nonlinear compression model that shrinks empty
time differently from active time.

Instead:

- each day remains a real day
- daily spacing should be visually compact
- readability should come from geometry, not time distortion

Target feel:

- one day takes little horizontal space
- roughly 60 days or more should fit within a single screen width at the base
  scale

## Event Geometry Contract

### Shared Event Rules

All same-day grouped actions should share one node.

This includes:

- grouped trades
- same-day bundled sign/waive transaction clusters
- draft-day grouped outcomes where appropriate

### Outgoing Geometry

Outgoing strands should begin curving before the event.

The lead-in window should be adaptive rather than fixed.

It should:

- be long enough to avoid abrupt right-angle transitions
- shorten automatically when nearby events would cause overlap
- lengthen when the surrounding time is visually quiet

### Incoming Geometry

Incoming strands should settle into their destination slot after the event over
a shorter adaptive window.

They should not appear to teleport instantly into a lane on the event day.

### Waiver Geometry

Waiver strands should terminate at the event.

They should not bend into unrelated lanes or imply continuing continuity after
termination.

### Shared System

Trades, signings, waivers, and draft conversions should use one underlying
geometry system with type-specific styling and event rules layered on top.

## Transaction Node Information Model

### Always Visible

Each node should always expose:

- event-type styling
- date
- compact summary label

### Focus / Hover Detail

Expanded node detail may expose:

- inbound assets
- outbound assets
- protections
- swap details
- waiver text
- supporting notes

### Grouped Trade Summary

Grouped trade nodes should explicitly show:

- `sent`
- `received`

They should not present a neutral undifferentiated participant list.

## Pick Behavior

### Visibility Rule

A pick strand should become eligible to appear when it is:

1. tradeable under league rules
2. relevant to Memphis through ownership, obligation, swap, encumbrance, or
   bounded conditional-family state

The visualization should not show every theoretical future pick automatically.

### Pick Conversion

Pick-to-player conversion should appear as a direct handoff at the draft node.

The draft event is the continuity bridge:

- the pick strand arrives
- the drafted player strand begins there

### Prior-Owner Lineage

Prior-owner lineage should usually be implicit in the strand continuity and
draft event rather than separately annotated in the base view.

### Conditional Pick Families

Conditional pick families are bounded special cases.

They should:

- remain visible in the derived visualization export
- avoid becoming simultaneous concrete pick strands when the branches are
  mutually exclusive
- remain secondary to the main concrete pick continuity model

## Lottery Context

Draft lottery data should remain in the model but should not have a visible role
in the base graph for now.

It should be retained for:

- later annotations
- richer pick storytelling
- future contextual enhancements

## Identity Markers

### Player Markers

Player markers should:

- stay attached to the lane near the left side
- move vertically with the lane when the lane shifts
- show headshot plus player name

### Pick Markers

Pick markers should:

- stay attached to the corresponding pick lane
- use a compact text chip

Collapse behavior may be added later if needed, but it is not part of the
initial model contract.

## Precompute vs Browser Responsibilities

### Precomputed

The derived visualization export should precompute:

- lane assignment
- slot occupancy intervals
- event staging windows
- grouped-event summaries
- strand segment boundaries
- connector intent

### Browser Responsibilities

The browser should compute only:

- exact pixel positions
- viewport scaling
- hover/focus interaction
- animation of already-determined visual state

## Proposed Derived Visualization Export

The exact TypeScript/Python schema is still to be formalized, but the derived
visualization export should conceptually contain:

### Metadata

- franchise
- span start / end
- rendering time model
- slot and band configuration

### Lane Definitions

Each lane should define:

- lane id
- band type
- slot index
- lane order
- lane role (`main_roster`, `two_way`, `temporary_overflow`, `pick`)

### Asset Identity

Each asset used by the visual should define:

- asset id
- asset kind
- display label
- marker metadata
- supporting identity metadata needed by rendering

### Occupancy Intervals

Each asset should have precomputed occupancy intervals that define:

- which lane it occupies
- start date
- end date
- band role
- whether the interval is stable continuity or event-staged movement

### Event Nodes

Each node should define:

- node id
- canonical event id
- event type
- event date
- grouped-event identity when applicable
- compact summary label
- sent and received summaries where applicable
- inbound and outbound asset references

### Strands

Each strand segment should define:

- asset id
- lane id
- start date
- end date
- segment type
- relationship to adjacent event nodes

### Connectors / Staging Shapes

Each event connector should define:

- source lane
- destination lane
- direction
- event id
- staging role (`incoming`, `outgoing`, `conversion`, `termination`)
- precomputed timing window

### Additive Context

The export may also carry additive non-core surfaces such as:

- conditional pick families
- draft lottery context

These are part of the broader visualization model but do not need to drive the
first render path.

## Render-Driving Minimum

The first render should require only:

- events
- player assets
- pick assets
- transitions
- daily roster state

The derived visualization export should be built from those surfaces first.

Additional surfaces may be attached for enhancement but should not block the
base graph render.

## Invariants

The visualization model should enforce these invariants:

- no player appears in two player slots on the same day
- no more than `15` main-roster slots are occupied on the same day
- no more than `3` two-way slots are occupied on the same day
- temporary overflow players do not occupy the core slot bands unless their
  status truly changes
- no concrete fallback pick is shown simultaneously with its primary branch
- every rendered strand segment is justified by precomputed visual-state data
- every draft conversion maps one pick strand into one player start
- same-day grouped events resolve to one shared node
- waiver terminations end at the event and do not drift into unrelated lanes

These invariants should become tests in the visualization-export implementation
pass.

## Remaining Open Decisions

The major product decisions are now mostly locked. Remaining open items are
implementation-level, not direction-level:

- exact numeric clamp values for adaptive lead-in and settle-in windows
- exact temporary-overflow entry and exit rules for every contract subtype
- exact final schema for the derived visualization export
- exact rendering conventions for conditional pick-family visibility

## Next Step

The next implementation-oriented step should be:

1. formalize the derived visualization export schema
2. implement a server-side builder for that export
3. add invariant tests
4. update the Astro frontend to render against the derived visualization export

