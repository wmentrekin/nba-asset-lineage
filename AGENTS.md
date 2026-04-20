# AGENTS.md

## Purpose

This repository is for building a Memphis Grizzlies asset-lineage and storytelling system.

The checked-in codebase is **transitional**:

* there is a legacy Python/Postgres medallion pipeline
* there is an active redesign path centered on evidence, canonical lineage, and frontend-ready presentation outputs

Agents must not assume the current legacy pipeline is the final architecture.

## Project Scope

Current working scope is Memphis/Grizzlies-focused.

Important defaults already encoded in the repo:

* franchise: `grizzlies`
* team slug: `memphis-grizzlies`
* team code: `mem`
* team abbrevs: `MEM,VAN`
* default scope starts at `2016-07-01`
* allowed event types include trade, draft pick, waiver, contract signing, extension, re-signing, and conversion

See:

* `configs/lineage_scope.yaml`
* `src/settings.py`

## Primary Architecture Rule

Treat the repo as having **two tracks**:

### 1. Legacy Track

Reference / transitional only.
Includes:

* `src/pipeline_cli.py`
* `src/pipeline/`
* `src/claims_live_ingest.py`
* `sql/0001_bootstrap_bronze_silver.sql`
* `sql/0002_clear_bronze_silver_data.sql`
* `exports/`

This track is useful for:

* understanding prior assumptions
* reusing deterministic transforms where still valid
* mining already-captured historical data

Do **not** assume this is the final product shape.

### 2. Redesign Track

Preferred direction for major new work.
Centered on:

* evidence ingestion and normalization
* canonical events
* canonical player tenure
* canonical pick lifecycle
* canonical event asset flow
* validation and provenance
* presentation-layer exports for the future timeline visualization

Primary redesign entrypoint:

* `src/redesign_cli.py`

## Source of Truth Priority

When making decisions, use this order:

1. active plan doc in `docs/plans/` if one exists
2. repo-level architecture/spec docs
3. this `AGENTS.md`
4. task handoff from manager
5. legacy implementation details only where they do not conflict with redesign goals

If current code conflicts with the intended redesign, prefer the redesign.

## Skills and Workflow

This repo uses two phases:

### Planning

Use:

* `plan-manage`
* `plan-design`
* `plan-review`

Use planning when:

* requirements are unclear
* redesign architecture is still being defined
* a feature affects evidence/canonical/presentation contracts
* implementation would otherwise require major assumptions

Planning output should be a markdown file under:

* `docs/plans/`

### Implementation

Use:

* `implement-manage`
* `implement-develop`
* `implement-review`
* `implement-test`

Use implementation when:

* a plan exists
* requirements are frozen
* the task is bounded enough to assign cleanly

## Subagent Rules

* Keep manager/orchestrator context thin.
* Spawn short-lived subagents with only minimal relevant context.
* For parallel developer agents, assign non-overlapping owned scope.
* Close subagents after completion.
* Persist durable outcomes into files/docs, not only chat.
* Escalate instead of making silent architectural or product assumptions.

## Repo-Specific Working Expectations

### For redesign work

Prefer work that strengthens:

* evidence schema and ingestion
* canonical domain model
* provenance and validation
* deterministic lineage outputs
* frontend-ready presentation contracts

### For legacy work

Only touch the legacy Bronze/Silver/Gold pipeline when:

* fixing a clearly bounded defect
* preserving useful transitional functionality
* extracting logic/data that supports the redesign

Avoid expanding legacy architecture unless explicitly requested.

## Commands

Use `mise` tasks where possible.

### Setup

```bash
mise run setup
```

### Legacy pipeline

```bash
mise run bronze
mise run bronze_live
mise run bronze_dry_run
mise run bronze_live_dry_run
mise run silver
mise run silver_dry_run
mise run gold
mise run pipeline
mise run pipeline_live
mise run visualize
```

### Legacy DB utilities

```bash
mise run db_bootstrap
mise run db_clear_data
```

### Redesign entrypoint

Use the redesign CLI for evidence/canonical work, for example via:

```bash
uv run python -m redesign_cli <command>
```

or the installed script:

```bash
nba-asset-redesign <command>
```

Key redesign command families currently include:

* `bootstrap-evidence`
* `build-evidence`
* `normalize-evidence`
* `load-overrides`
* `validate-evidence`
* `bootstrap-canonical-events`
* `build-canonical-events`
* `validate-canonical-events`
* `bootstrap-canonical-player-tenure`
* `build-canonical-player-tenures`
* `validate-canonical-player-tenures`
* `bootstrap-canonical-pick-lifecycle`
* `build-canonical-pick-lifecycle`
* `validate-canonical-pick-lifecycle`
* `bootstrap-canonical-event-asset-flow`
* `build-canonical-event-asset-flows`
* `validate-canonical-event-asset-flows`

## Testing and Validation Rules

Prefer the lowest-risk sufficient validation first:

1. formatting / lint
2. type / static checks
3. targeted unit tests
4. smoke checks
5. integration checks
6. DB-backed validation
7. deploy/live validation if explicitly appropriate

Repo-specific guidance:

* for legacy pipeline changes, validate with the smallest relevant `mise` task
* for redesign changes, prefer targeted `redesign_cli` validation commands over broad end-to-end runs when possible
* use dry-run modes whenever available before DB-writing modes
* destructive DB commands must be treated carefully

## Database and Environment Rules

Use local `.env` only.

Legacy DB settings expected by the repo:

* `NBA_ASSET_DB_HOST`
* `NBA_ASSET_DB_PORT`
* `NBA_ASSET_DB_NAME`
* `NBA_ASSET_DB_USER`
* `NBA_ASSET_DB_PASSWORD`
* `NBA_ASSET_DB_SSLMODE`

Do not assume safe access to destructive DB operations.
Escalate before:

* wiping schemas
* clearing data
* changing bootstrap SQL
* running risky live validations in ambiguous environments

## Task Naming and Tracking

Use stable task IDs:

`<phase>-<area>-<short-name>`

Examples:

* `plan-redesign-canonical-events`
* `impl-evidence-stage1-bootstrap`
* `impl-canonical-pick-lifecycle`
* `impl-presentation-export-contract`

Statuses:

* `todo`
* `in_progress`
* `in_review`
* `in_testing`
* `blocked`
* `complete`

If needed, store durable task state in:

* `docs/plans/TASKS.md`
  or within the active plan doc

Do not store long chat transcripts.

## Documentation Rules

Update docs when changing:

* canonical contracts
* schema assumptions
* pipeline entrypoints
* task workflows
* setup commands
* validation procedures

Relevant files often include:

* `README.md`
* `AGENTS.md`
* docs under `docs/plans/`
* schema / contract docs if present

## Escalation Rules

Escalate to the user when:

* requirements conflict
* redesign intent is unclear
* a task would materially harden the legacy architecture in the wrong direction
* a canonical contract is underdefined
* risky DB or live-source actions are required
* source data ambiguity requires a product/editorial decision

Do not silently invent lineage rules, evidence precedence, or presentation semantics.

## Definition of Done

A task is done only if:

* implementation is complete
* review feedback is resolved
* relevant validation has run
* docs are updated if needed
* status is clearly reported
* no major open questions remain

## Key Rule

> If a task changes evidence, canonical, or presentation contracts, plan first unless the contract is already explicitly defined.
