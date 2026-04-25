---
name: review
description: Orchestrate code review through the reviewer agent against requirements, plan, and implementation report.
---

# Workflow Position

Use `$review` after `$implement` has produced changes and `docs/<feature>/implementation-report.yaml`.

# Must Read First

1. `.agents/AGENTS.md`
2. `.agents/skills/review/SKILL.md`
3. `.agents/agents/reviewer.md`
4. `.agents/references/review-checklist.md`
5. `docs/<feature>/requirements.yaml`
6. `docs/<feature>/plan.yaml`
7. `docs/<feature>/implementation-report.yaml`

# Must Spawn

`$review` must use the `reviewer` agent.

Do not perform the substantive code review only in the main session.

# Inputs

- `docs/<feature>/requirements.yaml`
- `docs/<feature>/plan.yaml`
- `docs/<feature>/implementation-report.yaml`
- changed files or diff
- relevant repo docs

# Outputs

Primary output:
- structured review decision and findings

Reference:
- `.agents/references/review-checklist.md`

# User Updates

Standard update pattern:
- state that the review phase is running
- state that the reviewer agent was spawned
- summarize the highest-severity findings or approval status
- state the likely next `$command`

Prompt the user with the next `$command`.

# Subagent Handoff

For `reviewer`:
- objective: review the implementation against requirements, plan, and scope
- read: `.agents/agents/reviewer.md`
- include: `docs/<feature>/requirements.yaml`, `docs/<feature>/plan.yaml`, `docs/<feature>/implementation-report.yaml`, diff, `.agents/references/review-checklist.md`
- output: decision, findings, gaps, readiness

# Process

1. spawn the reviewer agent
2. collect the review decision and findings
3. determine whether the work proceeds, returns to implementation, or escalates

# Escalation

Escalate when:
- the plan conflicts with the implementation target
- review requires product decisions not present in the artifacts
- the changed behavior cannot be judged responsibly from the available context

# Completion

Review is complete only if it clearly states:
- decision
- actionable findings
- readiness

# Next Recommended Command

- if review approved and tests are acceptable: `$validate`
- if code changes are needed: `$implement`
- if failure diagnosis is needed first: `$debug`
