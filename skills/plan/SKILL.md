---
name: plan
description: Orchestrate design and task decomposition from frozen requirements, then draft docs/<feature>/plan.yaml.
---

# Workflow Position

Use `$plan` after `$discover` has produced ready requirements.

# Must Read First

1. `.agents/AGENTS.md`
2. `.agents/skills/plan/SKILL.md`
3. `docs/<feature>/requirements.yaml`
4. `.agents/templates/plan.yaml`
5. `.agents/references/workflow-overview.md`

# Must Spawn

`$plan` should still behave as an orchestrator first.

Default behavior:
- do the minimum local synthesis needed to convert requirements into a durable draft
- if repo exploration or decomposition detail requires additional focused analysis, spawn a bounded subagent rather than broadening the main-session context

# Inputs

- `docs/<feature>/requirements.yaml`
- relevant repo docs, code, and architecture references
- project constraints from `.agents/AGENTS.md`

# Outputs

Required artifact:
- draft `docs/<feature>/plan.yaml`

Use:
- `.agents/templates/plan.yaml`

# User Updates

Standard update pattern:
- confirm this is the planning phase
- state what design question or decomposition question is being resolved
- state whether a subagent was spawned
- state that the output is `docs/<feature>/plan.yaml`

Prompt the user with the next `$command`.

# Subagent Handoff

If spawning a bounded helper:
- objective: answer a specific design-support question
- include only the relevant task slice and files
- forbid broad implementation work
- require output that can be folded into `docs/<feature>/plan.yaml`

# Process

1. read `docs/<feature>/requirements.yaml`
2. define the implementation-oriented design
3. decompose into bounded tasks
4. identify dependencies, ordering, and parallelism
5. define expected validation per task
6. write `docs/<feature>/plan.yaml`

# Escalation

Escalate when:
- requirements are incomplete or unstable
- the design depends on a missing product decision
- repo context is still insufficient after bounded research

# Completion

`docs/<feature>/plan.yaml` is complete only if `$refine` can review it and `$implement` can execute it without guessing.

# Next Recommended Command

- if the draft plan is ready: `$refine`
- if requirements are not actually stable: `$discover`
