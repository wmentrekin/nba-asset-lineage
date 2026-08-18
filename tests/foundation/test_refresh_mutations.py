from foundation.foundation_table_manifest import FOUNDATION_TABLES
from foundation.refresh_mutations import (
    DeleteKeys,
    FoundationMutationPlan,
    InsertMissingRows,
    PatchRows,
    ReplaceAll,
    ReplacePartitions,
    UpsertRows,
    apply_plan_to_snapshot,
    empty_table_state,
    execute_plan,
    source_partition_plan,
)


class FakeConnection:
    def __init__(self, table_state):
        self.table_state = table_state


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))


class SqlRecordingConnection:
    def __init__(self):
        self.cursor_obj = RecordingCursor()

    def cursor(self):
        return self.cursor_obj


def test_sql_insert_executes_every_row_in_partition_replacement() -> None:
    connection = SqlRecordingConnection()
    plan = FoundationMutationPlan(
        operation_timestamp="2026-08-17T00:00:00Z",
        operations=(ReplaceAll("player", (
            {"player_id": "player:1", "display_name": "One"},
            {"player_id": "player:2", "display_name": "Two"},
        )),),
    )
    execute_plan(connection, plan)
    inserts = [call for call in connection.cursor_obj.calls if call[0].startswith("insert")]
    assert len(inserts) == 2
    assert [call[1] for call in inserts] == [("player:1", "One"), ("player:2", "Two")]


def test_closed_manifest_contains_the_21_active_foundation_tables() -> None:
    assert len(FOUNDATION_TABLES) == 21
    assert {table.name for table in FOUNDATION_TABLES} >= {"source_record", "source_event", "canonical_event", "daily_roster_state"}


def test_pure_and_registered_table_state_adapters_have_identical_mutation_semantics() -> None:
    baseline = empty_table_state()
    baseline["draft_selection"][("selection:1",)] = {"draft_selection_id": "selection:1", "team_code": "MEM", "pick_id": "old"}
    baseline["roster_snapshot_player"][("snap:1", "player:1")] = {
        "snapshot_id": "snap:1", "player_id": "player:1", "roster_status": "standard", "is_two_way": False
    }
    plan = FoundationMutationPlan(
        operation_timestamp="2026-08-17T00:00:00Z",
        operations=(
            UpsertRows("source_record", ({"source_record_id": "record:1", "source_system": "nba"},)),
            ReplacePartitions("source_event", ("source_record_id",), (("record:1",),), ({"source_event_id": "event:1", "source_record_id": "record:1"},)),
            UpsertRows("draft_selection", ({"draft_selection_id": "selection:1", "team_code": "MEM", "pick_id": None},), (("pick_id", "coalesce_excluded_existing"),)),
            PatchRows("roster_snapshot_player", ((("snap:1", "player:1"), {"roster_status": "two_way", "is_two_way": True}),)),
            InsertMissingRows("player", ({"player_id": "player:1", "display_name": "Player One"},)),
            ReplaceAll("canonical_event", ({"canonical_event_id": "canonical:1", "event_date": "2026-08-17"},)),
            DeleteKeys("canonical_event", (("missing",),)),
        ),
    )
    expected = apply_plan_to_snapshot(baseline, plan)
    fake = FakeConnection(baseline)
    execute_plan(fake, plan)
    assert fake.table_state == expected
    assert fake.table_state["draft_selection"][("selection:1",)]["pick_id"] == "old"


def test_bound_operation_timestamp_is_used_by_both_adapters() -> None:
    plan = FoundationMutationPlan(
        operation_timestamp="2026-08-17T12:00:00Z",
        operations=(UpsertRows("roster_snapshot_validation", ({"snapshot_id": "snap:1", "updated_at": "ignored"},), (("updated_at", "operation_timestamp"),)),),
    )
    state = apply_plan_to_snapshot(empty_table_state(), plan)
    assert state["roster_snapshot_validation"][("snap:1",)]["updated_at"] == "2026-08-17T12:00:00Z"


def test_source_partition_plan_replaces_only_reviewed_source_record_partitions() -> None:
    state = empty_table_state()
    state["source_event"][("old:1",)] = {"source_event_id": "old:1", "source_record_id": "record:1"}
    state["source_event"][("keep:1",)] = {"source_event_id": "keep:1", "source_record_id": "record:2"}
    plan = source_partition_plan(
        source_records=({"source_record_id": "record:1", "source_system": "nba"},),
        source_events=({"source_event_id": "new:1", "source_record_id": "record:1"},),
        operation_timestamp="2026-08-17T00:00:00Z",
    )
    result = apply_plan_to_snapshot(state, plan)
    assert set(result["source_event"]) == {("new:1",), ("keep:1",)}
