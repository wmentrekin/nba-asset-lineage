-- Stage 4 pick lifecycle bootstrap.
-- Adds pick continuity tables on top of the existing Stage 2 canonical event
-- schema and Stage 3 player tenure / asset schema.

begin;

create schema if not exists canonical;

create table if not exists canonical.pick_asset (
  pick_asset_id text primary key,
  origin_team_code text not null,
  draft_year integer not null,
  draft_round integer not null,
  protection_summary text,
  protection_payload jsonb not null default '{}'::jsonb,
  drafted_player_id text references canonical.player_identity (player_id) on delete set null,
  current_pick_stage text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_canonical_pick_asset_stage
    check (current_pick_stage in ('future_pick', 'resolved_pick', 'drafted_player', 'conveyed_away')),
  constraint chk_canonical_pick_asset_identity
    check (origin_team_code <> '' and draft_year > 0 and draft_round > 0)
);

create index if not exists idx_canonical_pick_asset_stage
  on canonical.pick_asset (current_pick_stage);

create index if not exists idx_canonical_pick_asset_year_team
  on canonical.pick_asset (draft_year, origin_team_code, draft_round);

create table if not exists canonical.pick_asset_provenance (
  pick_asset_provenance_id text primary key,
  pick_asset_id text not null references canonical.pick_asset (pick_asset_id) on delete cascade,
  source_record_id text references evidence.source_records (source_record_id) on delete set null,
  claim_id text references evidence.normalized_claims (claim_id) on delete set null,
  override_id text references evidence.overrides (override_id) on delete set null,
  provenance_role text not null,
  fallback_reason text,
  created_at timestamptz not null default now(),
  constraint chk_canonical_pick_asset_provenance_support
    check (
      source_record_id is not null
      or claim_id is not null
      or override_id is not null
      or fallback_reason is not null
    )
);

create index if not exists idx_canonical_pick_asset_provenance_pick
  on canonical.pick_asset_provenance (pick_asset_id);

create index if not exists idx_canonical_pick_asset_provenance_role
  on canonical.pick_asset_provenance (provenance_role);

create table if not exists canonical.pick_resolution (
  pick_resolution_id text primary key,
  pick_asset_id text not null references canonical.pick_asset (pick_asset_id) on delete cascade,
  state_type text not null,
  effective_start_date date not null,
  effective_end_date date,
  overall_pick_number integer,
  lottery_context text,
  drafted_player_id text references canonical.player_identity (player_id) on delete set null,
  source_event_id text references canonical.events (event_id) on delete set null,
  state_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_canonical_pick_resolution_interval
    check (effective_end_date is null or effective_end_date >= effective_start_date),
  constraint chk_canonical_pick_resolution_state
    check (state_type in ('future_pick', 'resolved_pick', 'drafted_player', 'conveyed_away'))
);

create index if not exists idx_canonical_pick_resolution_pick_dates
  on canonical.pick_resolution (pick_asset_id, effective_start_date, coalesce(effective_end_date, effective_start_date));

create index if not exists idx_canonical_pick_resolution_state_type
  on canonical.pick_resolution (state_type);

create table if not exists canonical.pick_resolution_provenance (
  pick_resolution_provenance_id text primary key,
  pick_resolution_id text not null references canonical.pick_resolution (pick_resolution_id) on delete cascade,
  source_record_id text references evidence.source_records (source_record_id) on delete set null,
  claim_id text references evidence.normalized_claims (claim_id) on delete set null,
  override_id text references evidence.overrides (override_id) on delete set null,
  provenance_role text not null,
  fallback_reason text,
  created_at timestamptz not null default now(),
  constraint chk_canonical_pick_resolution_provenance_support
    check (
      source_record_id is not null
      or claim_id is not null
      or override_id is not null
      or fallback_reason is not null
    )
);

create index if not exists idx_canonical_pick_resolution_provenance_resolution
  on canonical.pick_resolution_provenance (pick_resolution_id);

create index if not exists idx_canonical_pick_resolution_provenance_role
  on canonical.pick_resolution_provenance (provenance_role);

commit;
