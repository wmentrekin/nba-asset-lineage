# Workflow Overview

This workflow is designed for project-local use under `.agents/`.

## Command Convention

Use `$` commands in Codex:

- `$discover`
- `$plan`
- `$refine`
- `$implement`
- `$test`
- `$review`
- `$debug`
- `$validate`

## Default Flow

`$discover -> $plan -> $refine -> $implement -> $test + $review -> $validate`

Use `$debug` when a failure needs read-only investigation before more changes are made.

## Orchestration Principle

Top-level skills are orchestrators first. They should:

- read `.agents/AGENTS.md`
- read the invoked skill doc
- read the relevant agent and template docs
- spawn the correct bounded subagent(s)
- integrate outputs into the right project-local artifact

They should not default to doing the main work in the top-level session.

## Agent Roles

- `developer`: `.agents/agents/developer.md`
- `platform-researcher`: `.agents/agents/platform-researcher.md`
- `researcher`: `.agents/agents/researcher.md`
- `reviewer`: `.agents/agents/reviewer.md`
- `tester`: `.agents/agents/tester.md`

## Durable Contracts

Use these templates:

- `.agents/templates/requirements.yaml`
- `.agents/templates/plan.yaml`
- `.agents/templates/task-handoff.yaml`
- `.agents/templates/implementation-report.yaml`
- `.agents/templates/validation-report.yaml`

Write project-local outputs to:

- `docs/<feature>/requirements.yaml`
- `docs/<feature>/plan.yaml`
- `docs/<feature>/implementation-report.yaml`
- `docs/<feature>/validation-report.yaml`

## Workflow Principles

- Re-anchor to workflow docs explicitly.
- Prefer narrow subagent context.
- Keep outputs durable and standardized.
- End each skill run with the next recommended `$command`.
