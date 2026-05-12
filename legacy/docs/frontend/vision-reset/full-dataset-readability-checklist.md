# Full Dataset Readability Checklist

Date: 2026-05-01
Feature: `frontend-vision-reset`
Task: `T11`

## Dataset snapshot

- Generated presentation contract: 605 nodes, 302 edges.
- Generated layout contract: 302 lane segments, 442 event clusters, 41 minimap segments.
- Real generated lane groups currently present in Memphis export: `main_roster`, `future_picks`.
- Real generated `two_way` rows are not present in the current export, so two-way styling on the live dataset could not be visually verified from the generated artifacts alone.

## Built-artifact smoke notes

- `frontend/dist/index.html` built successfully from the generated Memphis artifacts.
- Default built viewport serializes 23 visible strands, 25 visible nodes, 25 visible junctions, 11 visible inline labels, and 24 visible identity markers.
- Hidden decade-wide node/junction SVG is no longer emitted into the built default viewport markup.
- Dense windows now stay inside a scrollable graph shell instead of forcing the whole page to grow with the full SVG height.
- No full interactive browser walkthrough was completed inside the sandbox; checklist findings below combine built-artifact inspection with the generated-data unit coverage required by the plan.

## Checklist

- [x] Default 180-day viewport stays readable on the earliest Memphis slice.
  Evidence: the generated default window (`2016-01-07` to `2016-07-05`) intersects 18 `main_roster` slots and 1 `future_picks` slot, which stays within a bounded shell and keeps both asset classes visible.

- [x] Main-roster and future-pick bands remain distinguishable in the real generated dataset.
  Evidence: current real data includes both groups, and the renderer keeps separate band classes plus separate strand styling for `main_roster` and `future_picks`.

- [~] Two-way distinguishability is covered in code but not visually exercised by the current Memphis export.
  Evidence: `src/lib/timeline.test.ts` still verifies rendering when a `two_way` row is present, but the generated artifacts used for T11 contain no `two_way` rows.

- [x] Traveling identity markers remain visible for compressed strands.
  Evidence: unit coverage for clipped-label fallback still passes, and the built default viewport emits 24 visible identity markers alongside 11 inline labels.

- [x] Leave/return continuity remains readable on real data.
  Evidence: Wayne Selden appears as two Memphis assets (`2016-07-26` to `2016-10-22`, then `2017-03-18` onward), and the generated-data continuity test still passes without `player_id` shortcuts.

- [x] Multi-asset same-day trade grouping remains readable on real data.
  Evidence: the 2019-07-06 Memphis cluster for Kyle Korver, Jae Crowder, Grayson Allen, and Darius Bazley is still covered by the grouped-junction test.

- [x] Pick-to-player conversion remains readable on real data.
  Evidence: the 2016-06-30 draft-transition cluster still exposes both `same_asset` and `pick_to_player` transition links in the generated-data tests.

- [~] Future-pick strand with protections or swap metadata could not be fully verified at the strand level from the current export.
  Evidence: future-pick strands are present, but the generated pick continuity payloads currently expose `protection_summary: null` and empty `protection_payload` objects. Protection/swap text exists on transaction-event descriptions in the presentation contract, not on the future-pick strand payloads consumed by the frontend.

- [x] Chapter/minimap navigation remains attached to the existing viewport model.
  Evidence: generated-data tests for chapter activation and minimap jumping still pass against the full Memphis export.

- [x] Dense late-dataset windows remain navigable without changing layout policy.
  Evidence: a chapter-era 180-day slice around `2024-02-08` intersects 136 `main_roster` rows. The frontend now keeps that density inside the timeline shell with normal vertical scrolling and horizontal-intent viewport traversal.

## Readability findings

- The frontend hardening improved renderer density behavior without inventing new lineage semantics: non-visible nodes and junctions are no longer serialized into the active SVG, inspection no longer rebuilds layout on hover, and dense windows no longer force the whole page to expand vertically.
- The largest remaining readability gap is upstream data shape, not frontend rendering: the current generated Memphis export does not provide live `two_way` rows and does not surface protection/swap metadata on future-pick strand payloads.
