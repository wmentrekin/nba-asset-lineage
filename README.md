# nba-asset-lineage

This repository is being redesigned into a public-facing Memphis Grizzlies asset
lineage and storytelling system.

The active implementation path is the redesigned evidence/canonical pipeline.
The old Bronze/Silver/Gold prototype has been removed from the active repo
structure; historical implementation details should be recovered from git
history if needed.

## Product Direction

The project models franchise evolution as a deterministic, time-indexed asset
lineage network that can drive a polished editorial visualization.

Initial release scope:

- Memphis Grizzlies only
- player-centric asset lineage
- continuous pick lifecycle modeling
- compound transaction events from the Memphis perspective
- explicit evidence, curated override, canonical, presentation, and editorial
  layers
- scrollytelling or chaptered frontend experience after the presentation
  contract is stable

## Repository Layout

- `agent-context/`
  - tracked planning, contract, and implementation-status docs
- `configs/data/`
  - curated YAML/JSON data inputs, currently Stage 2 event merge overrides
- `sql/`
  - redesign SQL bootstrap scripts
- `src/evidence/`
  - Stage 1 source capture, normalization, override loading, and validation
- `src/canonical/`
  - Stage 2-5 canonical event, tenure, pick lifecycle, and flow builders
- `src/presentation/`
  - reserved for Stage 6 presentation contract work
- `src/editorial/`
  - reserved for Stage 7 editorial overlay work
- `tests/`
  - local regression tests for evidence and canonical behavior

## Setup

Use local `.env` only. It is gitignored and should contain database connection
values for commands that talk to Postgres.

Install dependencies:

```bash
mise run setup
```

or:

```bash
uv sync
```

## Tests

Run the local test suite:

```bash
mise run test
```

or:

```bash
uv --cache-dir /tmp/uv-cache run pytest -q
```

## Redesign CLI

Run the CLI directly:

```bash
uv --cache-dir /tmp/uv-cache run python -m redesign_cli --help
```

or through the package script:

```bash
uv --cache-dir /tmp/uv-cache run nba-asset-redesign --help
```

## Stage Commands

Stage 1 evidence:

```bash
mise run stage1_bootstrap
mise run stage1_build
mise run stage1_validate
```

Stage 2 canonical events:

```bash
mise run stage2_bootstrap
mise run stage2_build
mise run stage2_validate
```

Stage 3 player tenure:

```bash
mise run stage3_bootstrap
mise run stage3_build
mise run stage3_validate
```

Stage 4 pick lifecycle:

```bash
mise run stage4_bootstrap
mise run stage4_build
mise run stage4_validate
```

Stage 5 event-asset flow:

```bash
mise run stage5_bootstrap
mise run stage5_build
mise run stage5_validate
```

## Curated Overrides

Stage 2 event merge overrides live in:

```text
configs/data/stage2_event_merge_overrides.yaml
```

The default redesign CLI override path is `configs/data`, so normal Stage 1
commands load that bundle without extra flags.

## Current Status

Stages 1 through 5 are implemented in the redesign path. The next architecture
stage is Stage 6, the presentation contract. Frontend implementation should wait
until Stage 6 produces stable frontend-ready data.

See `agent-context/current-status.md` and the navigation map in
`agent-context/README.md` for implementation context.
