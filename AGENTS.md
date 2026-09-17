# AGENTS.md

## Shared Workflow Framework

This repo imports a shared agent workflow at `.agents/` (git subtree). Read `.agents/AGENTS.md`
before starting substantial work; invoke it with `/work`.

## Purpose

This repository builds a simple, working, one-season Memphis Grizzlies asset-lineage pipeline:
opening night 2025-26 through today. The prior multi-season, multi-table implementation was
deleted in a reset (it remains in git history on `main`). Complexity gets added later, only once
this smaller scope is proven correct.

## Scope rules

- Memphis only.
- Window: 2025-26 opening night through the most recent load date.
- Node kinds: trade, signing, waiver/release, two-way signing, two-way conversion, ten-day or
  Exhibit-10 signing, draft selection, plus the virtual `baseline` opening-night node.
- Assets (strands): players and Memphis-owned future draft picks.
- Not in scope: G League moves, swap rights/cash/trade exceptions as strands, multi-season
  history, any frontend.

## Architecture

- A single Python package, `src/lineage/`.
- CLI verbs: `migrate`, `fetch`, `derive`, `validate`, `export`, `render`, `check-db`.
- Raw feed payloads are stored verbatim in `source_record`.
- `derive` is a pure function of raw payloads + `data/*.json` + code. It rebuilds all derived
  tables inside one transaction, with fully deterministic row ordering.
- Strands (per-asset holder timelines) are computed on demand by `lineage/timeline.py`; they are
  never stored.

## Rules

- Never hand-edit derived tables. Fix bad input via `data/corrections.json` and re-run `derive`.
- Unparseable pick text in a transaction description fails the load loudly — it does not get
  silently dropped or guessed at.
- Escalate before any destructive database operation.
- Python only, managed with `uv`. No Node, no frontend.
- Keep the schema at five tables unless the user explicitly agrees to add one.
- Docs live in `README.md`; keep it current when behavior changes.

## Commands

Use `mise` tasks:

```bash
mise run setup      # uv sync
mise run check_db   # confirm DATABASE_URL connectivity
mise run migrate    # apply the lineage schema
mise run fetch      # pull and store the raw feed
mise run derive     # rebuild derived tables
mise run validate   # check graph invariants
mise run export     # write graph.json
mise run render     # draw graph.svg
mise run load       # fetch + derive + validate + export + render
mise run test       # run the offline pytest suite
```

## Definition of done

A task is done only when:

- The offline pytest suite passes.
- `mise run load` is green in CI.
- README.md reflects any changed behavior or commands.
