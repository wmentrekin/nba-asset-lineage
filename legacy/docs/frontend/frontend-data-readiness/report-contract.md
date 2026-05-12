# Frontend Data Readiness Report Contract

## Purpose

This document freezes the durable report shape and blocked-mode semantics for the `frontend-data-readiness` workflow.

The canonical audited inputs remain:

- `frontend/src/data/generated/presentation-contract.json`
- `frontend/src/data/generated/layout-contract.json`
- `frontend/src/data/generated/editorial-chapters.json`

The canonical workflow remains:

1. capture workflow start time
2. regenerate the three frontend-facing artifacts
3. run the audit-only classifier
4. write `readiness-report.yaml` and `summary.md`

The audit command must not fall back to stale checked-in JSON as a substitute.

## Top-Level Schema

`readiness-report.yaml` is frozen to these required top-level keys:

- `artifact_summary`
- `workflow`
- `coverage`
- `population_gaps`
- `alignment_gaps`
- `strengths`
- `blockers`
- `overall_status`

## Artifact Summary

`artifact_summary` is frozen to these nested keys:

- `presentation_contract`
- `layout_contract`
- `editorial_chapters`

Each nested object must contain:

- `path`
- `mtime`
- `size_bytes`
- `fresh_after_workflow_start`

Artifact provenance is limited to observable metadata only. This phase does not introduce a separate regeneration manifest.

## Workflow Block

`workflow` is frozen to these required keys:

- `workflow_start_time`
- `wrapper_command`
- `audit_command`
- `prerequisites`
- `freshness_gate_passed`
- `used_checked_in_artifacts_as_substitute`
- `blocked_mode_reason`

The blocked-mode contract must also capture:

- every prerequisite command attempted
- the first failed prerequisite, if any
- whether any audited artifact failed the freshness gate
- an explicit statement that no mixed fresh/stale readiness classification was performed

## Coverage Rows

`coverage` is a required array with exactly one row per required readiness area:

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

Each coverage row must contain:

- `row`
- `status`
- `schema_supported`
- `live_populated`
- `frontend_consumed`
- `schema_evidence`
- `live_evidence`
- `frontend_evidence`
- `notes`

Row status meanings are frozen to:

- `ready`: all three audit layers are true
- `weak`: schema-supported, but live population is sparse or null-heavy, or frontend-consumption evidence is missing, with no blocked prerequisite
- `blocked`: evaluation could not proceed because a prerequisite or freshness gate failed
- `unresolved`: evaluation proceeded, but export and frontend evidence disagree materially

## Gap And Strength Arrays

`population_gaps`, `alignment_gaps`, `strengths`, and `blockers` are each required arrays of flat objects with keys:

- `row`
- `detail`

Blocked-mode semantics are frozen to:

- `population_gaps` is empty
- `alignment_gaps` is empty
- `strengths` is empty
- `blockers` contains at least one entry naming the first failed prerequisite or freshness failure

## Overall Status

`overall_status` is frozen to these required keys:

- `status`
- `ready_rows`
- `weak_rows`
- `blocked_rows`
- `unresolved_rows`

`overall_status.status` must be one of:

- `ready`
- `weak`
- `blocked`
- `unresolved`

## Frontend Consumption Contract

`frontend_consumed=true` only when:

1. the relevant exported field or structure is referenced by the frontend contract or timeline code path, and
2. the checked-in runtime rubric names exact qualifying test identifiers or assertion targets whose continued presence is verified by the audit.

Path existence alone is insufficient. If a readiness area has no direct frontend field consumer, `frontend_code_paths` must be an empty array and `frontend_consumed` must remain false.

## Schema Support Contract

`schema_supported=true` only when the authoritative selectors declared in [readiness-matrix.yaml](/Users/wentrekin/Documents/nba-asset-lineage/docs/frontend/frontend-data-readiness/readiness-matrix.yaml) remain present in the checked-in schema-support files under:

- `src/presentation/models.py`
- `src/presentation/contract.py`
- `tests/presentation/test_layout_contract.py`

## Leave/Return And Reacquired Semantics

The descriptive repeated-name heuristic is frozen for:

- `leave_and_return`
- `reacquired_players`

The report may only treat these rows as live-populated when repeated exported display names appear across multiple distinct `asset_id` values with non-overlapping exported date ranges, using the row-specific rules frozen in the readiness matrix.

This phase must not invent person-level identity resolution.

## Chapter Contract Boundary

The chapter contract boundary is frozen to:

- chapter text, ordering, and editorial metadata from `editorial-chapters.json`
- chapter focus and navigation truth from `layout-contract.json chapter_layout`

The report must treat frontend reliance on nonexistent editorial focus payloads as a contract misalignment, not as valid consumption evidence.

For chapter-related rows only, T1 predeclares the exact post-T3 selectors in the readiness matrix. T2 may validate selector shape and file lookup, but exact satisfaction of chapter `frontend_code_paths` and `frontend_test_ids` is first enforced after T3 lands.

## Selector Contract

Machine-verified evidence selectors are frozen to one exact format:

`relative/path::exact_substring`

The classifier treats a selector as present only when the file exists and contains the exact substring byte-for-byte. `schema_source_paths`, `frontend_code_paths`, and `frontend_test_ids` must use that format.
