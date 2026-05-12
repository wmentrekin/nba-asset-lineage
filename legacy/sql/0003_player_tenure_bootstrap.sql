-- Stage 3 canonical player tenure bootstrap.
-- Adds player identity, player tenure, asset, and asset-state tables on top of
-- the existing Stage 1 evidence and Stage 2 canonical event schema.

begin;

create schema if not exists canonical;

create table if not exists canonical.player_identity (
  player_id text primary key,
  display_name text not null,
  normalized_name text not null,
  nba_person_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_canonical_player_identity_normalized_name
  on canonical.player_identity (normalized_name);

create table if not exists canonical.player_identity_provenance (
  player_identity_provenance_id text primary key,
  player_id text not null references canonical.player_identity (player_id) on delete cascade,
  source_record_id text references evidence.source_records (source_record_id) on delete set null,
  claim_id text references evidence.normalized_claims (claim_id) on delete set null,
  override_id text references evidence.overrides (override_id) on delete set null,
  provenance_role text not null,
  fallback_reason text,
  created_at timestamptz not null default now(),
  constraint chk_canonical_player_identity_provenance_support
    check (
      source_record_id is not null
      or claim_id is not null
      or override_id is not null
      or fallback_reason is not null
    )
);

create index if not exists idx_canonical_player_identity_provenance_player
  on canonical.player_identity_provenance (player_id);

create table if not exists canonical.player_tenure (
  player_tenure_id text primary key,
  player_id text not null references canonical.player_identity (player_id) on delete cascade,
  tenure_start_date date not null,
  tenure_end_date date,
  entry_event_id text not null references canonical.events (event_id) on delete restrict,
  exit_event_id text references canonical.events (event_id) on delete set null,
  tenure_type text not null,
  roster_path_type text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_canonical_player_tenure_interval
    check (tenure_end_date is null or tenure_end_date >= tenure_start_date)
);

create index if not exists idx_canonical_player_tenure_player_dates
  on canonical.player_tenure (player_id, tenure_start_date, coalesce(tenure_end_date, tenure_start_date));

create table if not exists canonical.asset (
  asset_id text primary key,
  asset_kind text not null,
  player_tenure_id text unique references canonical.player_tenure (player_tenure_id) on delete cascade,
  pick_asset_id text unique,
  asset_label text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_canonical_asset_single_subtype
    check (
      (
        player_tenure_id is not null
        and pick_asset_id is null
        and asset_kind = 'player_tenure'
      )
      or (
        player_tenure_id is null
        and pick_asset_id is not null
        and asset_kind = 'pick_continuity'
      )
    )
);

create index if not exists idx_canonical_asset_kind
  on canonical.asset (asset_kind);

create table if not exists canonical.asset_provenance (
  asset_provenance_id text primary key,
  asset_id text not null references canonical.asset (asset_id) on delete cascade,
  player_tenure_id text references canonical.player_tenure (player_tenure_id) on delete cascade,
  pick_asset_id text,
  source_record_id text references evidence.source_records (source_record_id) on delete set null,
  claim_id text references evidence.normalized_claims (claim_id) on delete set null,
  override_id text references evidence.overrides (override_id) on delete set null,
  provenance_role text not null,
  fallback_reason text,
  created_at timestamptz not null default now(),
  constraint chk_canonical_asset_provenance_support
    check (
      source_record_id is not null
      or claim_id is not null
      or override_id is not null
      or fallback_reason is not null
    )
);

create index if not exists idx_canonical_asset_provenance_asset
  on canonical.asset_provenance (asset_id);

create index if not exists idx_canonical_asset_provenance_role
  on canonical.asset_provenance (provenance_role);

create table if not exists canonical.asset_state (
  asset_state_id text primary key,
  asset_id text not null references canonical.asset (asset_id) on delete cascade,
  state_type text not null,
  effective_start_date date not null,
  effective_end_date date,
  state_payload jsonb not null default '{}'::jsonb,
  source_event_id text references canonical.events (event_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_canonical_asset_state_interval
    check (effective_end_date is null or effective_end_date >= effective_start_date)
);

create index if not exists idx_canonical_asset_state_asset_dates
  on canonical.asset_state (asset_id, effective_start_date, coalesce(effective_end_date, effective_start_date));

create index if not exists idx_canonical_asset_state_type
  on canonical.asset_state (state_type);

create table if not exists canonical.asset_state_provenance (
  asset_state_provenance_id text primary key,
  asset_state_id text not null references canonical.asset_state (asset_state_id) on delete cascade,
  source_record_id text references evidence.source_records (source_record_id) on delete set null,
  claim_id text references evidence.normalized_claims (claim_id) on delete set null,
  override_id text references evidence.overrides (override_id) on delete set null,
  provenance_role text not null,
  fallback_reason text,
  created_at timestamptz not null default now(),
  constraint chk_canonical_asset_state_provenance_support
    check (
      source_record_id is not null
      or claim_id is not null
      or override_id is not null
      or fallback_reason is not null
    )
);

create index if not exists idx_canonical_asset_state_provenance_state
  on canonical.asset_state_provenance (asset_state_id);

create index if not exists idx_canonical_asset_state_provenance_role
  on canonical.asset_state_provenance (provenance_role);

commit;
