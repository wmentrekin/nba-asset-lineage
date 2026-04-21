-- Stage 6 presentation contract bootstrap.
-- Adds deterministic frontend-ready timeline nodes, edges, lanes, and
-- presentation build metadata derived from canonical rows.

begin;

create schema if not exists presentation;

create table if not exists presentation.builds (
  presentation_build_id text primary key,
  built_at timestamptz not null default now(),
  builder_version text not null,
  canonical_build_id text references canonical.builds (canonical_build_id) on delete set null,
  notes text
);

create index if not exists idx_presentation_builds_built_at
  on presentation.builds (built_at desc);

create table if not exists presentation.timeline_nodes (
  node_id text primary key,
  event_id text references canonical.events (event_id) on delete set null,
  event_date date not null,
  event_order integer not null,
  node_type text not null,
  label text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint chk_presentation_timeline_node_type
    check (node_type in ('event', 'state_boundary', 'calendar_marker'))
);

create index if not exists idx_presentation_timeline_nodes_order
  on presentation.timeline_nodes (event_date, event_order, node_id);

create index if not exists idx_presentation_timeline_nodes_event
  on presentation.timeline_nodes (event_id);

create table if not exists presentation.asset_lanes (
  asset_lane_id text primary key,
  asset_id text not null references canonical.asset (asset_id) on delete cascade,
  lane_group text not null,
  lane_index integer not null,
  effective_start_date date not null,
  effective_end_date date not null,
  assignment_method text not null,
  created_at timestamptz not null default now(),
  constraint chk_presentation_asset_lane_group
    check (lane_group in ('main_roster', 'two_way', 'future_picks')),
  constraint chk_presentation_asset_lane_index
    check (lane_index >= 0),
  constraint chk_presentation_asset_lane_interval
    check (effective_end_date >= effective_start_date)
);

create index if not exists idx_presentation_asset_lanes_asset
  on presentation.asset_lanes (asset_id);

create index if not exists idx_presentation_asset_lanes_group_index
  on presentation.asset_lanes (lane_group, lane_index, effective_start_date, effective_end_date);

create table if not exists presentation.timeline_edges (
  edge_id text primary key,
  asset_id text not null references canonical.asset (asset_id) on delete cascade,
  source_node_id text not null references presentation.timeline_nodes (node_id) on delete cascade,
  target_node_id text not null references presentation.timeline_nodes (node_id) on delete cascade,
  start_date date not null,
  end_date date not null,
  edge_type text not null,
  lane_group text not null,
  lane_index integer not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint chk_presentation_timeline_edge_type
    check (edge_type in ('player_line', 'pick_line', 'transition_line')),
  constraint chk_presentation_timeline_edge_lane_group
    check (lane_group in ('main_roster', 'two_way', 'future_picks')),
  constraint chk_presentation_timeline_edge_lane_index
    check (lane_index >= 0),
  constraint chk_presentation_timeline_edge_interval
    check (end_date >= start_date)
);

create index if not exists idx_presentation_timeline_edges_asset
  on presentation.timeline_edges (asset_id);

create index if not exists idx_presentation_timeline_edges_nodes
  on presentation.timeline_edges (source_node_id, target_node_id);

create index if not exists idx_presentation_timeline_edges_lane
  on presentation.timeline_edges (lane_group, lane_index, start_date, end_date);

commit;
