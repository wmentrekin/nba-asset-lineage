create table if not exists foundation.pick_inventory_obligation (
    obligation_id text primary key,
    effective_date date not null,
    perspective_team_code text not null,
    owner_team_code text not null,
    original_team_code text not null,
    draft_year integer not null,
    round_number integer not null,
    direction text not null,
    holding_status text not null,
    obligation_type text not null,
    confidence text not null,
    source_urls text[] not null default '{}'::text[],
    source_labels text[] not null default '{}'::text[],
    retrieved_at timestamptz not null,
    source_event_id text null,
    canonical_event_id text null,
    protection_text text null,
    swap_text text null,
    condition_text text null,
    notes text null,
    loadable boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pick_inventory_obligation_source_event_fk foreign key (source_event_id)
        references foundation.source_event(source_event_id) on delete set null,
    constraint pick_inventory_obligation_canonical_event_fk foreign key (canonical_event_id)
        references foundation.canonical_event(canonical_event_id) on delete set null,
    constraint pick_inventory_obligation_draft_year_check check (
        draft_year between 1947 and 2100
    ),
    constraint pick_inventory_obligation_round_check check (
        round_number in (1, 2)
    ),
    constraint pick_inventory_obligation_direction_check check (
        direction in ('incoming', 'outgoing', 'own', 'swap_right', 'swap_obligation')
    ),
    constraint pick_inventory_obligation_holding_status_check check (
        holding_status in ('owned', 'owed_out', 'swap_right', 'encumbered', 'conditional')
    ),
    constraint pick_inventory_obligation_type_check check (
        obligation_type in ('own_pick', 'traded_pick', 'swap', 'conditional_fallback')
    ),
    constraint pick_inventory_obligation_confidence_check check (
        confidence in ('derived', 'curated', 'validated', 'uncertain')
    ),
    constraint pick_inventory_obligation_sources_check check (
        cardinality(source_urls) > 0
        and cardinality(source_labels) > 0
        and cardinality(source_urls) = cardinality(source_labels)
    )
);

alter table foundation.pick_inventory_obligation
    add column if not exists obligation_id text;

alter table foundation.pick_inventory_obligation
    add column if not exists effective_date date;

alter table foundation.pick_inventory_obligation
    add column if not exists perspective_team_code text;

alter table foundation.pick_inventory_obligation
    add column if not exists owner_team_code text;

alter table foundation.pick_inventory_obligation
    add column if not exists original_team_code text;

alter table foundation.pick_inventory_obligation
    add column if not exists draft_year integer;

alter table foundation.pick_inventory_obligation
    add column if not exists round_number integer;

alter table foundation.pick_inventory_obligation
    add column if not exists direction text;

alter table foundation.pick_inventory_obligation
    add column if not exists holding_status text;

alter table foundation.pick_inventory_obligation
    add column if not exists obligation_type text;

alter table foundation.pick_inventory_obligation
    add column if not exists confidence text;

alter table foundation.pick_inventory_obligation
    add column if not exists source_urls text[] not null default '{}'::text[];

alter table foundation.pick_inventory_obligation
    add column if not exists source_labels text[] not null default '{}'::text[];

alter table foundation.pick_inventory_obligation
    add column if not exists retrieved_at timestamptz;

alter table foundation.pick_inventory_obligation
    add column if not exists source_event_id text;

alter table foundation.pick_inventory_obligation
    add column if not exists canonical_event_id text;

alter table foundation.pick_inventory_obligation
    add column if not exists protection_text text;

alter table foundation.pick_inventory_obligation
    add column if not exists swap_text text;

alter table foundation.pick_inventory_obligation
    add column if not exists condition_text text;

alter table foundation.pick_inventory_obligation
    add column if not exists notes text;

alter table foundation.pick_inventory_obligation
    add column if not exists loadable boolean not null default true;

alter table foundation.pick_inventory_obligation
    add column if not exists created_at timestamptz not null default now();

alter table foundation.pick_inventory_obligation
    add column if not exists updated_at timestamptz not null default now();

alter table foundation.roster_snapshot_pick
    add column if not exists source_obligation_id text null;

alter table foundation.roster_snapshot_pick
    add column if not exists confidence text null;

alter table foundation.roster_snapshot_pick
    alter column confidence set default 'derived';

alter table foundation.roster_snapshot_pick
    add column if not exists notes text null;

alter table foundation.draft_lottery_result
    add column if not exists owner_team_code text null;

alter table foundation.draft_lottery_result
    add column if not exists original_team_code text null;

