# Current Status

Last updated: 2026-04-20

## Scope

The active implementation path is the redesigned Memphis-only pipeline. The
legacy Bronze/Silver/Gold prototype has been removed from the active repo
structure and is not the target architecture.

## Implemented Stages

- Stage 1 evidence layer is implemented with source capture, normalized claims,
  curated override loading, and validation.
- Stage 2 canonical events are implemented with deterministic clustering,
  ordering, merge overrides, and row-level event provenance.
- Stage 3 player identity and Memphis-visible player tenure modeling is
  implemented.
- Stage 4 continuous pick lifecycle modeling is implemented.
- Stage 5 event-asset flow modeling is implemented.
- Stage 6 presentation contract generation is implemented with deterministic
  timeline nodes, timeline edges, asset lanes, validation, build metadata, and
  JSON export.
- Stage 7 editorial overlay generation is implemented with deterministic
  annotations, calendar markers, game overlays, eras, story chapters, validation,
  build metadata, and JSON export.

## Current Data Inputs

Curated override inputs live under `configs/data/`.

The active Stage 2 bundle is:

- `configs/data/stage2_event_merge_overrides.yaml`

The active Stage 7 editorial seed bundle is:

- `configs/data/stage7_editorial_overlays.yaml`

This bundle is a reproducible curated input, not scratch data. It should remain
tracked unless the underlying event merge decisions are replaced by another
tracked input.

## Current SQL Layout

Redesign bootstrap SQL now lives directly under `sql/`:

- `sql/0001_evidence_bootstrap.sql`
- `sql/0002_canonical_events_bootstrap.sql`
- `sql/0003_player_tenure_bootstrap.sql`
- `sql/0004_pick_lifecycle_bootstrap.sql`
- `sql/0005_event_asset_flow_bootstrap.sql`
- `sql/0006_presentation_contract_bootstrap.sql`

Legacy Bronze/Silver bootstrap SQL has been removed from the active command
surface.

## Next Stage

The next architecture stage is Stage 8: the first frontend slice.

Stage 7 layers editorial context on top of the Stage 6 presentation contract.
It does not alter canonical truth or require frontend-side lineage inference.

## Readiness

The planning set is implementation-ready for the current redesign path:

- identity and reference semantics are locked
- row-level provenance and build metadata requirements are locked
- Stages 1 through 6 are implemented and locally tested
- Stage 7 is implemented and available through the redesign CLI
- Stage 8 remains downstream after the presentation contract and editorial
  overlay are stable

Open refinements around editorial workflow, rendering technology, and future
typed-state expansion are not blockers for Stage 6.

## Cleanup Status

Generated legacy exports, legacy Bronze/Silver SQL, root-level overrides, and
the old Bronze/Silver/Gold source command path have been removed from the active
repo structure.
