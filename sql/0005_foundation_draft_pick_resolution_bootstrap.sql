create table if not exists foundation.draft_pick_resolution (
    draft_pick_resolution_id text primary key,
    draft_selection_id text not null references foundation.draft_selection(draft_selection_id) on delete cascade,
    pick_id text not null references foundation.pick(pick_id) on delete cascade,
    pick_asset_id text not null references foundation.asset(asset_id) on delete cascade,
    player_id text not null references foundation.player(player_id) on delete cascade,
    player_asset_id text not null references foundation.asset(asset_id) on delete cascade,
    draft_year integer not null,
    round_number integer not null,
    pick_overall integer not null,
    team_code text not null,
    resolution_status text not null,
    confidence text not null,
    source_bundle_id text not null,
    source_locator text null,
    notes text null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint draft_pick_resolution_status_check check (
        resolution_status in ('slot_verified')
    ),
    constraint draft_pick_resolution_confidence_check check (
        confidence in ('high', 'medium', 'low', 'none')
    )
);

create unique index if not exists draft_pick_resolution_selection_idx
on foundation.draft_pick_resolution (draft_selection_id);

create unique index if not exists draft_pick_resolution_pick_idx
on foundation.draft_pick_resolution (pick_id);

create unique index if not exists draft_pick_resolution_slot_idx
on foundation.draft_pick_resolution (draft_year, pick_overall);
