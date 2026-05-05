# Layout Contract Boundary

## Purpose

Define the frozen responsibility of the layout-oriented contract that sits on
top of Stage 6 presentation truth and alongside Stage 7 chapter text for the
first serious frontend implementation.

## Boundary Summary

The layout contract owns graph-composition truth only. It does not own lineage
semantics, chapter body text, or runtime interaction state.

- Stage 6 owns semantic nodes, semantic edges, lane-group eligibility, same-day
  canonical order, and asset continuity truth.
- Stage 7 owns chapter identity, order, title, slug, and body content.
- The layout contract owns the deterministic graph-shaping decisions the
  renderer should consume directly.
- The frontend owns only ephemeral interaction state.

## Contract Groups

| Group | Owns | Does not own |
| --- | --- | --- |
| `layout_meta` | Chronology bounds, default viewport bounds, day-width hint, axis strategy, minimap segments | Canonical event order, chapter text, live viewport state |
| `lane_layout` | Rendered strand segments, display rank, band slot, compaction group, entry/exit slots, continuity anchors, identity-marker hints | Asset identity semantics, lane-group eligibility rules |
| `event_layout` | Same-day cluster records, cluster order, junction type, slot mappings, transition anchors, transition links | Canonical event meaning, upstream continuity semantics |
| `label_layout` | Inline-label eligibility, label priority, fallback marker requirement, marker side | Asset naming truth or editorial copy |
| `chapter_layout` | Focus windows, highlight targets, minimap anchor linkage, optional default zoom | Chapter title/body/order ownership |

## Frozen Ownership Details

### `layout_meta`

`layout_meta` is the source of truth for:

- `start_date`
- `end_date`
- `default_window_start`
- `default_window_end`
- `default_day_width`
- `axis_strategy`
- `minimap_segments`

These fields define how the graph is composed and navigated by default. They do
not authorize the frontend to rewrite chronology truth.

### `lane_layout`

`lane_layout` is one row per rendered strand segment, not one row per asset.

Its owned fields include:

- `segment_id`
- `asset_id`
- `lane_group`
- `date_start`
- `date_end`
- `display_rank`
- `band_slot`
- `compaction_group`
- `continuity_anchor`
- `entry_slot`
- `exit_slot`
- `identity_marker`

This group freezes vertical ordering and reflow inputs without changing Stage 6
continuity semantics.

### `event_layout`

`event_layout` owns the renderer-facing transaction and transition records:

- `event_id`
- `cluster_id`
- `cluster_date`
- `cluster_order`
- `junction_type`
- `member_event_ids`
- `connected_asset_ids`
- `incoming_slots`
- `outgoing_slots`
- `transition_anchors`
- `transition_links`

This group is where same-day clusters and draft-transition rendering are made
explicit.

### `label_layout`

`label_layout` owns strand-label behavior hints:

- `inline_label_allowed`
- `label_priority`
- `fallback_marker_required`
- `marker_side`

These are layout hints only. They do not change asset naming truth.

### `chapter_layout`

`chapter_layout` is the source of truth for chapter focus behavior:

- `story_chapter_id`
- `window_start`
- `window_end`
- `highlight_asset_ids`
- `highlight_event_ids`
- `minimap_anchor_id`
- `default_zoom`

Visible chapter copy remains outside this contract.

## Frozen Same-Day Clustering Rule

Same-day clustering is representable without mutating Stage 6 truth because the
layout contract derives cluster records from Stage 6-visible inputs only.

The frozen rule is:

- non-trade same-day events remain separate by `event_id`
- trade events on the same date collapse into one cluster only when they share
  the same Stage 6 `transaction_group_key`
- disjoint same-day trade grouping keys remain separate clusters
- `cluster_order` is derived from the earliest Stage 6 canonical order among the
  member events

## Frozen Transition-Link Rule

Pick-to-player transitions are representable without mutating Stage 6 truth
because the layout contract writes renderer-facing continuity links on top of
Stage 6 semantic continuity.

The frozen rule is:

- every rendered continuity hop across a cluster boundary is represented by one
  `transition_link`
- `transition_link.link_type` distinguishes `same_asset`, `pick_to_player`, and
  `event_transition`
- draft conversion renders through `junction_type: draft_transition` plus the
  corresponding pick-to-player `transition_link`

## Frontend Interaction State Boundary

The frontend may own only:

- current viewport position
- current zoom within the frozen bounds
- active hover
- active selection
- active chapter emphasis

The frontend must not derive fallback clustering, continuity, slot motion, or
lane prominence when those facts are absent from exported layout data.
