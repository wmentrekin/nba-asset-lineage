# Frontend Data Readiness Rubric

## Purpose

This rubric freezes the audit semantics for `frontend-data-readiness` so T2 through T4 implement one reproducible readiness classifier rather than ad hoc inspection.

The authoritative machine-readable evidence source is [readiness-matrix.yaml](/Users/wentrekin/Documents/nba-asset-lineage/docs/frontend/frontend-data-readiness/readiness-matrix.yaml). This document defines the status model, row semantics, and chapter-specific selector expectations that the matrix encodes.

## Audit Layers

Every readiness row must be evaluated across exactly three layers:

1. `schema_supported`
   The declared schema-support selectors in the readiness matrix are present, and the row satisfies the matrix `schema_supported_rule`.
2. `live_populated`
   The freshly regenerated frontend-facing artifacts satisfy the row-specific `population_rule`.
3. `frontend_consumed`
   The exact `frontend_code_paths` and `frontend_test_ids` selectors declared in the readiness matrix are present, and the row satisfies the matrix `frontend_consumed_rule`.

`frontend_consumed` is not inferred from file existence, types, or approximate names. It is true only when the matrix-declared exact selectors are present.

## Readiness Rows

This phase audits exactly these rows:

- `main_roster`
- `two_way`
- `future_picks`
- `pick_protections_swaps`
- `pick_to_player`
- `leave_and_return`
- `reacquired_players`
- `chapter_rows`
- `chapter_focus_fields`
- `identity_markers`

## Status Rollup

Per the approved plan, row status is frozen to these meanings:

- `ready`: `schema_supported=true`, `live_populated=true`, and `frontend_consumed=true`
- `weak`: `schema_supported=true` with either sparse or null-heavy live population, or missing frontend-consumption evidence, and no blocked prerequisite
- `blocked`: the audit could not evaluate the row because a required prerequisite failed
- `unresolved`: the row is evaluable, but export-side evidence and frontend expectations disagree materially

`unresolved` includes cases where a schema-supported exported field is populated but the frontend does not consume it, or where the readiness matrix names frontend selectors for a field absent from the regenerated artifacts.

## Freshness And Blocked Mode

Freshness is a hard gate. Every audited artifact must have a modification time later than the workflow start timestamp captured before regeneration begins.

If any prerequisite regeneration step fails, or if any audited artifact fails the freshness gate, the report must enter full blocked mode:

- every required readiness row appears in `coverage`
- every row has `status=blocked`
- `schema_supported`, `live_populated`, and `frontend_consumed` are `null`
- `schema_evidence`, `live_evidence`, and `frontend_evidence` are empty arrays
- `notes` explain the blocked prerequisite or freshness failure
- `overall_status.status=blocked`
- every row is listed in `overall_status.blocked_rows`
- `population_gaps`, `alignment_gaps`, and `strengths` are empty arrays

The audit must not classify a partially refreshed artifact set.

## Evidence Rules

The runtime selector format is frozen to:

`relative/path::exact_substring`

A selector is satisfied only when the referenced file exists and contains the exact substring byte-for-byte.

The readiness matrix is the sole runtime evidence source for:

- `schema_source_paths`
- `schema_supported_rule`
- `json_paths`
- `population_rule`
- `frontend_code_paths`
- `frontend_test_paths`
- `frontend_test_ids`
- `frontend_consumed_rule`

## Row-Specific Population Semantics

The following population thresholds are frozen for this phase:

- `main_roster`: both audited exports contain at least one `main_roster` row
- `two_way`: both audited exports contain at least one `two_way` row; otherwise schema-supported absence is `weak`
- `future_picks`: both audited exports contain at least one `future_picks` row
- `pick_protections_swaps`: at least one frontend-consumed pick strand has non-null `protection_summary` or non-empty `protection_payload`; description-only event text is `weak`
- `pick_to_player`: at least one `pick_to_player` transition link exists and at least one paired drafted-player payload is non-null
- `leave_and_return`: at least one repeated exported player display name appears across multiple distinct `asset_id` values with non-overlapping exported date ranges and a visible gap between tenures
- `reacquired_players`: at least one repeated exported player display name spans multiple distinct `asset_id` values and a later reacquired segment is short enough to exercise overflow suppression independently
- `chapter_rows`: `ready` population requires at least 2 rows in both chapter exports; exactly 1 row in both exports is `weak`; 0 rows in either export is `blocked`
- `chapter_focus_fields`: at least one chapter row has non-empty `window_start` and `window_end` plus either a non-empty highlight list or non-null `default_zoom`; empty highlights with null zoom are `weak`
- `identity_markers`: at least one non-null `image_path` exists; all text-only or null-image coverage is `weak`

## Repeated-Name Heuristic

The audit heuristic for `leave_and_return` and `reacquired_players` is frozen to descriptive repeated exported display-name checks across multiple distinct `asset_id` values with non-overlapping exported date ranges.

This phase must not introduce person-level identity resolution logic.

## Upstream Data Limitation Standard

An issue may be classified as an `upstream data limitation` only when:

1. the freshly regenerated frontend-facing artifacts show absent or null-heavy population for a schema-supported area, and
2. the local frontend/export code path does not drop that field.

This phase does not perform deeper source-stage attribution beyond that limited evidence standard.

## Chapter Selectors

For chapter-related rows, T1 predeclares the exact selectors that later tasks must satisfy:

- `chapter_rows`
  - `frontend/src/lib/timeline.ts::chapterLayoutById`
  - `frontend/src/lib/timeline.test.ts::loads the generated artifacts without missing asset, event, or chapter references`
- `chapter_focus_fields`
  - `frontend/src/lib/timeline.ts::chapterLayoutById.get(chapter.story_chapter_id)`
  - `frontend/src/lib/timeline.test.ts::keeps editorial chapter title, body, and dates additive instead of sourcing scene windows from chapter_layout`

T2 validates matrix shape, selector format, and file-existence lookup for these rows. Exact selector satisfaction for chapter frontend selectors is first required after T3 aligns the frontend code and tests.
