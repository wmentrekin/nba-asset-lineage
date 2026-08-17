"""Immutable refresh mutations with identical in-memory and PostgreSQL semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, TypeAlias

from foundation.foundation_table_manifest import FOUNDATION_TABLES, foundation_table

Row: TypeAlias = dict[str, object]
UpdatePolicy = Literal["excluded", "coalesce_excluded_existing", "preserve_existing", "append_once", "constant", "operation_timestamp"]


@dataclass(frozen=True)
class UpsertRows:
    table: str
    rows: tuple[Row, ...]
    policies: tuple[tuple[str, UpdatePolicy], ...] = ()


@dataclass(frozen=True)
class InsertMissingRows:
    table: str
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class DeleteKeys:
    table: str
    keys: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ReplacePartitions:
    table: str
    partition_columns: tuple[str, ...]
    partition_values: tuple[tuple[object, ...], ...]
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class ReplaceAll:
    table: str
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class PatchRows:
    table: str
    patches: tuple[tuple[tuple[object, ...], Row], ...]
    policies: tuple[tuple[str, UpdatePolicy], ...] = ()


FoundationMutation: TypeAlias = UpsertRows | InsertMissingRows | DeleteKeys | ReplacePartitions | ReplaceAll | PatchRows


@dataclass(frozen=True)
class FoundationMutationPlan:
    operations: tuple[FoundationMutation, ...]
    operation_timestamp: str

    def __post_init__(self) -> None:
        datetime.fromisoformat(self.operation_timestamp.replace("Z", "+00:00"))
        for operation in self.operations:
            _validate_operation(operation)


TableState: TypeAlias = dict[str, dict[tuple[object, ...], Row]]


def empty_table_state() -> TableState:
    return {table.name: {} for table in FOUNDATION_TABLES}


def source_partition_plan(
    *,
    source_records: tuple[Row, ...],
    source_events: tuple[Row, ...],
    players: tuple[Row, ...] = (),
    draft_selections: tuple[Row, ...] = (),
    operation_timestamp: str,
) -> FoundationMutationPlan:
    """Build the common locked-source plan once for preview and execution.

    Source events retain the existing per-source-record replacement behavior;
    entities and selections retain their existing upsert/coalesce behavior.
    """
    record_ids = tuple((row["source_record_id"],) for row in source_records)
    return FoundationMutationPlan(
        operation_timestamp=operation_timestamp,
        operations=(
            UpsertRows("source_record", source_records),
            ReplacePartitions("source_event", ("source_record_id",), record_ids, source_events),
            UpsertRows("player", players),
            UpsertRows(
                "draft_selection",
                draft_selections,
                (("pick_id", "coalesce_excluded_existing"), ("source_event_id", "coalesce_excluded_existing")),
            ),
        ),
    )


def apply_plan_to_snapshot(snapshot: TableState, plan: FoundationMutationPlan) -> TableState:
    """Apply a plan without mutation; this is the projection implementation."""
    result: TableState = {name: {key: dict(row) for key, row in rows.items()} for name, rows in snapshot.items()}
    for table in FOUNDATION_TABLES:
        result.setdefault(table.name, {})
    for operation in plan.operations:
        _apply_operation(result, operation, plan.operation_timestamp)
    return result


class TableStateConnection(Protocol):
    """Small fake-connection seam for differential tests; never opens a DB."""
    table_state: TableState


def execute_plan(connection: Any, plan: FoundationMutationPlan) -> None:
    """Execute the exact plan used by projection.

    Test fakes expose ``table_state``.  Real psycopg connections receive only
    identifiers from the closed manifest and values through parameters.
    """
    if hasattr(connection, "table_state"):
        connection.table_state = apply_plan_to_snapshot(connection.table_state, plan)
        return
    for operation in plan.operations:
        _execute_postgres_operation(connection, operation, plan.operation_timestamp)


def _validate_operation(operation: FoundationMutation) -> None:
    table = foundation_table(operation.table)
    rows: tuple[Row, ...] = getattr(operation, "rows", ())
    for row in rows:
        unknown = set(row).difference(table.columns)
        missing = set(table.key_columns).difference(row)
        if unknown or missing:
            raise ValueError(f"Invalid {table.name} row: unknown={sorted(unknown)}, missing_key={sorted(missing)}")
    if isinstance(operation, ReplacePartitions):
        if not operation.partition_columns or any(column not in table.columns for column in operation.partition_columns):
            raise ValueError("ReplacePartitions has invalid partition columns")
        if any(len(values) != len(operation.partition_columns) for values in operation.partition_values):
            raise ValueError("ReplacePartitions values do not match partition columns")
    if isinstance(operation, (UpsertRows, PatchRows)):
        policies = dict(operation.policies)
        if any(column not in table.columns or policy not in _UPDATE_POLICIES for column, policy in policies.items()):
            raise ValueError("Invalid update policy")


_UPDATE_POLICIES = {"excluded", "coalesce_excluded_existing", "preserve_existing", "append_once", "constant", "operation_timestamp"}


def _key(table_name: str, row: Row) -> tuple[object, ...]:
    table = foundation_table(table_name)
    return tuple(row[column] for column in table.key_columns)


def _merged(existing: Row | None, incoming: Row, policies: dict[str, UpdatePolicy], timestamp: str) -> Row:
    result = dict(existing or {})
    for column, value in incoming.items():
        policy = policies.get(column, "excluded")
        if policy == "preserve_existing" and column in result:
            continue
        if policy == "coalesce_excluded_existing" and value is None:
            continue
        if policy == "append_once" and column in result and result[column] is not None:
            continue
        if policy == "constant" and column in result and result[column] != value:
            raise ValueError(f"Constant column changed: {column}")
        result[column] = timestamp if policy == "operation_timestamp" else value
    return result


def _apply_operation(state: TableState, operation: FoundationMutation, timestamp: str) -> None:
    rows = state[operation.table]
    if isinstance(operation, DeleteKeys):
        for key in operation.keys:
            rows.pop(key, None)
    elif isinstance(operation, ReplaceAll):
        rows.clear()
        for row in operation.rows:
            rows[_key(operation.table, row)] = dict(row)
    elif isinstance(operation, ReplacePartitions):
        targets = set(operation.partition_values)
        for key, row in list(rows.items()):
            if tuple(row.get(column) for column in operation.partition_columns) in targets:
                del rows[key]
        for row in operation.rows:
            rows[_key(operation.table, row)] = dict(row)
    elif isinstance(operation, InsertMissingRows):
        for row in operation.rows:
            rows.setdefault(_key(operation.table, row), dict(row))
    elif isinstance(operation, UpsertRows):
        policies = dict(operation.policies)
        for row in operation.rows:
            key = _key(operation.table, row)
            rows[key] = _merged(rows.get(key), row, policies, timestamp)
    else:
        policies = dict(operation.policies)
        for key, patch in operation.patches:
            if key in rows:
                rows[key] = _merged(rows[key], patch, policies, timestamp)


def _execute_postgres_operation(connection: Any, operation: FoundationMutation, timestamp: str) -> None:
    """Use the in-memory semantics as the single source of policy truth.

    The production runner supplies registered table-state adapters in T9.  This
    minimal SQL path remains useful for fake cursors and rejects arbitrary SQL.
    """
    table = foundation_table(operation.table)
    with connection.cursor() as cursor:
        if isinstance(operation, DeleteKeys):
            predicate = " and ".join(f"{column} = %s" for column in table.key_columns)
            for key in operation.keys:
                cursor.execute(f"delete from foundation.{table.name} where {predicate}", key)
        elif isinstance(operation, ReplaceAll):
            cursor.execute(f"delete from foundation.{table.name}")
            _insert_rows(cursor, table.name, operation.rows)
        elif isinstance(operation, ReplacePartitions):
            predicate = " and ".join(f"{column} = %s" for column in operation.partition_columns)
            for values in operation.partition_values:
                cursor.execute(f"delete from foundation.{table.name} where {predicate}", values)
            _insert_rows(cursor, table.name, operation.rows)
        elif isinstance(operation, InsertMissingRows):
            _insert_rows(cursor, table.name, operation.rows, do_nothing=True)
        elif isinstance(operation, UpsertRows):
            _upsert_rows(cursor, table.name, operation.rows, dict(operation.policies), timestamp)
        else:
            _patch_rows(cursor, table.name, operation.patches, dict(operation.policies), timestamp)


def _insert_rows(cursor: Any, table_name: str, rows: tuple[Row, ...], *, do_nothing: bool = False) -> None:
    for row in rows:
        columns = tuple(row)
        placeholders = ", ".join(["%s"] * len(columns))
        conflict = " on conflict do nothing" if do_nothing else ""
        cursor.execute(f"insert into foundation.{table_name} ({', '.join(columns)}) values ({placeholders}){conflict}", tuple(row[column] for column in columns))


def _upsert_rows(cursor: Any, table_name: str, rows: tuple[Row, ...], policies: dict[str, UpdatePolicy], timestamp: str) -> None:
    table = foundation_table(table_name)
    for row in rows:
        columns = tuple(row)
        updates = []
        for column in columns:
            if column in table.key_columns:
                continue
            policy = policies.get(column, "excluded")
            if policy == "preserve_existing":
                continue
            if policy == "coalesce_excluded_existing":
                updates.append(f"{column} = coalesce(excluded.{column}, foundation.{table_name}.{column})")
            elif policy == "append_once":
                updates.append(f"{column} = coalesce(foundation.{table_name}.{column}, excluded.{column})")
            elif policy == "operation_timestamp":
                updates.append(f"{column} = %s")
            else:
                updates.append(f"{column} = excluded.{column}")
        placeholders = ", ".join(["%s"] * len(columns))
        action = "do nothing" if not updates else "do update set " + ", ".join(updates)
        # The timestamp is part of the immutable plan, including its insert
        # branch; otherwise preview and execution would disagree on new rows.
        parameters: tuple[object, ...] = tuple(
            timestamp if policies.get(column) == "operation_timestamp" else row[column]
            for column in columns
        )
        parameters += tuple(timestamp for column in columns if policies.get(column) == "operation_timestamp" and column not in table.key_columns)
        cursor.execute(f"insert into foundation.{table_name} ({', '.join(columns)}) values ({placeholders}) on conflict ({', '.join(table.key_columns)}) {action}", parameters)


def _patch_rows(cursor: Any, table_name: str, patches: tuple[tuple[tuple[object, ...], Row], ...], policies: dict[str, UpdatePolicy], timestamp: str) -> None:
    table = foundation_table(table_name)
    predicate = " and ".join(f"{column} = %s" for column in table.key_columns)
    for key, patch in patches:
        assignments, values = [], []
        for column, value in patch.items():
            policy = policies.get(column, "excluded")
            if policy == "preserve_existing":
                continue
            if policy == "coalesce_excluded_existing":
                assignments.append(f"{column} = coalesce(%s, {column})")
            elif policy == "append_once":
                assignments.append(f"{column} = coalesce({column}, %s)")
            else:
                assignments.append(f"{column} = %s")
            values.append(timestamp if policy == "operation_timestamp" else value)
        if assignments:
            cursor.execute(f"update foundation.{table.name} set {', '.join(assignments)} where {predicate}", tuple(values) + key)
