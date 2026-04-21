# Stage 08 Frontend Vertical Slice Spec

## Purpose

Define the first real frontend implementation slice using the redesigned data
contracts.

## Stage Objective

At the end of Stage 8, the project should have a working interactive timeline
view that proves:

- the redesigned lineage model works end to end
- the presentation contract is sufficient
- editorial overlays can coexist with core lineage rendering

This stage should be designed as the foundation of a polished standalone public
experience, not only an internal engineering demo.

## In Scope

- one primary timeline view
- rendering of player and pick lines
- rendering of event nodes
- basic hover/detail interaction
- date navigation and filtering
- support for at least one overlay type
- support for an ordered chapter or scrollytelling sequence

## Out Of Scope

- full publication polish beyond the first credible standalone experience
- complex branching chapter logic beyond the minimum ordered sequence
- advanced authoring tools
- mobile-perfect production design

## Core UX Requirement

The frontend slice should validate the data model, not mask weaknesses in it.

That means:

- avoid custom semantic hacks in the UI
- render directly from the presentation contract
- surface issues in data shape rather than patching them invisibly in the client

Technical constraint:

- the frontend must fit within an Astro website
- rendering implementation remains open and can be SVG-first, Canvas-first, or a
  hybrid if justified

## Required Views And Behaviors

### Main Timeline View

The main view should show:

- x-axis by day
- y-axis lane groups
- player lines
- pick lines
- event nodes

### Hover / Inspection

The slice should support:

- event hover or click details
- asset hover or click details
- visibility into key metadata from payloads

### Filtering

At minimum:

- asset-type filter
- date-range control

### Navigation

At minimum:

- zoom or windowed date navigation
- horizontal exploration across time

### Narrative / Chaptering

The slice should support:

- ordered chapters
- chapter-triggered timeline focus
- chapter body content adjacent to the visualization

## Data Inputs

The frontend slice should consume:

- `presentation.timeline_nodes`
- `presentation.timeline_edges`
- `presentation.asset_lanes`
- at least one editorial overlay payload

## Rendering Priorities

The first slice should prove:

1. player tenures render correctly
2. returning players do not show false continuity
3. pick lines transition into player lines
4. same-day ordered events appear correctly
5. compound transaction moments are legible

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
- at least one trade event is legible as a transformation point

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
- it renders directly from the new presentation contract
- basic interaction works
- at least one contextual overlay is visible
- the output is useful for evaluating the redesigned system

## What Comes After

After Stage 8, the project can expand into:

- historical backfill and QA
- richer overlays
- deeper narrative chaptering
- visual polish
- eventual retirement of the legacy path
