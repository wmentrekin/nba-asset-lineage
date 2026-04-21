-- Stage 7 editorial overlay bootstrap.
-- Adds contextual and narrative layers separate from canonical lineage truth.

begin;

create schema if not exists editorial;

create table if not exists editorial.builds (
  editorial_build_id text primary key,
  built_at timestamptz not null default now(),
  builder_version text not null,
  presentation_build_id text references presentation.builds (presentation_build_id) on delete set null,
  notes text
);

create index if not exists idx_editorial_builds_built_at
  on editorial.builds (built_at desc);

create table if not exists editorial.annotations (
  annotation_id text primary key,
  annotation_type text not null,
  title text not null,
  body text not null,
  start_date date not null,
  end_date date not null,
  event_id text references canonical.events (event_id) on delete set null,
  asset_id text references canonical.asset (asset_id) on delete set null,
  priority integer not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_editorial_annotation_interval
    check (end_date >= start_date),
  constraint chk_editorial_annotation_priority
    check (priority >= 0)
);

create index if not exists idx_editorial_annotations_date
  on editorial.annotations (start_date, end_date, priority desc, annotation_id);

create index if not exists idx_editorial_annotations_event
  on editorial.annotations (event_id);

create index if not exists idx_editorial_annotations_asset
  on editorial.annotations (asset_id);

create table if not exists editorial.calendar_markers (
  calendar_marker_id text primary key,
  marker_type text not null,
  label text not null,
  marker_date date not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_editorial_calendar_markers_date
  on editorial.calendar_markers (marker_date, calendar_marker_id);

create table if not exists editorial.game_overlays (
  game_overlay_id text primary key,
  game_date date not null,
  opponent text not null,
  home_away text not null,
  result text not null,
  score_display text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_editorial_game_overlays_date
  on editorial.game_overlays (game_date, game_overlay_id);

create table if not exists editorial.eras (
  era_id text primary key,
  title text not null,
  start_date date not null,
  end_date date not null,
  description text not null,
  priority integer not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_editorial_era_interval
    check (end_date >= start_date),
  constraint chk_editorial_era_priority
    check (priority >= 0)
);

create index if not exists idx_editorial_eras_date
  on editorial.eras (start_date, end_date, priority desc, era_id);

create table if not exists editorial.story_chapters (
  story_chapter_id text primary key,
  slug text not null,
  chapter_order integer not null unique,
  title text not null,
  body text not null,
  start_date date not null,
  end_date date not null,
  era_id text references editorial.eras (era_id) on delete set null,
  focus_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_editorial_story_chapter_interval
    check (end_date >= start_date)
);

create index if not exists idx_editorial_story_chapters_order
  on editorial.story_chapters (chapter_order, start_date, story_chapter_id);

create index if not exists idx_editorial_story_chapters_era
  on editorial.story_chapters (era_id);

commit;
