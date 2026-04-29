# Stage 08 Frontend Vertical Slice Spec

## Purpose

Define the first real frontend implementation slice using the redesigned data
contracts.

## Stage Objective

At the end of Stage 8, the project should have a working interactive timeline
view that proves:

- the redesigned lineage model works end to end
- Stage 6 semantic truth plus the layout contract are sufficient
- chapter overlays can coexist with core lineage rendering without changing
  semantic truth

This stage should be designed as the foundation of a polished standalone public
experience, not only an internal engineering demo.

## In Scope

- one primary timeline view
- rendering of player and pick strands from exported layout data
- rendering of event clusters and transitions from exported layout data
- basic hover/detail interaction
- horizontal viewport navigation and zoom
- minimap-assisted chronology jumping
- support for an ordered chapter sequence

## Out Of Scope

- full publication polish beyond the first credible standalone experience
- complex branching chapter logic beyond the minimum ordered sequence
- advanced authoring tools
- mobile-perfect production design
- semantic clustering or continuity inference in the client
- non-chapter overlay families in the first implementation phase

## Core UX Requirement

The frontend slice should validate the data model, not mask weaknesses in it.

That means:

- avoid custom semantic hacks in the UI
- render semantic truth from Stage 6 through the layout contract
- surface issues in data shape rather than patching them invisibly in the client

Technical constraint:

- the frontend must fit within an Astro website
- the first implementation is SVG-first

## Required Views And Behaviors

### Main Timeline View

The main view should show:

- x-axis by day
- y-axis lane groups
- player strands
- pick strands
- event clusters and transition junctions

### Hover / Inspection

The slice should support:

- event hover or click details
- asset hover or click details
- visibility into key metadata from payloads

### Navigation

At minimum:

- zoom or windowed date navigation
- horizontal exploration across time
- minimap jump navigation

### Narrative / Chaptering

The slice should support:

- ordered chapters
- chapter-triggered timeline focus
- chapter body content adjacent to the visualization

## Data Inputs

The frontend slice should consume:

- Stage 6 presentation export for semantic timeline truth
- layout-contract export for graph composition truth
- chapter-only editorial export for chapter identity and visible text

## Rendering Priorities

The first slice should prove:

1. player tenures render correctly
2. returning players do not show false continuity
3. pick strands transition into player strands through exported draft-transition
   links
4. same-day events appear with the exported clustering behavior
5. compound transaction moments are legible without client-side semantic
   invention

## Minimal Visual Structure

Suggested first layout:

- main roster lane block
- two-way lane block
- future picks lane block
- bottom-axis support for key daily context

The visual system does not need to be fully polished yet, but it should align
with the eventual timeline product.

## Validation

Stage 8 should be considered successful only if the frontend reveals the core
lineage story clearly enough to validate the backend model.

Recommended validation checks:

- sample known Memphis sequence renders coherently
- pick-to-player transition is visually understandable
- leave/return player cases read correctly
- at least one grouped trade event is legible as a transformation point
- viewport and chapter interaction change only frontend state, not exported truth

## Test Dataset Recommendation

The first slice should use a bounded Memphis time range with representative
scenarios:

- signing
- waiver
- leave and return player
- draft pick to player
- trade with multiple assets

## Deliverable Checklist

Stage 8 is complete when:

- one working timeline view exists
- it renders from the Stage 6 presentation export plus the layout contract
- basic interaction works
- chapter context is visible
- the output is useful for evaluating the redesigned system

## What Comes After

After Stage 8, the project can expand into:

- historical backfill and QA
- richer overlays
- deeper narrative chaptering
- visual polish
- eventual retirement of the legacy path
