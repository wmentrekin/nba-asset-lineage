create table if not exists foundation.daily_roster_state (
    roster_state_id text primary key,
    state_date date not null,
    season text not null,
    team_code text not null,
    source_record_id text null references foundation.source_record(source_record_id) on delete set null,
    event_count integer not null default 0,
    source_event_ids text[] not null default '{}'::text[],
    player_count integer not null default 0,
    standard_count integer not null default 0,
    two_way_count integer not null default 0,
    derivation_mode text not null,
    notes text null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint daily_roster_state_derivation_mode_check check (
        derivation_mode in ('end_of_day_carry_forward')
    ),
    constraint daily_roster_state_team_date_unique unique (team_code, state_date),
    constraint daily_roster_state_event_count_check check (event_count >= 0),
    constraint daily_roster_state_player_count_check check (
        player_count >= 0
        and standard_count >= 0
        and two_way_count >= 0
        and standard_count + two_way_count = player_count
    )
);

create index if not exists daily_roster_state_team_date_idx
on foundation.daily_roster_state (team_code, state_date);

create index if not exists daily_roster_state_season_idx
on foundation.daily_roster_state (season, state_date);

create table if not exists foundation.daily_roster_state_player (
    roster_state_id text not null references foundation.daily_roster_state(roster_state_id) on delete cascade,
    state_date date not null,
    season text not null,
    team_code text not null,
    player_id text not null references foundation.player(player_id) on delete cascade,
    display_name text not null,
    asset_id text null references foundation.asset(asset_id) on delete set null,
    roster_status text not null,
    roster_order integer null,
    is_two_way boolean not null default false,
    is_standard_contract boolean not null default true,
    primary key (roster_state_id, player_id),
    constraint daily_roster_state_player_status_check check (
        roster_status in ('standard', 'two_way')
    ),
    constraint daily_roster_state_player_contract_check check (
        (roster_status = 'standard' and is_two_way = false and is_standard_contract = true)
        or (roster_status = 'two_way' and is_two_way = true and is_standard_contract = false)
    )
);

create index if not exists daily_roster_state_player_asset_idx
on foundation.daily_roster_state_player (asset_id);

create index if not exists daily_roster_state_player_order_idx
on foundation.daily_roster_state_player (roster_state_id, roster_order);

create table if not exists foundation.draft_prior_owner_lineage (
    draft_prior_owner_lineage_id text primary key,
    draft_selection_id text not null references foundation.draft_selection(draft_selection_id) on delete cascade,
    draft_pick_resolution_id text null references foundation.draft_pick_resolution(draft_pick_resolution_id) on delete set null,
    pick_id text not null references foundation.pick(pick_id) on delete cascade,
    pick_asset_id text not null references foundation.asset(asset_id) on delete cascade,
    player_id text not null references foundation.player(player_id) on delete cascade,
    player_asset_id text null references foundation.asset(asset_id) on delete set null,
    draft_year integer not null,
    round_number integer not null,
    pick_overall integer not null,
    team_code text not null,
    owner_team_code text not null,
    original_team_code text not null,
    source_obligation_id text null references foundation.pick_inventory_obligation(obligation_id) on delete set null,
    resolution_kind text not null,
    confidence text not null,
    notes text null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint draft_prior_owner_lineage_resolution_kind_check check (
        resolution_kind in (
            'resolved_pick_original_team',
            'inventory_exact_pick',
            'inventory_single_candidate',
            'team_default_fallback',
            'curated_override'
        )
    ),
    constraint draft_prior_owner_lineage_confidence_check check (
        confidence in ('high', 'medium', 'low', 'none')
    ),
    constraint draft_prior_owner_lineage_owner_codes_check check (
        owner_team_code <> ''
        and original_team_code <> ''
    )
);

alter table foundation.draft_prior_owner_lineage
drop constraint if exists draft_prior_owner_lineage_resolution_kind_check;

alter table foundation.draft_prior_owner_lineage
add constraint draft_prior_owner_lineage_resolution_kind_check check (
    resolution_kind in (
        'resolved_pick_original_team',
        'inventory_exact_pick',
        'inventory_source_event_exact',
        'inventory_single_candidate',
        'team_default_fallback',
        'curated_override'
    )
);

create unique index if not exists draft_prior_owner_lineage_selection_idx
on foundation.draft_prior_owner_lineage (draft_selection_id);

create unique index if not exists draft_prior_owner_lineage_pick_idx
on foundation.draft_prior_owner_lineage (pick_id);

create index if not exists draft_prior_owner_lineage_obligation_idx
on foundation.draft_prior_owner_lineage (source_obligation_id);

create index if not exists draft_prior_owner_lineage_team_year_idx
on foundation.draft_prior_owner_lineage (team_code, draft_year, round_number, pick_overall);
