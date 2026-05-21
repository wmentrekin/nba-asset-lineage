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

create table if not exists foundation.roster_snapshot_validation (
    snapshot_id text primary key references foundation.roster_snapshot(snapshot_id) on delete cascade,
    validation_scope text not null default 'season_reference',
    validation_status text not null,
    reference_source_record_id text null references foundation.source_record(source_record_id) on delete set null,
    snapshot_player_count integer not null default 0,
    reference_player_count integer null,
    matched_player_count integer not null default 0,
    notes text null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint roster_snapshot_validation_scope_check check (
        validation_scope in ('season_reference')
    ),
    constraint roster_snapshot_validation_status_check check (
        validation_status in ('source_missing', 'season_reference_backed', 'season_reference_incomplete')
    ),
    constraint roster_snapshot_validation_source_state_check check (
        (
            validation_status = 'source_missing'
            and reference_source_record_id is null
            and reference_player_count is null
            and matched_player_count = 0
        )
        or (
            validation_status in ('season_reference_backed', 'season_reference_incomplete')
            and reference_source_record_id is not null
            and reference_player_count is not null
        )
    ),
    constraint roster_snapshot_validation_snapshot_player_count_check check (
        snapshot_player_count >= 0
    ),
    constraint roster_snapshot_validation_reference_player_count_check check (
        reference_player_count is null or reference_player_count >= 0
    ),
    constraint roster_snapshot_validation_matched_player_count_check check (
        matched_player_count >= 0
        and matched_player_count <= snapshot_player_count
        and (reference_player_count is null or matched_player_count <= reference_player_count)
    ),
    constraint roster_snapshot_validation_match_state_check check (
        (
            validation_status = 'source_missing'
            and matched_player_count = 0
        )
        or (
            validation_status = 'season_reference_backed'
            and matched_player_count = snapshot_player_count
        )
        or (
            validation_status = 'season_reference_incomplete'
            and matched_player_count < snapshot_player_count
        )
    )
);

create index if not exists roster_snapshot_validation_status_idx
on foundation.roster_snapshot_validation (validation_scope, validation_status);

create index if not exists roster_snapshot_validation_source_record_idx
on foundation.roster_snapshot_validation (reference_source_record_id);

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
