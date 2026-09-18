-- A contract voided outside the normal transaction feed (e.g. a player's death) is its own
-- kind so the data stays truthful; it renders like a waiver. A drafted-but-unsigned player is
-- held as draft_rights until a signing node changes the contract type.
alter table lineage.transaction drop constraint if exists transaction_kind_check;
alter table lineage.transaction add constraint transaction_kind_check
  check (kind in ('baseline','trade','signing','waiver','two_way_signing','two_way_conversion','ten_day','draft_selection','expiry','contract_void'));
alter table lineage.asset_movement drop constraint if exists asset_movement_contract_type_check;
alter table lineage.asset_movement add constraint asset_movement_contract_type_check
  check (contract_type in ('standard','two_way','ten_day','draft_rights'));
