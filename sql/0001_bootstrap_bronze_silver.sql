-- Full bootstrap for local/Supabase setup.
-- Recreates bronze + silver schemas and all tables required by current pipeline.
-- WARNING: destructive (drops existing bronze/silver data).

begin;

create extension if not exists pgcrypto;

drop schema if exists bronze cascade;
drop schema if exists silver cascade;

create schema bronze;
create schema silver;

-- ---------------------------------------------------------------------------
-- BRONZE: raw ingestion layer
-- ---------------------------------------------------------------------------

create table bronze.ingest_runs (
  run_id uuid primary key default gen_random_uuid(),
  pipeline_name text not null,
  source_system text not null,
  run_mode text not null,
  status text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  records_seen integer not null default 0,
  records_written integer not null default 0,
  notes text,
  error_text text
);

create index idx_bronze_ingest_runs_started_at
  on bronze.ingest_runs (started_at desc);

create index idx_bronze_ingest_runs_status
  on bronze.ingest_runs (status, started_at desc);

create table bronze.raw_events (
  raw_event_id uuid primary key default gen_random_uuid(),
  ingest_run_id uuid references bronze.ingest_runs(run_id) on delete set null,
  source_system text not null,
  source_event_ref text not null,
  event_date_raw text,
  event_type_raw text,
  source_url text,
  source_payload jsonb not null default '{}'::jsonb,
  payload_hash text not null,
  created_at timestamptz not null default now()
);

create unique index uq_bronze_raw_events_dedupe
  on bronze.raw_events (source_system, source_event_ref, payload_hash);

create index idx_bronze_raw_events_source_ref
  on bronze.raw_events (source_system, source_event_ref);

create index idx_bronze_raw_events_created
  on bronze.raw_events (created_at desc);

create table bronze.raw_assets (
  raw_asset_id uuid primary key default gen_random_uuid(),
  ingest_run_id uuid references bronze.ingest_runs(run_id) on delete set null,
  source_system text not null,
  source_asset_ref text not null,
  asset_type_raw text,
  effective_date_raw text,
  source_payload jsonb not null default '{}'::jsonb,
  payload_hash text not null,
  created_at timestamptz not null default now()
);

create unique index uq_bronze_raw_assets_dedupe
  on bronze.raw_assets (source_system, source_asset_ref, payload_hash);

create index idx_bronze_raw_assets_source_ref
  on bronze.raw_assets (source_system, source_asset_ref);

create index idx_bronze_raw_assets_created
  on bronze.raw_assets (created_at desc);

create table bronze.raw_event_asset_links (
  raw_link_id uuid primary key default gen_random_uuid(),
  ingest_run_id uuid references bronze.ingest_runs(run_id) on delete set null,
  source_system text not null,
  source_event_ref text not null,
  source_asset_ref text not null,
  action_raw text not null default '',
  direction_raw text,
  effective_date_raw text,
  source_payload jsonb not null default '{}'::jsonb,
  payload_hash text not null,
  created_at timestamptz not null default now()
);

create unique index uq_bronze_raw_links_dedupe
  on bronze.raw_event_asset_links (
    source_system,
    source_event_ref,
    source_asset_ref,
    action_raw,
    payload_hash
  );

create index idx_bronze_raw_links_event_ref
  on bronze.raw_event_asset_links (source_system, source_event_ref);

create index idx_bronze_raw_links_asset_ref
  on bronze.raw_event_asset_links (source_system, source_asset_ref);

create index idx_bronze_raw_links_created
  on bronze.raw_event_asset_links (created_at desc);

-- ---------------------------------------------------------------------------
-- SILVER: robust normalized lineage layer
-- ---------------------------------------------------------------------------

create table silver.events (
  event_id text primary key,
  source_system text not null,
  source_event_ref text not null,
  event_date date not null,
  event_type text not null,
  event_label text,
  description text,
  source_url text,
  team_id text,
  event_order integer not null default 0,
  franchise_id text not null default 'grizzlies',
  operating_team_id text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index uq_silver_events_source
  on silver.events (source_system, source_event_ref);

create index idx_silver_events_time
  on silver.events (event_date, event_order);

create index idx_silver_events_franchise_time
  on silver.events (franchise_id, event_date, event_order);

create index idx_silver_events_operating_team_time
  on silver.events (operating_team_id, event_date, event_order);

create table silver.assets (
  edge_id text primary key,
  asset_id text not null,
  asset_key text not null,
  source_system text not null,
  source_asset_ref text not null,
  asset_type text not null,
  subtype text,
  start_date date not null,
  end_date date,
  is_active_at_end boolean not null default false,
  player_name text,
  contract_expiry_year integer,
  average_annual_salary numeric(14,2),
  acquisition_method text,
  prior_transactions jsonb,
  original_team text,
  pick_year integer,
  pick_round integer,
  pick_number integer,
  protections_raw text,
  swap_conditions_raw text,
  owner_team_id text,
  franchise_id text not null default 'grizzlies',
  operating_team_id text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (end_date is null or end_date >= start_date)
);

create index idx_silver_assets_asset_interval
  on silver.assets (asset_id, start_date, end_date);

create index idx_silver_assets_source_ref
  on silver.assets (source_system, source_asset_ref);

create index idx_silver_assets_franchise_time
  on silver.assets (franchise_id, start_date, asset_id);

create index idx_silver_assets_operating_team_time
  on silver.assets (operating_team_id, start_date, asset_id);

create table silver.event_asset_lineage (
  lineage_id text primary key,
  event_id text not null references silver.events(event_id) on delete cascade,
  asset_id text not null,
  action_raw text,
  direction_raw text,
  effective_date date not null,
  source_system text not null,
  source_event_ref text not null,
  source_asset_ref text not null,
  source_link_id text,
  franchise_id text not null default 'grizzlies',
  created_at timestamptz not null default now()
);

create index idx_silver_lineage_event
  on silver.event_asset_lineage (event_id);

create index idx_silver_lineage_asset_time
  on silver.event_asset_lineage (asset_id, effective_date);

create index idx_silver_lineage_franchise_time
  on silver.event_asset_lineage (franchise_id, effective_date, event_id);

create table silver.franchise_team_eras (
  franchise_id text not null,
  operating_team_id text not null,
  team_name text not null,
  era_start date not null,
  era_end date,
  primary key (franchise_id, era_start),
  check (era_end is null or era_end >= era_start)
);

insert into silver.franchise_team_eras (
  franchise_id,
  operating_team_id,
  team_name,
  era_start,
  era_end
) values
  ('grizzlies', 'VAN', 'Vancouver Grizzlies', date '1995-06-23', date '2001-06-30'),
  ('grizzlies', 'MEM', 'Memphis Grizzlies', date '2001-07-01', null);

commit;
