# Agent Context

This folder contains implementation context for agents working on the redesign
of `nba-asset-lineage`. These are not polished public docs; they are the tracked
source of truth for product decisions, design contracts, stage specs, and current
implementation status.

Live operational notes, credentials, ad hoc debugging logs, and local-only
handoffs belong in `agent-context/private/`, which is gitignored.

## Navigation

- `current-status.md`
  - Current implementation status, cleanup state, and next-stage pointer.
- `product/decisions.md`
  - Confirmed product, scope, modeling, visualization, and implementation
    decisions.
- `product/vision.md`
  - Long-term product vision for the Memphis asset-lineage storytelling system.
- `design/evidence-model.md`
  - Source evidence, normalized claims, curated overrides, and canonical-truth
    relationship model.
- `plans/stage-roadmap.md`
  - Stage-by-stage redesign implementation roadmap.
- `contracts/identity-and-reference.md`
  - Locked identity and reference semantics.
- `contracts/provenance-and-build-versioning.md`
  - Minimum provenance and build-versioning write contract.

## Stage Specs

- `stages/01-evidence-layer.md`
  - Evidence schema, source capture, normalization, override loading, and
    validation.
- `stages/02-canonical-events.md`
  - Deterministic canonical event construction.
- `stages/03-player-tenure.md`
  - Player identity and Memphis-visible tenure modeling.
- `stages/04-pick-lifecycle.md`
  - Continuous Memphis pick lifecycle modeling.
- `stages/05-event-asset-flow.md`
  - Canonical asset flow into and out of events.
- `stages/06-presentation-contract.md`
  - Frontend-ready timeline nodes, edges, lanes, and JSON contract.
- `stages/07-editorial-overlay.md`
  - Annotations, eras, game context, and story chapters.
- `stages/08-frontend-vertical-slice.md`
  - First interactive Astro frontend slice.

## Use

When assigning implementation work, read `current-status.md`, the relevant
product/design contracts, and the specific stage spec. Do not treat the removed
legacy Bronze/Silver/Gold implementation as the target architecture.
