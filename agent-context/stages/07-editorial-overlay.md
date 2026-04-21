# Stage 07 Editorial Overlay Spec

## Purpose

Define the contextual and narrative layers that sit alongside canonical lineage
and presentation data.

## Stage Objective

At the end of Stage 7, the system should support:

- timeline annotations
- key calendar markers
- game-level context
- era framing

without mixing editorial storytelling data into canonical transaction truth.

This stage matters for the first public release because that release is expected
to include scrollytelling or chaptered narrative presentation.

## In Scope

- `editorial.annotations`
- `editorial.calendar_markers`
- `editorial.game_overlays`
- `editorial.eras`
- `editorial.story_chapters`

## Out Of Scope

- polished content editing UI
- final publication design system

## Core Principle

Editorial context is additive, not constitutive.

It should enrich the story without changing the underlying lineage model.

## Overlay Types

### Annotations

Narrative notes attached to:

- dates
- date ranges
- specific events
- specific assets

Required fields:

- `annotation_id`
- `annotation_type`
- `title`
- `body`
- `start_date`
- `end_date`
- `event_id`
- `asset_id`
- `priority`

### Calendar Markers

Important league and franchise dates.

Examples:

- draft
- draft lottery
- trade deadline
- start of free agency

Required fields:

- `calendar_marker_id`
- `marker_type`
- `label`
- `marker_date`
- `payload`

### Game Overlays

Daily game context for the timeline axis.

Examples:

- opponent
- home/away
- result
- score
- record impact or notable-game flag

Required fields:

- `game_overlay_id`
- `game_date`
- `opponent`
- `home_away`
- `result`
- `score_display`
- `payload`

### Eras

Post hoc narrative grouping of franchise periods.

Required fields:

- `era_id`
- `title`
- `start_date`
- `end_date`
- `description`
- `priority`

### Story Chapters

Ordered narrative sections for the first-release scrollytelling experience.

Required fields:

- `story_chapter_id`
- `slug`
- `chapter_order`
- `title`
- `body`
- `start_date`
- `end_date`
- `focus_payload`

## Interaction With Presentation Layer

Overlay data should be joinable to the presentation contract by:

- date
- event ID
- asset ID

The frontend should not need to transform editorial content into lineage content.

Story chapters should be able to focus the visualization on:

- date ranges
- event IDs
- graph asset IDs
- lane groups

## Stage 7 Build Strategy

Start with data-first, not tool-first.

Acceptable initial input methods:

- structured files
- manual DB inserts
- simple scripts

Do not block this stage on a custom authoring interface.

However, the planning assumption is that manual editorial entry will eventually
exist, so Stage 7 should not paint the project into a corner where annotations
can only be created by direct DB edits forever.

## Validation

Stage 7 should validate:

- date ranges are coherent
- linked event IDs and asset IDs exist
- overlapping high-priority annotations are intentional

## Test Scenarios

Minimum useful tests:

- annotation attached to a specific event
- annotation attached to a date range
- one game overlay row rendered for a date
- one era spanning multiple seasons

## Deliverable Checklist

Stage 7 is complete when:

- structured editorial/context data can be loaded
- overlays remain separate from canonical lineage truth
- presentation exports can include overlay payloads cleanly

## Next Dependency

Stage 8 should use the presentation and editorial contracts to build the first
real frontend slice.
