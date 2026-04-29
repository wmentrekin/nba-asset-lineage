# Stage 6 Gap Audit

## Purpose

Record the frozen boundary between Stage 6 presentation truth, the new
layout-oriented contract, and frontend interaction state for
`frontend-vision-reset` task `T1`.

## Frozen Conclusion

No Stage 6 contract mutation is required for the first implementation.

Stage 6 already carries the semantic truth needed by later frontend work:

- lineage continuity
- lane-group eligibility
- same-day canonical order
- the transaction grouping key consumed by layout export
- pick-to-player transition semantics

The layout contract is the approved place to add graph-composition truth without
rewriting Stage 6 semantics.

## Ownership Classification

| Behavior | Frozen owner | Notes |
| --- | --- | --- |
| Semantic event nodes and edges | Stage 6 semantic truth | Canonical lineage remains explicit before any layout shaping. |
| Asset continuity truth across Memphis-visible tenures | Stage 6 semantic truth | Leave/return cases remain separate tenures; frontend does not infer continuity. |
| Lane-group eligibility for `main_roster`, `two_way`, and `future_picks` | Stage 6 semantic truth | Eligibility comes from canonical state, not layout or client logic. |
| Same-day canonical event order | Stage 6 semantic truth | Layout may read it, but does not redefine it. |
| `transaction_group_key` visibility for same-day trade grouping | Stage 6 semantic truth | This is the Stage 6 input that lets layout cluster grouped trades. |
| Pick-to-player transition semantics | Stage 6 semantic truth | Layout renders the transition; it does not invent the meaning. |
| Display ranking and band slots | Layout-contract truth | Graph prominence and vertical placement belong to layout, not Stage 6. |
| Compaction groups and reflow slots | Layout-contract truth | `compaction_group`, `entry_slot`, `exit_slot`, and related geometry are composition decisions. |
| Same-day clustered transaction moments | Layout-contract truth | Clustering is derived from Stage 6-visible inputs and written explicitly for the renderer. |
| Transition anchors and transition links | Layout-contract truth | Includes same-asset continuity hops and pick-to-player transitions across cluster boundaries. |
| Inline-label eligibility and fallback-marker hints | Layout-contract truth | These are render hints, not lineage semantics. |
| Identity-marker label/image hints | Layout-contract truth | Marker content is layout/export-owned; runtime lookup is out of scope. |
| Default viewport bounds, axis hints, and minimap segments | Layout-contract truth | These are graph-composition defaults, not semantic truth. |
| Current viewport position | Frontend interaction state | User-driven state only. |
| Current zoom within frozen bounds | Frontend interaction state | The client may change zoom, but does not rewrite exported defaults. |
| Active hover, selection, and chapter emphasis | Frontend interaction state | Interaction state remains ephemeral and client-owned. |

## Resolved Non-Gaps

### Same-Day Grouped Events

Same-day grouped events are representable without mutating Stage 6 truth.

The frozen rule is:

- Stage 6 preserves event identity, same-day order, and `transaction_group_key`
- layout export collapses same-date trade events only when they share that key
- non-trade same-day events, or trade events with disjoint keys, remain separate

### Pick-To-Player Transitions

Pick-to-player transitions are representable without mutating Stage 6 truth.

The frozen rule is:

- Stage 6 remains authoritative for the semantic continuity between the pick and
  the resulting player asset
- layout export writes the renderer-facing draft transition records, including
  transition links and junction typing
- the frontend renders the supplied transition without semantic inference

## Guardrails

- Stage 6 must not absorb display ranking, band-slot policy, compaction, or
  minimap concerns.
- The layout contract must not change lineage truth, editorial text ownership,
  or canonical event ordering.
- The frontend must not create fallback clustering, continuity, or lane
  semantics when exported data is missing or weak.
