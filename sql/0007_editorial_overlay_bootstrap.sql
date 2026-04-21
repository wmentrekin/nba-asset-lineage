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
  editorial_build_id text not null references editorial.builds (editorial_build_id) on delete cascade,
  annotation_id text not null,
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
    check (priority >= 0),
  primary key (editorial_build_id, annotation_id)
);

create index if not exists idx_editorial_annotations_build_date
  on editorial.annotations (editorial_build_id, start_date, end_date, priority desc, annotation_id);

create index if not exists idx_editorial_annotations_event
  on editorial.annotations (event_id);

create index if not exists idx_editorial_annotations_asset
  on editorial.annotations (asset_id);

create table if not exists editorial.calendar_markers (
  editorial_build_id text not null references editorial.builds (editorial_build_id) on delete cascade,
  calendar_marker_id text not null,
  marker_type text not null,
  label text not null,
  marker_date date not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (editorial_build_id, calendar_marker_id)
);

create index if not exists idx_editorial_calendar_markers_build_date
  on editorial.calendar_markers (editorial_build_id, marker_date, calendar_marker_id);

create table if not exists editorial.game_overlays (
  editorial_build_id text not null references editorial.builds (editorial_build_id) on delete cascade,
  game_overlay_id text not null,
  game_date date not null,
  opponent text not null,
  home_away text not null,
  result text not null,
  score_display text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (editorial_build_id, game_overlay_id)
);

create index if not exists idx_editorial_game_overlays_build_date
  on editorial.game_overlays (editorial_build_id, game_date, game_overlay_id);

create table if not exists editorial.eras (
  editorial_build_id text not null references editorial.builds (editorial_build_id) on delete cascade,
  era_id text not null,
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
    check (priority >= 0),
  primary key (editorial_build_id, era_id)
);

create index if not exists idx_editorial_eras_build_date
  on editorial.eras (editorial_build_id, start_date, end_date, priority desc, era_id);

create table if not exists editorial.story_chapters (
  editorial_build_id text not null references editorial.builds (editorial_build_id) on delete cascade,
  story_chapter_id text not null,
  slug text not null,
  chapter_order integer not null,
  title text not null,
  body text not null,
  start_date date not null,
  end_date date not null,
  era_id text,
  focus_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_editorial_story_chapter_interval
    check (end_date >= start_date),
  primary key (editorial_build_id, story_chapter_id)
);

create index if not exists idx_editorial_story_chapters_build_order
  on editorial.story_chapters (editorial_build_id, chapter_order, start_date, story_chapter_id);

create index if not exists idx_editorial_story_chapters_era
  on editorial.story_chapters (era_id);

alter table if exists editorial.annotations
  add column if not exists editorial_build_id text;
alter table if exists editorial.calendar_markers
  add column if not exists editorial_build_id text;
alter table if exists editorial.game_overlays
  add column if not exists editorial_build_id text;
alter table if exists editorial.eras
  add column if not exists editorial_build_id text;
alter table if exists editorial.story_chapters
  add column if not exists editorial_build_id text;

do $$
begin
  if exists (select 1 from editorial.builds) then
    update editorial.annotations
    set editorial_build_id = coalesce(
      editorial_build_id,
      (select editorial_build_id from editorial.builds order by built_at desc, editorial_build_id desc limit 1)
    )
    where editorial_build_id is null;
    update editorial.calendar_markers
    set editorial_build_id = coalesce(
      editorial_build_id,
      (select editorial_build_id from editorial.builds order by built_at desc, editorial_build_id desc limit 1)
    )
    where editorial_build_id is null;
    update editorial.game_overlays
    set editorial_build_id = coalesce(
      editorial_build_id,
      (select editorial_build_id from editorial.builds order by built_at desc, editorial_build_id desc limit 1)
    )
    where editorial_build_id is null;
    update editorial.eras
    set editorial_build_id = coalesce(
      editorial_build_id,
      (select editorial_build_id from editorial.builds order by built_at desc, editorial_build_id desc limit 1)
    )
    where editorial_build_id is null;
    update editorial.story_chapters
    set editorial_build_id = coalesce(
      editorial_build_id,
      (select editorial_build_id from editorial.builds order by built_at desc, editorial_build_id desc limit 1)
    )
    where editorial_build_id is null;
  end if;
end $$;

alter table if exists editorial.annotations
  alter column editorial_build_id set not null;
alter table if exists editorial.calendar_markers
  alter column editorial_build_id set not null;
alter table if exists editorial.game_overlays
  alter column editorial_build_id set not null;
alter table if exists editorial.eras
  alter column editorial_build_id set not null;
alter table if exists editorial.story_chapters
  alter column editorial_build_id set not null;

alter table if exists editorial.annotations
  drop constraint if exists annotations_pkey;
alter table if exists editorial.calendar_markers
  drop constraint if exists calendar_markers_pkey;
alter table if exists editorial.game_overlays
  drop constraint if exists game_overlays_pkey;
alter table if exists editorial.eras
  drop constraint if exists eras_pkey;
alter table if exists editorial.story_chapters
  drop constraint if exists story_chapters_pkey;
alter table if exists editorial.story_chapters
  drop constraint if exists story_chapters_chapter_order_key;
alter table if exists editorial.story_chapters
  drop constraint if exists story_chapters_era_id_fkey;
alter table if exists editorial.story_chapters
  drop constraint if exists fk_editorial_story_chapters_era;

alter table if exists editorial.annotations
  add primary key (editorial_build_id, annotation_id);
alter table if exists editorial.calendar_markers
  add primary key (editorial_build_id, calendar_marker_id);
alter table if exists editorial.game_overlays
  add primary key (editorial_build_id, game_overlay_id);
alter table if exists editorial.eras
  add primary key (editorial_build_id, era_id);
alter table if exists editorial.story_chapters
  add primary key (editorial_build_id, story_chapter_id);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'story_chapters_build_order_key'
      and conrelid = 'editorial.story_chapters'::regclass
  ) then
    alter table editorial.story_chapters
      add constraint story_chapters_build_order_key unique (editorial_build_id, chapter_order);
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'fk_editorial_story_chapters_era'
      and conrelid = 'editorial.story_chapters'::regclass
  ) then
    alter table editorial.story_chapters
      add constraint fk_editorial_story_chapters_era
      foreign key (editorial_build_id, era_id)
      references editorial.eras (editorial_build_id, era_id)
      on delete restrict;
  end if;
end $$;

commit;
