# NBA Asset Lineage

## Repository Purpose

This repository is for designing and building a system that models NBA franchise
evolution as a time-indexed asset lineage network.

Today, the checked-in implementation is an early Grizzlies-focused lineage
pipeline with:

- Postgres-backed ingestion and transformation stages
- deterministic IDs for lineage records
- exported graph artifacts
- a lightweight visualization prototype

That implementation should be treated as a reference point, not as the final
architecture.

## Current Redesign Status

The project is in redesign planning.

The long-term goal is broader than the current codebase. Future-state planning
docs live in `agent-context/`.

Start there when making architectural decisions:

- `agent-context/00-project-brief.md`
- `agent-context/01-current-state-vs-target-state.md`
- `agent-context/02-high-level-implementation-plan.md`
- `agent-context/03-open-questions.md`
- `agent-context/10-future-vision.md`

## Working Expectations For Agents

- Do not assume the current Bronze/Silver/Gold pipeline is the correct final
  structure.
- Reuse existing code only where it supports the redesigned canonical model.
- Preserve deterministic, reproducible outputs as a core project value.
- Keep Memphis Grizzlies as the initial working example unless directed
  otherwise, but avoid hard-coding franchise-specific assumptions into new
  architecture.
- Prefer creating explicit planning and contract docs before large structural
  code changes.

## Immediate Planning Priority

The first major design task is to define the canonical domain model for:

- assets
- events
- transformations
- time intervals
- state reconstruction

That model should drive the schema, ingestion pipeline, export contract, and
visualization architecture.
