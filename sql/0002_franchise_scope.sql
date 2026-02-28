-- Extend silver lineage model from Memphis-only to full franchise history
-- Start boundary target: 1995-06-23 (pre-expansion draft)

begin;

-- 1) Events: add franchise + operating team dimensions
alter table silver.events
  add column if not exists franchise_id text,
  add column if not exists operating_team_id text;

update silver.events
set franchise_id = 'grizzlies'
where franchise_id is null;

update silver.events
set operating_team_id = case
  when operating_team_id is not null then operating_team_id
  when team_id is not null and team_id in ('MEM', 'VAN') then team_id
  when event_date < date '2001-07-01' then 'VAN'
  else 'MEM'
end;

alter table silver.events
  alter column franchise_id set default 'grizzlies',
  alter column franchise_id set not null,
  alter column operating_team_id set not null;

-- 2) Assets: carry franchise + operating team timeline in state intervals
alter table silver.assets
  add column if not exists franchise_id text,
  add column if not exists operating_team_id text;

update silver.assets
set franchise_id = 'grizzlies'
where franchise_id is null;

update silver.assets
set operating_team_id = case
  when operating_team_id is not null then operating_team_id
  when owner_team_id in ('MEM', 'VAN') then owner_team_id
  when valid_from_date < date '2001-07-01' then 'VAN'
  else 'MEM'
end;

alter table silver.assets
  alter column franchise_id set default 'grizzlies',
  alter column franchise_id set not null,
  alter column operating_team_id set not null;

-- 3) Lineage: add franchise partition key
alter table silver.event_asset_lineage
  add column if not exists franchise_id text;

update silver.event_asset_lineage l
set franchise_id = e.franchise_id
from silver.events e
where l.event_id = e.event_id
  and l.franchise_id is null;

alter table silver.event_asset_lineage
  alter column franchise_id set default 'grizzlies',
  alter column franchise_id set not null;

-- 4) Franchise team-era mapping table
create table if not exists silver.franchise_team_eras (
  franchise_id text not null,
  operating_team_id text not null,
  team_name text not null,
  era_start date not null,
  era_end date,
  primary key (franchise_id, era_start),
  check (era_end is null or era_end >= era_start)
);

insert into silver.franchise_team_eras (
  franchise_id,
  operating_team_id,
  team_name,
  era_start,
  era_end
) values
  ('grizzlies', 'VAN', 'Vancouver Grizzlies', date '1995-06-23', date '2001-06-30'),
  ('grizzlies', 'MEM', 'Memphis Grizzlies', date '2001-07-01', null)
on conflict (franchise_id, era_start) do nothing;

-- 5) Time and partition indexes
create index if not exists idx_silver_events_franchise_time
  on silver.events (franchise_id, event_date, event_order);

create index if not exists idx_silver_events_operating_team_time
  on silver.events (operating_team_id, event_date, event_order);

create index if not exists idx_silver_assets_franchise_time
  on silver.assets (franchise_id, valid_from_date, asset_id);

create index if not exists idx_silver_assets_operating_team_time
  on silver.assets (operating_team_id, valid_from_date, asset_id);

create index if not exists idx_silver_lineage_franchise_time
  on silver.event_asset_lineage (franchise_id, effective_date, event_id);

commit;
