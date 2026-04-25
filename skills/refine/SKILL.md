---
name: refine
description: Orchestrate plan review with the reviewer agent, run the plan review loop, and approve or escalate within three cycles.
---

# Workflow Position

Use `$refine` after `$plan` has produced a draft `docs/<feature>/plan.yaml`.

# Must Read First

1. `.agents/AGENTS.md`
2. `.agents/skills/refine/SKILL.md`
3. `.agents/agents/reviewer.md`
4. `.agents/references/review-checklist.md`
5. `docs/<feature>/requirements.yaml`
6. `docs/<feature>/plan.yaml`

# Must Spawn

`$refine` must use the `reviewer` agent.

Do not perform the substantive plan critique only in the main session.

# Inputs

- `docs/<feature>/requirements.yaml`
- draft `docs/<feature>/plan.yaml`

# Outputs

Required artifact:
- approved or revised `docs/<feature>/plan.yaml`

Reference:
- `.agents/templates/plan.yaml`

# User Updates

Standard update pattern:
- state the current review cycle count
- state that the reviewer agent was spawned
- summarize the current blocking issues or approval status
- state whether the next action is another refinement cycle or a handoff to `$implement`

Prompt the user with the next `$command`.

# Subagent Handoff

For `reviewer`:
- objective: critique the plan against requirements and readiness
- read: `.agents/agents/reviewer.md`
- include: `docs/<feature>/requirements.yaml`, `docs/<feature>/plan.yaml`, `.agents/references/review-checklist.md`
- output: decision, findings, gaps, readiness

# Process

1. spawn the reviewer on the current plan
2. collect the decision and findings
3. revise the plan or send it back for revision
4. repeat up to 3 cycles
5. approve, escalate, or send back to `$discover`

# Escalation

Escalate when:
- requirements and design conflict
- architecture choices cannot be resolved responsibly
- the plan still depends on unknown facts
- scope is no longer bounded

# Completion

The plan is complete only if:
- it aligns with requirements
- task boundaries are clear
- dependencies are explicit
- validation expectations exist
- `$implement` should not need to guess

# Next Recommended Command

- if the plan is approved: `$implement`
- if requirements are the real blocker: `$discover`
- if another review cycle is needed: continue `$refine`
