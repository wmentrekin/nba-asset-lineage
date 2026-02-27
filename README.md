# nba-asset-lineage

Franchise-wide NBA asset lineage pipeline for the Grizzlies organization (Vancouver + Memphis), using a medallion architecture:

- Bronze: raw source ingestion to Supabase bronze tables
- Silver: canonical events/assets/lineage normalization
- Gold: export-ready graph artifacts

## Scope

- Franchise scope: `grizzlies`
- Start date: `1995-06-23` (day before 1995 expansion draft)
- End date: rolling (configured in `configs/lineage_scope.yaml`)

## Repository Structure

```
nba-asset-lineage/
├── configs/
│   └── lineage_scope.yaml
├── data/
│   ├── bronze/
│   │   ├── raw/
│   │   └── checkpoints/
│   ├── silver/
│   └── gold/
│       └── exports/
├── pipelines/
│   ├── bronze_ingest/
│   ├── silver_transform/
│   ├── gold_publish/
│   └── visualize/
├── schemas/
│   └── bronze_raw_contract.yaml
├── sql/
│   └── migrations/
├── src/
│   └── nba_asset_lineage/
├── run_pipeline.py
├── mise.toml
├── pyproject.toml
└── README.md
```

## Local DB Credentials

Store credentials only in local `.env` (gitignored):

```bash
cp .env.example .env
```

Required variables:

- `NBA_ASSET_DB_HOST`
- `NBA_ASSET_DB_PORT`
- `NBA_ASSET_DB_NAME`
- `NBA_ASSET_DB_USER`
- `NBA_ASSET_DB_PASSWORD`
- `NBA_ASSET_DB_SSLMODE`

Optional:

- `DATABASE_URL`

## Supabase Migration

After your base table bootstrap, apply franchise-scope migration:

- `sql/migrations/0002_franchise_scope.sql`

This adds:

- `franchise_id` and `operating_team_id` columns to Silver tables
- `silver.franchise_team_eras` mapping table
- franchise/time indexes for full-history querying

## Bronze Raw Input Contract

Place raw source files before Bronze ingest:

- `data/bronze/raw/events/**/*.jsonl` or `.json`
- `data/bronze/raw/assets/**/*.jsonl` or `.json`
- `data/bronze/raw/event_asset_links/**/*.jsonl` or `.json`

Schema details:

- `schemas/bronze_raw_contract.yaml`

## Source Governance Before Ingest

Review these before implementing/running any adapters:

- `configs/source_catalog.yaml` (source-level terms posture, key requirements, known coverage)
- `docs/bronze_field_source_matrix.md` (field-level mapping from source -> Bronze columns + gap analysis)
- `docs/silver_field_endpoint_coverage.md` (field-level Silver schema coverage by specific `nba_api` and scraper endpoints)

## Run With Mise

```bash
mise run setup
mise run pipeline
```

Stage-by-stage:

```bash
mise run bronze
mise run silver
mise run gold
mise run visualize
```

Bronze validation-only (no DB writes):

```bash
mise run bronze_dry_run
```

## Current Status

- Bronze DB loader is implemented and idempotent (`ON CONFLICT DO NOTHING`).
- Silver and Gold stages are scaffolded but not implemented yet.
- Visualization currently expects gold exports at:
  - `data/gold/exports/nodes.csv`
  - `data/gold/exports/edges.csv`
