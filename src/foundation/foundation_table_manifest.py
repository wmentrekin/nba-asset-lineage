"""Closed foundation-table contract used by refresh projection and execution.

Keeping identifiers here (rather than accepting caller supplied table names) is
intentional: a reviewed refresh plan may only affect the reset-era foundation
surfaces below.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FoundationForeignKey:
    """One closed child-to-parent foundation relationship."""

    column: str
    parent_table: str
    parent_column: str


@dataclass(frozen=True)
class FoundationTable:
    name: str
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    alternate_unique_keys: tuple[tuple[str, ...], ...] = ()
    foreign_keys: tuple[FoundationForeignKey, ...] = ()


def _fk(column: str, parent_table: str, parent_column: str) -> FoundationForeignKey:
    return FoundationForeignKey(column, parent_table, parent_column)


def _table(
    name: str,
    columns: tuple[str, ...],
    *keys: str,
    foreign_keys: tuple[FoundationForeignKey, ...] = (),
) -> FoundationTable:
    return FoundationTable(name=name, columns=columns, key_columns=keys, foreign_keys=foreign_keys)


# This is deliberately a closed tuple.  Snapshot/restore and mutation plans
# must not grow a generic "table" input surface.
FOUNDATION_TABLES: tuple[FoundationTable, ...] = (
    _table("source_record", ("source_record_id", "source_system", "source_type", "source_locator", "fetched_at", "raw_payload"), "source_record_id"),
    _table("player", ("player_id", "display_name", "nba_player_ref", "birth_date", "position_text"), "player_id"),
    _table("pick", ("pick_id", "draft_year", "round_number", "original_team", "protection_text", "swap_text", "resolution_status", "raw_text", "pick_overall"), "pick_id"),
    _table("canonical_event", ("canonical_event_id", "event_date", "event_type", "label", "sequence_on_date", "is_grouped_event"), "canonical_event_id"),
    _table("draft_lottery_result", ("lottery_result_id", "draft_year", "lottery_date", "team_code", "owner_team_code", "original_team_code", "lottery_position", "result_pick_slot", "pre_lottery_odds", "notes"), "lottery_result_id"),
    _table("source_event", ("source_event_id", "source_record_id", "event_date", "event_type", "label", "team_scope", "source_group_hint", "normalized_payload"), "source_event_id", foreign_keys=(_fk("source_record_id", "source_record", "source_record_id"),)),
    _table("asset", ("asset_id", "asset_kind", "player_id", "pick_id", "start_source_event_id", "end_source_event_id"), "asset_id", foreign_keys=(_fk("player_id", "player", "player_id"), _fk("pick_id", "pick", "pick_id"), _fk("start_source_event_id", "source_event", "source_event_id"), _fk("end_source_event_id", "source_event", "source_event_id"))),
    _table("player_alias", ("alias_id", "player_id", "source_system", "alias_name", "normalized_alias_name", "is_manual", "notes"), "alias_id", foreign_keys=(_fk("player_id", "player", "player_id"),)),
    _table("roster_baseline_player", ("season", "team_code", "player_id", "display_name", "source_record_id", "roster_order", "nba_player_ref", "birth_date", "position_text", "years_experience"), "season", "team_code", "player_id", foreign_keys=(_fk("player_id", "player", "player_id"), _fk("source_record_id", "source_record", "source_record_id"))),
    _table("roster_snapshot", ("snapshot_id", "snapshot_date", "snapshot_kind", "season", "team_code", "source_record_id", "notes"), "snapshot_id", foreign_keys=(_fk("source_record_id", "source_record", "source_record_id"),)),
    _table("draft_selection", ("draft_selection_id", "draft_year", "pick_overall", "round_number", "team_code", "player_id", "pick_id", "source_event_id", "notes"), "draft_selection_id", foreign_keys=(_fk("player_id", "player", "player_id"), _fk("pick_id", "pick", "pick_id"), _fk("source_event_id", "source_event", "source_event_id"))),
    _table("daily_roster_state", ("roster_state_id", "state_date", "season", "team_code", "source_record_id", "event_count", "source_event_ids", "player_count", "standard_count", "two_way_count", "derivation_mode", "notes", "created_at", "updated_at"), "roster_state_id", foreign_keys=(_fk("source_record_id", "source_record", "source_record_id"),)),
    _table("canonical_event_member", ("canonical_event_id", "source_event_id"), "canonical_event_id", "source_event_id", foreign_keys=(_fk("canonical_event_id", "canonical_event", "canonical_event_id"), _fk("source_event_id", "source_event", "source_event_id"))),
    _table("event_asset_transition", ("transition_id", "canonical_event_id", "asset_id", "transition_type", "direction"), "transition_id", foreign_keys=(_fk("canonical_event_id", "canonical_event", "canonical_event_id"), _fk("asset_id", "asset", "asset_id"))),
    _table("pick_inventory_obligation", ("obligation_id", "effective_date", "perspective_team_code", "owner_team_code", "original_team_code", "draft_year", "round_number", "direction", "holding_status", "obligation_type", "confidence", "source_urls", "source_labels", "retrieved_at", "source_event_id", "canonical_event_id", "protection_text", "swap_text", "condition_text", "notes", "composite_family_id", "composite_kind", "composite_payload", "loadable", "created_at", "updated_at"), "obligation_id", foreign_keys=(_fk("source_event_id", "source_event", "source_event_id"), _fk("canonical_event_id", "canonical_event", "canonical_event_id"))),
    _table("roster_snapshot_player", ("snapshot_id", "player_id", "asset_id", "roster_status", "depth_order", "is_two_way", "is_standard_contract"), "snapshot_id", "player_id", foreign_keys=(_fk("snapshot_id", "roster_snapshot", "snapshot_id"), _fk("player_id", "player", "player_id"), _fk("asset_id", "asset", "asset_id"))),
    _table("roster_snapshot_pick", ("snapshot_id", "pick_id", "asset_id", "holding_status", "display_order", "source_obligation_id", "confidence", "notes"), "snapshot_id", "pick_id", foreign_keys=(_fk("snapshot_id", "roster_snapshot", "snapshot_id"), _fk("pick_id", "pick", "pick_id"), _fk("asset_id", "asset", "asset_id"), _fk("source_obligation_id", "pick_inventory_obligation", "obligation_id"))),
    _table("roster_snapshot_validation", ("snapshot_id", "validation_scope", "validation_status", "reference_source_record_id", "snapshot_player_count", "reference_player_count", "matched_player_count", "notes", "created_at", "updated_at"), "snapshot_id", foreign_keys=(_fk("snapshot_id", "roster_snapshot", "snapshot_id"), _fk("reference_source_record_id", "source_record", "source_record_id"))),
    _table("draft_pick_resolution", ("draft_pick_resolution_id", "draft_selection_id", "pick_id", "pick_asset_id", "player_id", "player_asset_id", "draft_year", "round_number", "pick_overall", "team_code", "resolution_status", "confidence", "source_bundle_id", "source_locator", "notes", "created_at", "updated_at"), "draft_pick_resolution_id", foreign_keys=(_fk("draft_selection_id", "draft_selection", "draft_selection_id"), _fk("pick_id", "pick", "pick_id"), _fk("pick_asset_id", "asset", "asset_id"), _fk("player_id", "player", "player_id"), _fk("player_asset_id", "asset", "asset_id"))),
    _table("daily_roster_state_player", ("roster_state_id", "state_date", "season", "team_code", "player_id", "display_name", "asset_id", "roster_status", "roster_order", "is_two_way", "is_standard_contract"), "roster_state_id", "player_id", foreign_keys=(_fk("roster_state_id", "daily_roster_state", "roster_state_id"), _fk("player_id", "player", "player_id"), _fk("asset_id", "asset", "asset_id"))),
    _table("draft_prior_owner_lineage", ("draft_prior_owner_lineage_id", "draft_selection_id", "draft_pick_resolution_id", "pick_id", "pick_asset_id", "player_id", "player_asset_id", "draft_year", "round_number", "pick_overall", "team_code", "owner_team_code", "original_team_code", "source_obligation_id", "resolution_kind", "confidence", "notes", "created_at", "updated_at"), "draft_prior_owner_lineage_id", foreign_keys=(_fk("draft_selection_id", "draft_selection", "draft_selection_id"), _fk("draft_pick_resolution_id", "draft_pick_resolution", "draft_pick_resolution_id"), _fk("pick_id", "pick", "pick_id"), _fk("pick_asset_id", "asset", "asset_id"), _fk("player_id", "player", "player_id"), _fk("player_asset_id", "asset", "asset_id"), _fk("source_obligation_id", "pick_inventory_obligation", "obligation_id"))),
)

TABLE_BY_NAME = {table.name: table for table in FOUNDATION_TABLES}
RESTORE_INSERT_ORDER = tuple(table.name for table in FOUNDATION_TABLES)
DELETE_ORDER = tuple(reversed(RESTORE_INSERT_ORDER))


def foundation_table(name: str) -> FoundationTable:
    try:
        return TABLE_BY_NAME[name]
    except KeyError as error:
        raise ValueError(f"Unknown foundation table: {name}") from error


def foundation_schema_contract() -> tuple[dict[str, object], ...]:
    """Return the closed logical contract used in snapshot fingerprints.

    Keeping this derived from the immutable manifest means a snapshot cannot be
    accidentally taken from a caller-selected subset or table order.
    """

    return tuple(
        {
            "name": table.name,
            "columns": table.columns,
            "key_columns": table.key_columns,
            "alternate_unique_keys": table.alternate_unique_keys,
            "foreign_keys": tuple(
                {
                    "column": foreign_key.column,
                    "parent_table": foreign_key.parent_table,
                    "parent_column": foreign_key.parent_column,
                }
                for foreign_key in table.foreign_keys
            ),
        }
        for table in FOUNDATION_TABLES
    )
