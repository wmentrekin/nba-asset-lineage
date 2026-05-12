create table if not exists foundation.canonical_event (
    canonical_event_id text primary key,
    event_date date not null,
    event_type text not null,
    label text not null,
    sequence_on_date integer not null,
    is_grouped_event boolean not null default false,
    constraint canonical_event_type_check check (
        event_type in ('trade', 'draft', 'waiver', 'signing')
    )
);

create table if not exists foundation.canonical_event_member (
    canonical_event_id text not null references foundation.canonical_event(canonical_event_id) on delete cascade,
    source_event_id text not null references foundation.source_event(source_event_id) on delete cascade,
    primary key (canonical_event_id, source_event_id)
);

create table if not exists foundation.event_asset_transition (
    transition_id text primary key,
    canonical_event_id text not null references foundation.canonical_event(canonical_event_id) on delete cascade,
    asset_id text not null references foundation.asset(asset_id) on delete cascade,
    transition_type text not null,
    direction text not null,
    constraint event_asset_transition_type_check check (
        transition_type in ('acquired', 'departed')
    ),
    constraint event_asset_transition_direction_check check (
        direction in ('in', 'out')
    )
);

create index if not exists canonical_event_event_date_idx on foundation.canonical_event (event_date, sequence_on_date);
create index if not exists canonical_event_member_source_event_idx on foundation.canonical_event_member (source_event_id);
create index if not exists event_asset_transition_canonical_event_idx on foundation.event_asset_transition (canonical_event_id);
create index if not exists event_asset_transition_asset_idx on foundation.event_asset_transition (asset_id);
