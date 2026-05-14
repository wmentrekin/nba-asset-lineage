create table if not exists foundation.player_alias (
    alias_id text primary key,
    player_id text not null references foundation.player(player_id) on delete cascade,
    source_system text not null,
    alias_name text not null,
    normalized_alias_name text not null,
    is_manual boolean not null default false,
    notes text null
);

create unique index if not exists player_alias_source_name_idx
on foundation.player_alias (source_system, normalized_alias_name);

create table if not exists foundation.roster_snapshot (
    snapshot_id text primary key,
    snapshot_date date not null,
    snapshot_kind text not null,
    season text not null,
    team_code text not null,
    source_record_id text null references foundation.source_record(source_record_id) on delete set null,
    notes text null,
    constraint roster_snapshot_kind_check check (
        snapshot_kind in ('season_opening', 'season_closing', 'post_draft', 'post_deadline')
    )
);

create table if not exists foundation.roster_snapshot_player (
    snapshot_id text not null references foundation.roster_snapshot(snapshot_id) on delete cascade,
    player_id text not null references foundation.player(player_id) on delete cascade,
    asset_id text null references foundation.asset(asset_id) on delete set null,
    roster_status text not null,
    depth_order integer null,
    is_two_way boolean not null default false,
    is_standard_contract boolean not null default true,
    primary key (snapshot_id, player_id),
    constraint roster_snapshot_player_status_check check (
        roster_status in ('standard', 'two_way', 'non_roster')
    )
);

create table if not exists foundation.roster_snapshot_pick (
    snapshot_id text not null references foundation.roster_snapshot(snapshot_id) on delete cascade,
    pick_id text not null references foundation.pick(pick_id) on delete cascade,
    asset_id text null references foundation.asset(asset_id) on delete set null,
    holding_status text not null default 'owned',
    display_order integer null,
    source_obligation_id text null,
    confidence text not null default 'derived',
    notes text null,
    primary key (snapshot_id, pick_id),
    constraint roster_snapshot_pick_holding_status_check check (
        holding_status in ('owned', 'owed_out', 'swap_right', 'encumbered', 'conditional')
    ),
    constraint roster_snapshot_pick_confidence_check check (
        confidence in ('derived', 'curated', 'validated', 'uncertain')
    )
);

create table if not exists foundation.draft_selection (
    draft_selection_id text primary key,
    draft_year integer not null,
    pick_overall integer not null,
    round_number integer not null,
    team_code text not null,
    player_id text not null references foundation.player(player_id) on delete cascade,
    pick_id text null references foundation.pick(pick_id) on delete set null,
    source_event_id text null references foundation.source_event(source_event_id) on delete set null,
    notes text null
);

create unique index if not exists draft_selection_year_overall_idx
on foundation.draft_selection (draft_year, pick_overall);

create table if not exists foundation.draft_lottery_result (
    lottery_result_id text primary key,
    draft_year integer not null,
    lottery_date date null,
    team_code text not null,
    owner_team_code text null,
    original_team_code text null,
    lottery_position integer null,
    result_pick_slot integer not null,
    pre_lottery_odds text null,
    notes text null
);

create unique index if not exists draft_lottery_result_year_team_idx
on foundation.draft_lottery_result (draft_year, team_code);

create index if not exists draft_lottery_result_year_owner_idx
on foundation.draft_lottery_result (draft_year, owner_team_code);

create index if not exists draft_lottery_result_year_original_idx
on foundation.draft_lottery_result (draft_year, original_team_code);
