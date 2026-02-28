# Repository Outline And File Purpose

As-of date: 2026-02-27

This document explains what each tracked file is for and whether it is active or scaffolded.

Status tags:

- `active`: used in current runnable workflow
- `scaffold`: intentionally present but not fully implemented yet

## Root

| File | Status | Purpose |
|---|---|---|
| `README.md` | active | Project overview, run instructions, and governance pointers. |
| `LICENSE` | active | MIT license. |
| `pyproject.toml` | active | Python package metadata, dependencies, and CLI entrypoints. |
| `mise.toml` | active | Task runner commands. |
| `run_pipeline.py` | active | Thin wrapper that loads `src/` and calls `pipeline_cli`. |
| `.gitignore` | active | Ignore local secrets/artifacts (`.env`, caches, etc.). |

## Configs (all YAML consolidated here)

| File | Status | Purpose |
|---|---|---|
| `configs/lineage_scope.yaml` | active | Franchise/time/event scope policy. |
| `configs/source_catalog.yaml` | active | Source governance catalog (terms posture, API key, coverage notes, open items). |
| `configs/bronze_raw_contract.yaml` | active | Bronze raw-file contract for optional local-file ingest mode (`--raw-dir`). |

## SQL

| File | Status | Purpose |
|---|---|---|
| `sql/0002_franchise_scope.sql` | active | Adds franchise-era dimensions and indexes to Silver tables. |

## Docs

| File | Status | Purpose |
|---|---|---|
| `docs/silver_field_endpoint_coverage.md` | active | Silver field coverage matrix, Sportradar-primary. |
| `docs/bronze_field_source_matrix.md` | active | Bronze field source mapping, Sportradar-primary. |
| `docs/repo_outline_and_file_purpose.md` | active | This file; inventory and purpose map. |

## Source Modules (`src/`)

| File | Status | Purpose |
|---|---|---|
| `src/pipeline_cli.py` | active | Main CLI implementation for `--stage` execution and stage wrappers. |
| `src/bronze_ingest.py` | active | Bronze stage orchestration plus all Bronze ingest internals (raw IO, normalization, DB load). |
| `src/silver_transform.py` | scaffold | Prints Silver scaffold summary only. |
| `src/gold_publish.py` | scaffold | Prints Gold scaffold summary only. |
| `src/visualization.py` | active | Generates interactive HTML graph view from CSV exports. |
| `src/scope.py` | active | Loads scope config. |
| `src/settings.py` | active | Central paths and defaults. |
| `src/db_config.py` | active | Loads DB credentials from env/.env and builds DSN. |
| `src/files.py` | active | Shared file helpers used by visualization. |

## Notes

1. Project code is now flattened directly under `src/` (no nested package namespace).
2. `pipelines/`, `schemas/`, and the old `src/nba_asset_lineage/` tree were removed.
3. `sql/migrations/` was flattened to `sql/` for the single migration script.
4. Bronze internals were consolidated into `src/bronze_ingest.py` as requested.
