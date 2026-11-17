-- Lock the lineage tables to the anon/authenticated API roles. The pipeline connects as
-- postgres (bypassrls), so no policies are needed for it to keep working.
alter table lineage.source_record enable row level security;
alter table lineage.player enable row level security;
alter table lineage.pick enable row level security;
alter table lineage.transaction enable row level security;
alter table lineage.asset_movement enable row level security;

-- Free-text derive notes, e.g. "draft consideration: picks not yet curated", so validate can
-- cross-check feed draft-consideration legs against curated pick movements from the DB alone.
alter table lineage.transaction add column if not exists note text;
