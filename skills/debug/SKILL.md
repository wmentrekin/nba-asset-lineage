---
name: debug
description: Orchestrate read-only failure investigation, produce a diagnosis, and recommend the next owner without making fixes.
---

# Workflow Position

Use `$debug` when `$test`, `$review`, or `$validate` surfaces a failure or ambiguity that needs diagnosis before more changes.

# Must Read First

1. `.agents/AGENTS.md`
2. `.agents/skills/debug/SKILL.md`
3. `.agents/references/workflow-overview.md`
4. relevant artifacts: `docs/<feature>/requirements.yaml`, `docs/<feature>/plan.yaml`, `docs/<feature>/implementation-report.yaml`
5. failing logs, traces, or commands

# Must Spawn

`$debug` should use a bounded subagent whenever the diagnosis would otherwise broaden main-session context too much.

If the failure slice is narrow and already fully loaded, local diagnosis is acceptable. Otherwise spawn a focused diagnostic helper.

# Inputs

- failing command or observed behavior
- relevant artifacts
- logs, traces, test output, or code paths tied to the failure

# Outputs

Primary output:
- diagnosis report in chat

The diagnosis must include:
- observed failure
- evidence examined
- likely cause
- confidence level
- suggested next owner

# User Updates

Standard update pattern:
- state the failure being investigated
- state whether a diagnostic helper was spawned
- state what evidence is being checked
- state the likely next `$command`

Prompt the user with the next `$command`.

# Subagent Handoff

If spawning a helper:
- objective: investigate one narrow failure slice
- include: only the relevant artifacts, logs, and files
- forbid code changes
- require: evidence, likely cause, confidence, next owner

# Process

1. isolate the failure slice
2. inspect the minimum relevant artifacts and evidence
3. produce a read-only diagnosis
4. recommend the smallest responsible next step

# Escalation

Escalate when:
- the failure depends on inaccessible systems or missing data
- the environment is too incomplete for diagnosis
- the real issue appears to be requirements ambiguity

# Completion

`$debug` is complete only if it clearly recommends who should act next.

# Next Recommended Command

- if code changes are needed: `$implement`
- if more testing is needed after a fix: `$test`
- if the issue is really requirements ambiguity: `$discover`
- if final verification can resume: `$validate`
