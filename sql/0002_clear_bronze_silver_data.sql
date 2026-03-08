-- Data-only reset for iterative development.
-- Keeps schema objects and static lookup tables intact.

begin;

truncate table silver.event_asset_lineage;
truncate table silver.assets;
truncate table silver.events;

truncate table bronze.raw_event_asset_links;
truncate table bronze.raw_assets;
truncate table bronze.raw_events;
truncate table bronze.ingest_runs;

commit;

