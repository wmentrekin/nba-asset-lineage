---
name: implement
description: Orchestrate bounded development execution through developer subagents only, then write docs/<feature>/implementation-report.yaml.
---

# Workflow Position

Use `$implement` after `$refine` has approved `docs/<feature>/plan.yaml`.

# Must Read First

1. `.agents/AGENTS.md`
2. `.agents/skills/implement/SKILL.md`
3. `.agents/agents/developer.md`
4. `.agents/templates/task-handoff.yaml`
5. `.agents/templates/implementation-report.yaml`
6. `docs/<feature>/plan.yaml`
7. `docs/<feature>/requirements.yaml`

# Must Spawn

`$implement` must use one or more `developer` agents.

Developer subagents are the default execution path.

Do not do implementation work directly in the main session.

# Inputs

- approved `docs/<feature>/plan.yaml`
- relevant task slice from the plan
- `docs/<feature>/requirements.yaml`
- repo conventions and source-of-truth docs

# Outputs

Required artifact:
- `docs/<feature>/implementation-report.yaml`

Supporting artifact:
- task handoff for each developer based on `.agents/templates/task-handoff.yaml`

Use:
- `.agents/templates/implementation-report.yaml`

# User Updates

Standard update pattern:
- state which task ids are being executed
- state which developer agents were spawned
- state whether work is parallel or sequential
- state that the output will be `docs/<feature>/implementation-report.yaml`

Prompt the user with the next `$command`.

# Subagent Handoff

For each `developer`:
- objective: complete one bounded task or one bounded task batch
- read: `.agents/agents/developer.md`
- include: `docs/<feature>/requirements.yaml`, `docs/<feature>/plan.yaml`, the filled handoff, and only relevant repo files
- specify: owned scope, forbidden scope, expected validation, escalation rules
- output: changes, local validation, blockers, notes

# Process

1. choose the next bounded task set from `docs/<feature>/plan.yaml`
2. determine ordering and safe parallelism
3. create explicit task handoffs
4. spawn developer agents
5. collect implementation outputs
6. integrate into `docs/<feature>/implementation-report.yaml`

# Escalation

Escalate when:
- the approved plan is insufficient for safe execution
- implementation requires a new architecture or product decision
- tasks overlap too heavily for safe delegation
- scope expansion would be required

# Completion

`docs/<feature>/implementation-report.yaml` is complete only if it records:
- task ids attempted
- files and modules changed
- local validation performed
- blockers and known issues
- recommended next step

# Next Recommended Command

- if implementation completed cleanly: `$test` and `$review`
- if failures need diagnosis first: `$debug`
- if plan issues block execution: `$refine`
