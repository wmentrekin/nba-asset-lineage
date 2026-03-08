-- Data-only reset for iterative development.
-- Keeps schema objects and static lookup tables intact.

begin;

truncate table
  silver.event_asset_lineage,
  silver.assets,
  silver.events,
  bronze.raw_event_asset_links,
  bronze.raw_assets,
  bronze.raw_events,
  bronze.ingest_runs
restart identity;

commit;
