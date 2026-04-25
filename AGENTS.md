# AGENTS.md

Use this file as the entry point when these workflow assets are imported into a project repo under `.agents/`.

## Command Convention

In Codex, invoke these workflow entrypoints with `$` commands, not `/` commands.

Use:

- `$discover`
- `$plan`
- `$refine`
- `$implement`
- `$test`
- `$review`
- `$debug`
- `$validate`

## First Read Order

When starting in a project repo, read in this order:

1. `.agents/AGENTS.md`
2. the requested skill doc in `.agents/skills/<skill>/SKILL.md`
3. any referenced agent doc in `.agents/agents/`
4. any referenced template in `.agents/templates/`
5. any referenced checklist or guide in `.agents/references/`

Do not rely on memory of the workflow. Re-anchor to these files explicitly.

## Workflow Model

This workflow is orchestration-first.

Top-level skills should do most work through subagents, not in the main session. The main session should:

- orient itself
- read the relevant contracts
- decide the next bounded action
- spawn the correct subagent(s)
- integrate outputs
- communicate clearly with the user

Direct main-session work should be the exception, not the default.

## Default Flow

The normal path is:

`$discover -> $plan -> $refine -> $implement -> $test + $review -> $validate`

Use `$debug` as a read-only side loop when failures need diagnosis before more implementation.

## Skills

- `.agents/skills/discover/SKILL.md`
- `.agents/skills/plan/SKILL.md`
- `.agents/skills/refine/SKILL.md`
- `.agents/skills/implement/SKILL.md`
- `.agents/skills/test/SKILL.md`
- `.agents/skills/review/SKILL.md`
- `.agents/skills/debug/SKILL.md`
- `.agents/skills/validate/SKILL.md`

## Agents

- `.agents/agents/developer.md`
- `.agents/agents/platform-researcher.md`
- `.agents/agents/researcher.md`
- `.agents/agents/reviewer.md`
- `.agents/agents/tester.md`

## Templates

Project-local artifacts should be created under `docs/<feature>/` using these templates:

- `.agents/templates/requirements.yaml`
- `.agents/templates/plan.yaml`
- `.agents/templates/task-handoff.yaml`
- `.agents/templates/implementation-report.yaml`
- `.agents/templates/validation-report.yaml`

Expected project-local outputs:

- `docs/<feature>/requirements.yaml`
- `docs/<feature>/plan.yaml`
- `docs/<feature>/implementation-report.yaml`
- `docs/<feature>/validation-report.yaml`

## References

- `.agents/references/workflow-overview.md`
- `.agents/references/test-ladder.md`
- `.agents/references/review-checklist.md`
- `.agents/references/validation-checklist.md`

## Core Rules

- Keep requirements separate from design.
- Keep design separate from execution.
- Keep execution separate from review and validation.
- Use subagents with minimal necessary context.
- Use project-local paths explicitly when citing workflow files.
- Prefer durable artifact handoffs over long conversational context.
- If a skill should spawn subagents, it must do so explicitly.
- End every skill run with a recommended next command.

## Standard Communication Contract

Every skill should communicate in a regular structure:

- `Workflow Position`
- `Must Read First`
- `Must Spawn`
- `Inputs`
- `Outputs`
- `User Updates`
- `Subagent Handoff`
- `Escalation`
- `Completion`
- `Next Recommended Command`

Every subagent handoff should be explicit about:

- objective
- relevant files
- allowed scope
- forbidden scope
- required output format
- escalation conditions
