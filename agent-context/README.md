# Agent Context

This folder holds tracked planning and contract docs for the redesign of
`nba-asset-lineage`.

Public docs in this folder should contain product, architecture, and implementation
status context only. Live operational notes, credentials, ad hoc debugging logs,
or local-only handoffs belong in `agent-context/private/`, which is gitignored.

## Core Docs

- `04-confirmed-decisions.md`
  - Agreed product, scope, modeling, visualization, and implementation
    constraints.
- `10-future-vision.md`
  - Product-level end-state vision for the storytelling system.
- `13-source-evidence-model.md`
  - Separation between raw claims, normalized claims, manual overrides, and
    canonical truth.
- `15-implementation-stage-plan.md`
  - Staged roadmap for the redesign implementation.
- `26-canonical-identity-and-reference-contract.md`
  - Locked identity and reference semantics.
- `27-provenance-and-build-versioning-contract.md`
  - Minimum provenance and build-versioning write contract.
- `30-final-planning-readiness-review.md`
  - Final planning readiness judgment before implementation.
- `current-redesign-status.md`
  - Sanitized current implementation status for the redesign path.

## Stage Specs

- `17-stage-01-evidence-layer-spec.md`
  - Evidence schema, source capture, normalization, override loading, and
    validation.
- `18-stage-02-canonical-event-spec.md`
  - Deterministic canonical event construction.
- `19-stage-03-player-tenure-spec.md`
  - Player identity and Memphis-visible tenure modeling.
- `20-stage-04-pick-lifecycle-spec.md`
  - Continuous Memphis pick lifecycle modeling.
- `21-stage-05-event-asset-flow-spec.md`
  - Canonical asset flow into and out of events.
- `22-stage-06-presentation-contract-spec.md`
  - Frontend-ready timeline nodes, edges, lanes, and JSON contract.
- `23-stage-07-editorial-overlay-spec.md`
  - Annotations, eras, game context, and story chapters.
- `24-stage-08-frontend-vertical-slice-spec.md`
  - First interactive Astro frontend slice.

## Use

When assigning implementation work, read the confirmed decisions, the identity
and provenance contracts, the current status doc, and the specific stage spec.
Do not treat the legacy Bronze/Silver/Gold implementation as the target
architecture.
