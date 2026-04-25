---
name: discover
description: Orchestrate task identification, requirements gathering, repo research, and optional platform research, then write docs/<feature>/requirements.yaml.
---

# Workflow Position

Use `$discover` at the start of work.

This skill defines the task before planning begins.

# Must Read First

1. `.agents/AGENTS.md`
2. `.agents/skills/discover/SKILL.md`
3. `.agents/agents/researcher.md`
4. `.agents/agents/platform-researcher.md`
5. `.agents/templates/requirements.yaml`
6. `.agents/references/workflow-overview.md`

# Must Spawn

`$discover` should do most work through subagents.

Default behavior:
- spawn a `researcher` when repo context is needed
- spawn a `platform-researcher` when current external facts are needed

Do not keep discovery work in the main session by default.

# Inputs

- user request
- repo docs and source-of-truth files
- prior work artifacts in `docs/<feature>/` if they exist
- project constraints from `.agents/AGENTS.md`

# Outputs

Required artifact:
- `docs/<feature>/requirements.yaml`

Use:
- `.agents/templates/requirements.yaml`

# User Updates

Keep user updates regular and explicit.

Standard update pattern:
- current phase in the workflow
- what subagent was spawned or why none was needed
- what question is being resolved
- what artifact will be updated next

Prompt the user with the next `$command`, not a `/command`.

# Subagent Handoff

For `researcher`:
- objective: answer a narrow repo question
- read: `.agents/agents/researcher.md`
- include: exact repo paths when known
- output: relevant paths, findings, ambiguities

For `platform-researcher`:
- objective: answer a narrow external/platform question
- read: `.agents/agents/platform-researcher.md`
- include: exact question and source constraints
- output: findings suitable for `docs/<feature>/requirements.yaml`

# Process

1. identify the bounded task
2. gather goals, non-goals, constraints, assumptions, acceptance criteria, and open questions
3. spawn repo research and platform research as needed
4. integrate findings into a single requirements contract
5. determine whether requirements are ready for planning
6. write `docs/<feature>/requirements.yaml`

# Escalation

Escalate when:
- the request contains conflicting goals
- a major product decision is unresolved
- repo context is insufficient to define the task responsibly
- external research is needed but the question is still vague
- new scope appears that changes the task materially

# Completion

`docs/<feature>/requirements.yaml` is complete only if it is strong enough for `$plan` to work without reopening basic task definition.

# Next Recommended Command

- if requirements are ready: `$plan`
- if blocking questions remain: continue `$discover`
