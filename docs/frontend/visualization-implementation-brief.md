# Visualization Implementation Brief

## Purpose

This brief packages the active frontend visualization requirements into one
implementation-facing handoff.

It is the intended entry point for the next `$work` implementation pass that
builds the derived visualization exporter and updates the Astro page to consume
it.

This brief consolidates the locked decisions from:

- [`visualization-model.md`](visualization-model.md)
- [`visualization-export-schema.md`](visualization-export-schema.md)
- [`visualization-algorithm-spec.md`](visualization-algorithm-spec.md)

## Goal

Build the first truthful render path for the Memphis-only 10-year asset
evolution graph using a derived visualization export.

The implementation should:

- derive render-ready lane truth server-side
- preserve slot stability and grouped transaction clarity
- keep time strictly linear by day
- support player and pick continuity
- avoid reintroducing narrative/editorial systems

## Core Locked Decisions

### Architecture

- The frontend must consume a **derived visualization export**
- The frontend must **not** derive lane truth, slot logic, or event geometry
  from raw foundation surfaces
- The browser should only render, scale, animate, and handle interaction

### Lane Model

- player lanes are sacred slots, not asset-owned tracks
- slots `1-15` are the main roster band
- slots `16-18` are the two-way band
- temporary short-term players live in a dynamic overflow band below `18`
- pick lanes are a separate dynamic lower band

### Ordering

- tenure is the primary default ranking factor
- players do not jump above already-occupied slots
- sacred slots reflow upward when vacated
- future manual ordering override capability may be added later, but is not part
  of v1

### Time and Geometry

- time is strictly linear by day
- daily spacing is compact
- grouped same-day actions share one node
- outgoing strands use adaptive lead-in windows
- incoming strands use adaptive settle-in windows
- waiver strands terminate at the event

### Source of Continuity Truth

- `daily_roster_state` is the continuity truth for slot occupancy
- canonical `events` define node semantics
- `transitions` define event continuity behavior
- roster snapshots are validation surfaces, not the render driver

### Picks

- picks appear when they are tradeable and Memphis-relevant
- pick-to-player conversion is a direct handoff at the draft node
- conditional pick families stay bounded additive context
- lottery remains additive-only for now

## Required Foundation Inputs

The implementation should consume these render-driving inputs from the current
foundation export:

- `events`
- `player_assets`
- `pick_assets`
- `transitions`
- `daily_roster_states`

Supporting additive/context inputs that may also be consumed:

- `roster_snapshots`
- `draft_prior_owner_lineages`
- `conditional_pick_families`
- `draft_lottery_results`

## Required Derived Export

The implementation must build a new derived export with this conceptual shape:

- metadata
- lane definitions
- asset identity payloads
- occupancy intervals
- grouped event nodes
- strand segments
- event connectors
- additive context

The detailed contract lives in:

- [`visualization-export-schema.md`](visualization-export-schema.md)

## Required Algorithm Behavior

The implementation must follow these algorithm families:

- initial slot seeding by band
- sacred-slot daily reflow
- separate two-way reflow
- temporary overflow entry/exit rules
- pick-lane eligibility and ordering
- grouped event construction
- adaptive lead/settle window generation
- deterministic segment and connector construction

The detailed algorithm contract lives in:

- [`visualization-algorithm-spec.md`](visualization-algorithm-spec.md)

## Minimum Deliverables

The next build pass should produce at least:

1. Python-side visualization export models
2. a server-side builder that transforms foundation export truth into the new
   visualization export
3. invariant tests for the builder
4. a generated visualization export artifact for the frontend
5. Astro/frontend code updated to consume the derived visualization export
6. docs updated to describe the new export path and command surface

## Required Invariants

The implementation must enforce at least these invariants:

- no player appears in two player lanes on the same day
- no more than `15` main-roster slots are occupied on one day
- no more than `3` two-way slots are occupied on one day
- temporary overflow does not silently displace core-band players
- no concrete fallback pick appears simultaneously with its primary branch
- every connector refers to a valid node and valid asset
- every strand segment refers to a valid lane and valid asset
- every draft conversion maps one pick continuity into one player continuity
- same-day grouped events resolve to one shared node
- waiver terminations end at the event

## Suggested Implementation Order

The next `$work` pass should execute in roughly this order:

1. encode the visualization export schema in Python and TypeScript
2. implement grouped event normalization
3. derive daily band membership and slot occupancy
4. implement player-lane reflow and overflow logic
5. implement pick-lane assignment
6. compute adaptive event windows
7. emit strand segments and connectors
8. add invariant tests
9. generate the visualization export artifact
10. update the Astro renderer to use the new export

## Explicit Non-Goals For The Next Pass

Do not expand scope into:

- editorial overlays
- chaptering
- narrative annotations
- minimap systems
- lottery storytelling
- full conditional branch rendering as normal strands

## Remaining Open Items

These are still intentionally open implementation-level choices:

- exact numeric tuning for adaptive lead/settle windows
- exact temporary-overflow eligibility rules for every contract subtype
- exact first-pass UI treatment of additive conditional pick-family context

These should be resolved pragmatically during implementation without reopening
the larger model decisions.

## Hand-Off Summary

If the next agent/pass reads only one frontend doc, it should read this one
first.

Then:

1. read [`visualization-model.md`](visualization-model.md) for the product
   intent
2. read [`visualization-export-schema.md`](visualization-export-schema.md) for
   the contract shape
3. read [`visualization-algorithm-spec.md`](visualization-algorithm-spec.md) for
   the builder logic

