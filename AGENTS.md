# AGENTS.md

## Purpose

This repository is for building a Memphis Grizzlies asset-lineage system.

The repo is currently in a reset phase.

The previous staged redesign implementation has been archived under `legacy/`
and should not be treated as the active architecture.

## Current Product Goal

The current target is intentionally narrow:

- a Memphis-only Astro page
- a 10-year asset evolution graph
- transactions represented as graph nodes
- player and pick continuity represented as graph strands
- no narrative layer in the base output
- no chaptering or editorial overlay requirements in the base output

## Active Direction

Work should currently focus on these questions, in order:

1. What is the minimum truthful graph output?
2. What exact source data is required to build it?
3. What durable schema should exist in Supabase?
4. How should the graph-ready export be shaped for Astro?

Do not jump ahead into richer storytelling, layout, or editorial systems before
the base lineage truth is stable.

## Architecture Rule

Treat the repo as having two tracks:

### 1. Active Reset Track

This is the current working direction.

Primary active paths:

- `src/foundation/`
- `src/redesign_cli.py`
- `src/db_config.py`
- `frontend/`
- `docs/foundation/`
- `docs/frontend/`

### 2. Legacy Archive Track

Reference only.

Archived under:

- `legacy/src/`
- `legacy/sql/`
- `legacy/tests/`
- `legacy/docs/`
- `legacy/frontend-v1/`
- `legacy/configs/`

This material can be mined for useful assumptions or logic, but it is not the
active target architecture.

## Source of Truth Priority

Use this order when making decisions:

1. current reset intent expressed in repo-root docs
2. active docs under `docs/foundation/` and `docs/frontend/`
3. this `AGENTS.md`
4. explicit user direction in the current thread
5. archived `legacy/` material only when it does not conflict with the reset

## Working Expectations

### Preferred work now

Prefer work that strengthens:

- source-system definition
- smaller lineage contracts
- ingest/storage planning
- durable identity and continuity rules
- graph-ready export thinking
- minimal frontend scaffolding

### Avoid for now

Avoid reintroducing:

- chapter systems
- editorial overlays
- storytelling schema
- large staged pipeline assumptions
- frontend interaction complexity not required by the base graph

## Subagent Rules

- Keep orchestrator context thin.
- Spawn short-lived subagents only when the task is clearly separable.
- Keep write scopes disjoint.
- Close subagents after completion.
- Persist durable outcomes into repo files when appropriate.
- Escalate instead of inventing source semantics or lineage rules.

## Commands

Use `mise` tasks where possible.

Current temporary task surface:

```bash
mise run setup
mise run db_check
mise run frontend_setup
mise run frontend_dev
mise run frontend_check
mise run frontend_test
mise run frontend_build
```

These are scaffolding commands, not a frozen workflow.

## Database and Environment Rules

Use local `.env` only.

Do not assume the next durable Supabase schema is already defined.

Before making DB-shape changes, confirm they support the reset-era minimum graph
contract rather than a legacy or overbuilt staged design.

Escalate before:

- destructive DB operations
- schema wipes
- ambiguous live write operations
- freezing SQL structure that has not been agreed to yet

## Documentation Rules

Update docs when changing:

- the minimum graph contract
- source-system assumptions
- planned Supabase storage model
- frontend/base-export boundaries
- reset-era command surface

Do not let stale staged-redesign language remain in active docs.

## Definition of Done

A reset-era task is done only if:

- the intended reset scope is respected
- implementation is coherent with the smaller target architecture
- relevant validation has run
- docs remain aligned with the reset direction
- no silent architectural assumptions were introduced

## Key Rule

> The repo is starting over from the data foundation. Do not optimize for the
> old staged redesign unless the user explicitly asks to restore something from
> `legacy/`.
