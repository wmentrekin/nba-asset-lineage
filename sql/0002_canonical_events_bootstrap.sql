-- Stage 2 canonical event bootstrap.
-- Creates canonical event and provenance tables without entering asset modeling.

begin;

create schema if not exists canonical;

create table if not exists canonical.builds (
  canonical_build_id text primary key,
  built_at timestamptz not null default now(),
  builder_version text not null,
  evidence_build_id text,
  override_snapshot_hash text,
  notes text
);

create index if not exists idx_canonical_builds_built_at
  on canonical.builds (built_at desc);

create table if not exists canonical.events (
  event_id text primary key,
  event_type text not null,
  event_date date not null,
  event_order integer not null,
  event_label text not null,
  description text,
  transaction_group_key text,
  is_compound boolean not null default false,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists uq_canonical_events_same_day_order
  on canonical.events (event_date, event_order);

create index if not exists idx_canonical_events_date_type
  on canonical.events (event_date, event_type);

create index if not exists idx_canonical_events_group_key
  on canonical.events (transaction_group_key);

create table if not exists canonical.event_provenance (
  event_provenance_id text primary key,
  event_id text not null references canonical.events (event_id) on delete cascade,
  source_record_id text references evidence.source_records (source_record_id) on delete set null,
  claim_id text references evidence.normalized_claims (claim_id) on delete set null,
  override_id text references evidence.overrides (override_id) on delete set null,
  provenance_role text not null,
  fallback_reason text,
  created_at timestamptz not null default now(),
  constraint chk_canonical_event_provenance_support
    check (
      source_record_id is not null
      or claim_id is not null
      or override_id is not null
      or fallback_reason is not null
    )
);

create index if not exists idx_canonical_event_provenance_event
  on canonical.event_provenance (event_id);

create index if not exists idx_canonical_event_provenance_role
  on canonical.event_provenance (provenance_role);

commit;
