-- lineage: one-season Memphis asset-lineage model.
-- source_record holds raw payloads verbatim; transaction (nodes) and asset_movement (strand
-- segments) are derived from them plus data/*.json and are rebuilt wholesale by `lineage derive`.

create schema if not exists lineage;

create table if not exists lineage.source_record (
  id bigserial primary key,
  source text not null,                 -- 'nba_player_movement' | 'curated_snapshot' | 'curated_corrections'
  source_url text not null,
  fetched_at timestamptz not null default now(),
  payload jsonb not null,
  payload_sha256 text not null unique
);

create table if not exists lineage.player (
  id integer primary key,               -- NBA person id
  full_name text not null,
  slug text
);

create table if not exists lineage.pick (
  id text primary key,                  -- '{draft_year}-R{round}-{original_team}', e.g. '2030-R1-ORL'
  draft_year integer not null,
  round integer not null check (round in (1,2)),
  original_team text not null,
  protections text
);

create table if not exists lineage.transaction (
  id text primary key,
  occurred_on date not null,
  kind text not null check (kind in ('baseline','trade','signing','waiver','two_way_signing','two_way_conversion','ten_day','draft_selection')),
  description text not null,
  group_key text,
  source_record_id bigint not null references lineage.source_record(id),
  counterparties text[] not null default '{}'   -- denormalized convenience, not truth
);

create table if not exists lineage.asset_movement (
  id bigserial primary key,
  transaction_id text not null references lineage.transaction(id) on delete cascade,
  asset_type text not null check (asset_type in ('player','pick')),
  asset_id text not null,
  from_holder text,                     -- null only for the baseline origin
  to_holder text not null,              -- team tricode | 'FA' | 'DRAFT'
  contract_type text check (contract_type in ('standard','two_way','ten_day')),
  note text,
  unique (transaction_id, asset_type, asset_id)
);

create index if not exists asset_movement_asset_idx on lineage.asset_movement (asset_type, asset_id);
create index if not exists transaction_occurred_on_idx on lineage.transaction (occurred_on);
