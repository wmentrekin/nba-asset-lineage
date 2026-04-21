-- Stage 5 event asset flow bootstrap.
-- Adds the shared event-to-asset flow model on top of the existing Stage 2-4
-- canonical schema.

begin;

create schema if not exists canonical;

create table if not exists canonical.event_asset_flow (
  event_asset_flow_id text primary key,
  event_id text not null references canonical.events (event_id) on delete cascade,
  asset_id text not null references canonical.asset (asset_id) on delete cascade,
  flow_direction text not null,
  flow_role text not null,
  flow_order integer not null,
  effective_date date not null,
  created_at timestamptz not null default now(),
  constraint chk_canonical_event_asset_flow_direction
    check (flow_direction in ('in', 'out')),
  constraint chk_canonical_event_asset_flow_role
    check (
      flow_role in (
        'incoming_player',
        'outgoing_player',
        'incoming_pick',
        'outgoing_pick',
        'pick_consumed',
        'player_emerges'
      )
    )
);

create unique index if not exists uq_canonical_event_asset_flow_event_order
  on canonical.event_asset_flow (event_id, flow_order);

create index if not exists idx_canonical_event_asset_flow_event
  on canonical.event_asset_flow (event_id);

create index if not exists idx_canonical_event_asset_flow_asset
  on canonical.event_asset_flow (asset_id);

create index if not exists idx_canonical_event_asset_flow_role
  on canonical.event_asset_flow (flow_role);

create table if not exists canonical.event_asset_flow_provenance (
  event_asset_flow_provenance_id text primary key,
  event_asset_flow_id text not null references canonical.event_asset_flow (event_asset_flow_id) on delete cascade,
  source_record_id text references evidence.source_records (source_record_id) on delete set null,
  claim_id text references evidence.normalized_claims (claim_id) on delete set null,
  override_id text references evidence.overrides (override_id) on delete set null,
  provenance_role text not null,
  fallback_reason text,
  created_at timestamptz not null default now(),
  constraint chk_canonical_event_asset_flow_provenance_support
    check (
      source_record_id is not null
      or claim_id is not null
      or override_id is not null
      or fallback_reason is not null
    )
);

create index if not exists idx_canonical_event_asset_flow_provenance_flow
  on canonical.event_asset_flow_provenance (event_asset_flow_id);

create index if not exists idx_canonical_event_asset_flow_provenance_role
  on canonical.event_asset_flow_provenance (provenance_role);

commit;
