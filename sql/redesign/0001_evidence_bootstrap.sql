-- Stage 1 evidence bootstrap.
-- Creates the redesigned evidence schema without touching legacy Bronze/Silver
-- objects or any canonical/provenance tables.

begin;

create schema if not exists evidence;

-- ---------------------------------------------------------------------------
-- Evidence source capture
-- ---------------------------------------------------------------------------

create table if not exists evidence.source_records (
  source_record_id text primary key,
  source_system text not null,
  source_type text not null,
  source_locator text not null,
  source_url text,
  captured_at timestamptz not null default now(),
  raw_payload jsonb not null default '{}'::jsonb,
  payload_hash text not null,
  parser_version text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists uq_evidence_source_records_dedupe
  on evidence.source_records (source_system, source_type, source_locator, payload_hash);

create index if not exists idx_evidence_source_records_captured_at
  on evidence.source_records (captured_at desc);

create index if not exists idx_evidence_source_records_source_time
  on evidence.source_records (source_system, source_type, captured_at desc);

create index if not exists idx_evidence_source_records_locator
  on evidence.source_records (source_system, source_type, source_locator);

-- ---------------------------------------------------------------------------
-- Normalized claims
-- ---------------------------------------------------------------------------

create table if not exists evidence.normalized_claims (
  claim_id text primary key,
  source_record_id text not null references evidence.source_records (source_record_id) on delete cascade,
  claim_type text not null,
  claim_subject_type text not null,
  claim_subject_key text not null,
  claim_group_hint text,
  claim_date date,
  source_sequence integer,
  claim_payload jsonb not null default '{}'::jsonb,
  confidence_flag text not null default 'unreviewed',
  normalizer_version text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists uq_evidence_normalized_claims_dedupe
  on evidence.normalized_claims (
    source_record_id,
    claim_type,
    claim_subject_type,
    claim_subject_key,
    claim_group_hint,
    claim_date,
    source_sequence,
    normalizer_version,
    md5(claim_payload::text)
  );

create index if not exists idx_evidence_normalized_claims_source_record
  on evidence.normalized_claims (source_record_id);

create index if not exists idx_evidence_normalized_claims_subject
  on evidence.normalized_claims (claim_subject_type, claim_subject_key);

create index if not exists idx_evidence_normalized_claims_claim_type_date
  on evidence.normalized_claims (claim_type, claim_date, source_sequence);

create index if not exists idx_evidence_normalized_claims_normalizer_version
  on evidence.normalized_claims (normalizer_version);

-- ---------------------------------------------------------------------------
-- Manual overrides
-- ---------------------------------------------------------------------------

create table if not exists evidence.overrides (
  override_id text primary key,
  override_type text not null,
  target_type text not null,
  target_key text not null,
  payload jsonb not null default '{}'::jsonb,
  reason text not null,
  authored_by text not null,
  authored_at timestamptz not null default now(),
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create unique index if not exists uq_evidence_overrides_dedupe
  on evidence.overrides (
    override_type,
    target_type,
    target_key,
    authored_by,
    authored_at,
    md5(payload::text)
  );

create index if not exists idx_evidence_overrides_active_target
  on evidence.overrides (target_type, target_key)
  where is_active;

create index if not exists idx_evidence_overrides_authored_at
  on evidence.overrides (authored_at desc);

create index if not exists idx_evidence_overrides_type_target
  on evidence.overrides (override_type, target_type, target_key);

-- ---------------------------------------------------------------------------
-- Override links
-- ---------------------------------------------------------------------------

create table if not exists evidence.override_links (
  override_link_id text primary key,
  override_id text not null references evidence.overrides (override_id) on delete cascade,
  source_record_id text references evidence.source_records (source_record_id) on delete cascade,
  claim_id text references evidence.normalized_claims (claim_id) on delete cascade,
  created_at timestamptz not null default now(),
  constraint chk_evidence_override_links_target_present
    check (source_record_id is not null or claim_id is not null)
);

create unique index if not exists uq_evidence_override_links_dedupe
  on evidence.override_links (
    override_id,
    coalesce(source_record_id, ''),
    coalesce(claim_id, '')
  );

create index if not exists idx_evidence_override_links_override_id
  on evidence.override_links (override_id);

create index if not exists idx_evidence_override_links_source_record_id
  on evidence.override_links (source_record_id);

create index if not exists idx_evidence_override_links_claim_id
  on evidence.override_links (claim_id);

commit;
