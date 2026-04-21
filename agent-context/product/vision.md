# Future Vision

## Objective

Build a complete, time-indexed system that represents the evolution of an NBA
franchise as an asset transformation network and presents it as a high-quality,
interactive data journalism visualization.

The first working franchise is the Memphis Grizzlies, but the conceptual model
should be extensible beyond a single team.

## Core Representation

The system models a franchise as:

- a set of assets
- a sequence of events
- a continuous timeline
- a directed lineage graph

### Assets

- players
- contracts or player-linked roster assets, pending final canonical definition
- draft picks, including protections and origin lineage

### Events

- drafts
- trades
- signings
- waivers and buyouts
- pick conveyances

### Relationships

- assets flow into events
- events transform assets
- assets flow out of events

The intended result is a directed acyclic temporal graph where:

- nodes are events
- edges are assets moving through time

## Time-Based Structure

Time is the primary organizing dimension.

The system should support:

- precise event ordering
- state reconstruction at any point in time
- continuous tracking of asset ownership and transformation

## Primary Visual Deliverable

The main product is a timeline-based lineage visualization.

### Layout

- X-axis: continuous time at daily resolution
- Y-axis: structured asset lanes

Planned Y-axis sections:

1. main roster
2. two-way roster slots
3. future draft picks

Each row should represent a persistent slot over time, not just a list of
entities.

### Asset Representation

Players should render as horizontal lines across time and occupy roster slots.

Draft picks should render in future-pick lanes, persist until draft execution,
and transition into player lines when drafted.

### Event Representation

Events are transformation points that must be visually distinct and precisely
time-aligned.

Examples:

- trade: multiple incoming assets merge into a node and multiple outgoing assets
  split from it
- draft: pick line transitions into player line
- waiver or buyout: player line terminates
- signing: new player line begins

### Lineage Continuity

The visualization must make it easy to follow:

- how assets evolve over time
- how one asset becomes another
- how groups of assets transform through transactions

Example lineage:

- draft pick -> player -> traded -> new players and picks

## Overlay Layers

The core lineage model should support additive overlays without changing the
underlying structure.

Initial overlay categories:

- game timeline
- organizational context such as coaches and front office
- narrative annotations

## Interaction Model

The visualization should support:

- hover for metadata and transaction details
- zoom and scroll across time ranges
- filtering by asset type
- tracing a single asset across its lineage path

## Data-To-Visualization Contract

The frontend should consume structured lineage data directly.

The frontend should not need custom interpretive logic to understand the
underlying lineage semantics.

The output contract should include:

- nodes with event metadata
- edges with asset identity and temporal bounds
- metadata for assets, events, and annotations
- overlay payloads for contextual layers

## Editorial Goal

This is not only a technical system.

It should support telling the story of franchise evolution over time, including:

- inflection points
- strategic decisions
- peak and decline cycles
- era framing

The data model should therefore support:

- notes attached to dates, assets, or events
- links to external references
- narrative content adjacent to the visualization

## Design Goals

### Visually

- clean
- modern
- intuitive
- high signal-to-noise

### Technically

- deterministic
- reproducible
- extensible

### Conceptually

- accurate representation of asset flow
- easy to reason about
- scalable to additional franchises

## Final Outcome

The completed system should produce:

1. a structured, time-indexed lineage dataset
2. a graph representation of asset transformations
3. a fully interactive timeline visualization
4. a narrative-driven presentation layer

Together these form a data-driven story of franchise evolution grounded in a
rigorous model.
