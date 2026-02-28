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
│   ├── lineage_scope.yaml
│   ├── source_catalog.yaml
│   └── bronze_raw_contract.yaml
├── docs/
├── sql/
│   └── 0002_franchise_scope.sql
├── src/
│   ├── pipeline_cli.py
│   ├── bronze_ingest.py
│   ├── silver_transform.py
│   ├── gold_publish.py
│   ├── visualization.py
│   ├── db_config.py
│   ├── scope.py
│   ├── settings.py
│   └── files.py
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

- `sql/0002_franchise_scope.sql`

This adds:

- `franchise_id` and `operating_team_id` columns to Silver tables
- `silver.franchise_team_eras` mapping table
- franchise/time indexes for full-history querying

## Bronze Raw Input Contract

Optional local-file mode (for manual/ad-hoc ingestion) uses `--raw-dir`.
Default raw dir:

- `/tmp/nba-asset-lineage/raw`

Expected subpaths under `--raw-dir`:

- `events/**/*.jsonl` or `.json`
- `assets/**/*.jsonl` or `.json`
- `event_asset_links/**/*.jsonl` or `.json`

Schema details:

- `configs/bronze_raw_contract.yaml`

## Source Governance Before Ingest

Review these before implementing/running any adapters:

- `configs/source_catalog.yaml` (source-level terms posture, key requirements, known coverage)
- `docs/bronze_field_source_matrix.md` (field-level mapping from source -> Bronze columns + gap analysis)
- `docs/silver_field_endpoint_coverage.md` (field-level Silver schema coverage by specific source endpoints, Sportradar-primary)
- `docs/repo_outline_and_file_purpose.md` (inventory of repository files and why each exists)

## Run With UV (Recommended)

```bash
uv sync
uv run python run_pipeline.py --stage bronze --dry-run
```

Direct stage execution:

```bash
uv run python run_pipeline.py --stage bronze
uv run python run_pipeline.py --stage silver
uv run python run_pipeline.py --stage gold
uv run python run_pipeline.py --stage visualize
```

Custom raw input location:

```bash
uv run python run_pipeline.py --stage bronze --raw-dir /path/to/raw
```

## Run With Mise (UV-backed)

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
- Visualization defaults to:
  - `exports/nodes.csv`
  - `exports/edges.csv`
