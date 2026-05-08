create schema if not exists foundation;

create table if not exists foundation.source_record (
    source_record_id text primary key,
    source_system text not null,
    source_type text not null,
    source_locator text null,
    fetched_at timestamptz not null,
    raw_payload jsonb not null
);

create table if not exists foundation.source_event (
    source_event_id text primary key,
    source_record_id text not null references foundation.source_record(source_record_id) on delete cascade,
    event_date date not null,
    event_type text not null,
    label text not null,
    team_scope text not null,
    source_group_hint text null,
    normalized_payload jsonb not null,
    constraint source_event_type_check check (
        event_type in ('trade', 'draft', 'waiver', 'signing', 're_signing', 'extension', 'conversion', 'release')
    )
);

create table if not exists foundation.player (
    player_id text primary key,
    display_name text not null,
    nba_player_ref text null,
    birth_date text null,
    position_text text null
);

create table if not exists foundation.pick (
    pick_id text primary key,
    draft_year integer not null,
    round_number integer not null,
    original_team text null,
    protection_text text null,
    swap_text text null,
    resolution_status text null,
    raw_text text not null
);

create table if not exists foundation.asset (
    asset_id text primary key,
    asset_kind text not null,
    player_id text null references foundation.player(player_id) on delete cascade,
    pick_id text null references foundation.pick(pick_id) on delete cascade,
    start_source_event_id text null references foundation.source_event(source_event_id) on delete set null,
    end_source_event_id text null references foundation.source_event(source_event_id) on delete set null,
    constraint asset_kind_check check (asset_kind in ('player', 'pick')),
    constraint asset_pointer_check check (
        (asset_kind = 'player' and player_id is not null and pick_id is null)
        or
        (asset_kind = 'pick' and pick_id is not null and player_id is null)
    )
);

create index if not exists source_event_event_date_idx on foundation.source_event (event_date);
create index if not exists source_event_group_hint_idx on foundation.source_event (source_group_hint);
create index if not exists asset_player_idx on foundation.asset (player_id);
create index if not exists asset_pick_idx on foundation.asset (pick_id);
