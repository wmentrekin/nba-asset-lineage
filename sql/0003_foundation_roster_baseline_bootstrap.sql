create table if not exists foundation.roster_baseline_player (
    season text not null,
    team_code text not null,
    player_id text not null references foundation.player(player_id) on delete cascade,
    display_name text not null,
    source_record_id text not null references foundation.source_record(source_record_id) on delete cascade,
    roster_order integer not null,
    nba_player_ref text null,
    birth_date text null,
    position_text text null,
    years_experience integer null,
    primary key (season, team_code, player_id)
);

create index if not exists roster_baseline_player_order_idx
on foundation.roster_baseline_player (season, team_code, roster_order);
