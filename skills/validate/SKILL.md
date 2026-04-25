---
name: validate
description: Orchestrate end-to-end verification and final readiness checks, then write docs/<feature>/validation-report.yaml.
---

# Workflow Position

Use `$validate` at the end of the workflow after implementation, testing, and review have produced enough evidence.

# Must Read First

1. `.agents/AGENTS.md`
2. `.agents/skills/validate/SKILL.md`
3. `.agents/references/validation-checklist.md`
4. `.agents/templates/validation-report.yaml`
5. `docs/<feature>/requirements.yaml`
6. `docs/<feature>/plan.yaml`
7. `docs/<feature>/implementation-report.yaml`

# Must Spawn

`$validate` should use a bounded helper when the end-to-end verification surface is wide enough to risk main-session context overflow.

If the evidence is already narrow and assembled, local integration is acceptable. Otherwise spawn a focused validation helper.

# Inputs

- `docs/<feature>/requirements.yaml`
- `docs/<feature>/plan.yaml`
- `docs/<feature>/implementation-report.yaml`
- review outcome
- test outcome
- repo-specific pre-commit or final-check instructions

# Outputs

Required artifact:
- `docs/<feature>/validation-report.yaml`

Use:
- `.agents/templates/validation-report.yaml`
- `.agents/references/validation-checklist.md`

# User Updates

Standard update pattern:
- state that final validation is running
- state whether a helper was spawned
- state which acceptance criteria or final checks are being verified
- state that the output is `docs/<feature>/validation-report.yaml`

Prompt the user with the next `$command`.

# Subagent Handoff

If spawning a helper:
- objective: verify one bounded validation surface
- include: relevant acceptance criteria, test/review results, and final-check instructions
- require: explicit evidence and readiness impact

# Process

1. gather requirements, plan, implementation, review, and test evidence
2. verify acceptance criteria end to end
3. verify pre-commit or equivalent final checks
4. record remaining caveats
5. write `docs/<feature>/validation-report.yaml`

# Escalation

Escalate when:
- final readiness depends on missing evidence
- environment-specific checks are too risky or ambiguous
- requirements and final behavior still disagree

# Completion

Validation is complete only if `docs/<feature>/validation-report.yaml` states:
- final status
- satisfied and unsatisfied acceptance criteria
- evidence used
- remaining caveats
- next actions

# Next Recommended Command

- if ready: no further command required
- if caveats require more work: `$implement`, `$test`, or `$review` as appropriate
- if requirements are still wrong: `$discover`
