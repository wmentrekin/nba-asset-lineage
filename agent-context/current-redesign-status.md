# Current Redesign Status

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

## Current Data Inputs

Curated override inputs live under `configs/data/`.

The active Stage 2 bundle is:

- `configs/data/stage2_event_merge_overrides.yaml`

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

Legacy Bronze/Silver bootstrap SQL has been removed from the active command
surface.

## Next Stage

The next architecture stage is Stage 6: presentation contract generation.

Stage 6 should derive deterministic frontend-ready structures from canonical
data. It should not start the Astro frontend and should not move editorial
content into canonical truth.

Relevant docs for Stage 6:

- `agent-context/22-stage-06-presentation-contract-spec.md`
- `agent-context/21-stage-05-event-asset-flow-spec.md`
- `agent-context/26-canonical-identity-and-reference-contract.md`
- `agent-context/27-provenance-and-build-versioning-contract.md`

## Cleanup Status

Generated legacy exports, legacy Bronze/Silver SQL, root-level overrides, and
the old Bronze/Silver/Gold source command path have been removed from the active
repo structure.
