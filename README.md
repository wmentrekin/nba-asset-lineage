# nba-asset-lineage

Franchise-wide NBA asset lineage pipeline for the Grizzlies organization (Vancouver + Memphis), using a medallion architecture:

- Bronze: raw source ingestion
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

## Current Status

- Medallion stage scaffolding is implemented and idempotent.
- Bronze/Silver/Gold loaders are not implemented yet.
- Visualization currently expects gold exports at:
  - `data/gold/exports/nodes.csv`
  - `data/gold/exports/edges.csv`
