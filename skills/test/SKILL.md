---
name: test
description: Orchestrate graduated technical validation through the tester agent and report readiness, failures, and gaps.
---

# Workflow Position

Use `$test` after `$implement` has produced `docs/<feature>/implementation-report.yaml`.

# Must Read First

1. `.agents/AGENTS.md`
2. `.agents/skills/test/SKILL.md`
3. `.agents/agents/tester.md`
4. `.agents/references/test-ladder.md`
5. `docs/<feature>/plan.yaml`
6. `docs/<feature>/implementation-report.yaml`

# Must Spawn

`$test` must use the `tester` agent.

Do not run the substantive testing flow only in the main session.

# Inputs

- `docs/<feature>/plan.yaml`
- `docs/<feature>/implementation-report.yaml`
- relevant changed files
- repo testing instructions

# Outputs

Primary output:
- structured testing result suitable for `$debug`, `$implement`, or `$validate`

Reference:
- `.agents/references/test-ladder.md`

# User Updates

Standard update pattern:
- state the changed scope under test
- state that the tester agent was spawned
- state the current ladder step or failure point
- state the likely next `$command`

Prompt the user with the next `$command`.

# Subagent Handoff

For `tester`:
- objective: validate the changed scope with the smallest sufficient ladder subset
- read: `.agents/agents/tester.md`
- include: `docs/<feature>/plan.yaml`, `docs/<feature>/implementation-report.yaml`, changed files, repo test instructions
- output: status, checks run, failures, gaps

# Process

1. spawn the tester agent
2. run the ladder in order: lint -> types -> unit -> integration -> smoke
3. stop early on blocking failures
4. report failures, gaps, and likely next owner

# Escalation

Escalate when:
- the environment is unsafe or ambiguous
- destructive or live validation would be required
- intended behavior cannot be inferred from the plan

# Completion

Testing is complete only if the result clearly states:
- what was run
- what passed
- what failed
- what remains untested

# Next Recommended Command

- if tests passed or passed with gaps: `$validate`
- if failures need diagnosis: `$debug`
- if implementation fixes are clearly needed: `$implement`
