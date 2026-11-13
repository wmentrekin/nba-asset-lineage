-- A new draft year becomes tradeable the day after each draft (7-year horizon): derive adds
-- Memphis's own picks for that year through a `pick_horizon` transaction.
alter table lineage.transaction drop constraint if exists transaction_kind_check;
alter table lineage.transaction add constraint transaction_kind_check
  check (kind in ('baseline','trade','signing','waiver','two_way_signing','two_way_conversion','ten_day','draft_selection','expiry','contract_void','pick_horizon'));
