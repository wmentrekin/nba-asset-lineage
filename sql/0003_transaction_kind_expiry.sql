-- 10-day contracts expire on their own; the feed records no row for that, so derive emits a
-- synthetic `expiry` transaction ten days after each ten_day signing (unless the player moved
-- again first). This keeps strand continuity truthful without inventing a waiver.
alter table lineage.transaction drop constraint if exists transaction_kind_check;
alter table lineage.transaction add constraint transaction_kind_check
  check (kind in ('baseline','trade','signing','waiver','two_way_signing','two_way_conversion','ten_day','draft_selection','expiry'));