alter table foundation.pick
    add column if not exists pick_overall integer null;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'pick_inventory_obligation_source_event_fk'
          and conrelid = 'foundation.pick_inventory_obligation'::regclass
    ) then
        alter table foundation.pick_inventory_obligation
            add constraint pick_inventory_obligation_source_event_fk
            foreign key (source_event_id)
            references foundation.source_event(source_event_id)
            on delete set null
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'pick_inventory_obligation_canonical_event_fk'
          and conrelid = 'foundation.pick_inventory_obligation'::regclass
    ) then
        alter table foundation.pick_inventory_obligation
            add constraint pick_inventory_obligation_canonical_event_fk
            foreign key (canonical_event_id)
            references foundation.canonical_event(canonical_event_id)
            on delete set null
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'pick_inventory_obligation_draft_year_check'
          and conrelid = 'foundation.pick_inventory_obligation'::regclass
    ) then
        alter table foundation.pick_inventory_obligation
            add constraint pick_inventory_obligation_draft_year_check
            check (draft_year between 1947 and 2100)
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'pick_inventory_obligation_round_check'
          and conrelid = 'foundation.pick_inventory_obligation'::regclass
    ) then
        alter table foundation.pick_inventory_obligation
            add constraint pick_inventory_obligation_round_check
            check (round_number in (1, 2))
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'pick_inventory_obligation_direction_check'
          and conrelid = 'foundation.pick_inventory_obligation'::regclass
    ) then
        alter table foundation.pick_inventory_obligation
            add constraint pick_inventory_obligation_direction_check
            check (direction in ('incoming', 'outgoing', 'own', 'swap_right', 'swap_obligation'))
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'pick_inventory_obligation_holding_status_check'
          and conrelid = 'foundation.pick_inventory_obligation'::regclass
    ) then
        alter table foundation.pick_inventory_obligation
            add constraint pick_inventory_obligation_holding_status_check
            check (holding_status in ('owned', 'owed_out', 'swap_right', 'encumbered', 'conditional'))
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'pick_inventory_obligation_type_check'
          and conrelid = 'foundation.pick_inventory_obligation'::regclass
    ) then
        alter table foundation.pick_inventory_obligation
            add constraint pick_inventory_obligation_type_check
            check (obligation_type in ('own_pick', 'traded_pick', 'swap', 'conditional_fallback'))
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'pick_inventory_obligation_confidence_check'
          and conrelid = 'foundation.pick_inventory_obligation'::regclass
    ) then
        alter table foundation.pick_inventory_obligation
            add constraint pick_inventory_obligation_confidence_check
            check (confidence in ('derived', 'curated', 'validated', 'uncertain'))
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'pick_inventory_obligation_sources_check'
          and conrelid = 'foundation.pick_inventory_obligation'::regclass
    ) then
        alter table foundation.pick_inventory_obligation
            add constraint pick_inventory_obligation_sources_check
            check (
                cardinality(source_urls) > 0
                and cardinality(source_labels) > 0
                and cardinality(source_urls) = cardinality(source_labels)
            )
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'roster_snapshot_pick_source_obligation_fk'
          and conrelid = 'foundation.roster_snapshot_pick'::regclass
    ) then
        alter table foundation.roster_snapshot_pick
            add constraint roster_snapshot_pick_source_obligation_fk
            foreign key (source_obligation_id)
            references foundation.pick_inventory_obligation(obligation_id)
            on delete set null
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'roster_snapshot_pick_holding_status_check'
          and conrelid = 'foundation.roster_snapshot_pick'::regclass
    ) then
        alter table foundation.roster_snapshot_pick
            add constraint roster_snapshot_pick_holding_status_check
            check (holding_status in ('owned', 'owed_out', 'swap_right', 'encumbered', 'conditional'))
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'roster_snapshot_pick_confidence_check'
          and conrelid = 'foundation.roster_snapshot_pick'::regclass
    ) then
        alter table foundation.roster_snapshot_pick
            add constraint roster_snapshot_pick_confidence_check
            check (confidence is null or confidence in ('derived', 'curated', 'validated', 'uncertain'))
            not valid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'pick_pick_overall_check'
          and conrelid = 'foundation.pick'::regclass
    ) then
        alter table foundation.pick
            add constraint pick_pick_overall_check
            check (pick_overall is null or pick_overall > 0)
            not valid;
    end if;
end $$;

create index if not exists pick_inventory_obligation_effective_idx
on foundation.pick_inventory_obligation (perspective_team_code, effective_date, obligation_id);

create index if not exists pick_inventory_obligation_slot_idx
on foundation.pick_inventory_obligation (draft_year, round_number, original_team_code);

create index if not exists pick_inventory_obligation_owner_idx
on foundation.pick_inventory_obligation (owner_team_code, draft_year, round_number);

create index if not exists pick_inventory_obligation_source_event_idx
on foundation.pick_inventory_obligation (source_event_id);

create index if not exists pick_inventory_obligation_canonical_event_idx
on foundation.pick_inventory_obligation (canonical_event_id);

create index if not exists roster_snapshot_pick_source_obligation_idx
on foundation.roster_snapshot_pick (source_obligation_id);

create index if not exists roster_snapshot_pick_holding_status_idx
on foundation.roster_snapshot_pick (holding_status);

create index if not exists draft_lottery_result_year_owner_idx
on foundation.draft_lottery_result (draft_year, owner_team_code);

create index if not exists draft_lottery_result_year_original_idx
on foundation.draft_lottery_result (draft_year, original_team_code);

create index if not exists pick_year_pick_overall_idx
on foundation.pick (draft_year, pick_overall)
where pick_overall is not null;
