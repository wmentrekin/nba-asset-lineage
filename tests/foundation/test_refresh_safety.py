from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from foundation.foundation_table_manifest import FOUNDATION_TABLES
from foundation.refresh_safety import (
    FoundationSnapshot,
    RefreshSafetyError,
    SNAPSHOT_FILE_NAME,
    canonical_database_value,
    canonical_safety_digest,
    capture_foundation_snapshot,
    create_refresh_artifact_directory,
    foundation_schema_fingerprint,
    load_foundation_snapshot,
    logical_database_fingerprint,
    snapshot_payload,
    write_foundation_snapshot,
)


class FakeCursor:
    def __init__(self, rows_by_table: dict[str, list[object]]) -> None:
        self.rows_by_table = rows_by_table
        self.queries: list[str] = []
        self.current_rows: list[object] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> None:
        assert params is None
        self.queries.append(query)
        if query.startswith("SELECT"):
            table_name = query.split("foundation.", 1)[1].split(" ", 1)[0]
            self.current_rows = self.rows_by_table[table_name]

    def fetchall(self) -> list[object]:
        return self.current_rows


class FakeConnection:
    def __init__(self, rows_by_table: dict[str, list[object]]) -> None:
        self.cursor_instance = FakeCursor(rows_by_table)
        self.rollbacks = 0

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def rollback(self) -> None:
        self.rollbacks += 1


def _empty_snapshot() -> FoundationSnapshot:
    return FoundationSnapshot(
        tables={table.name: () for table in FOUNDATION_TABLES},
        schema_fingerprint=foundation_schema_fingerprint(),
        database_fingerprint=logical_database_fingerprint(database_name="nba", server_version=170002),
    )


def test_canonical_database_values_are_tagged_and_digest_is_a_golden_vector() -> None:
    value = {
        "bytes": b"\x00\xff",
        "date": date(2026, 8, 16),
        "datetime": datetime(2026, 8, 16, 12, 30, tzinfo=timezone.utc),
        "decimal": Decimal("1.20"),
    }
    assert canonical_database_value(value)["type"] == "object"
    assert canonical_safety_digest("golden", {"value": 7}) == "a96232f78ea743c4a907a10ff730d377fd5104492d941fa114f8d49037c97b62"
    with pytest.raises(RefreshSafetyError, match="Unsupported"):
        canonical_database_value(object())


def test_snapshot_capture_uses_exact_manifest_selects_and_read_only_transaction() -> None:
    rows = {table.name: [] for table in FOUNDATION_TABLES}
    rows["source_record"] = [("source-1", "nba", "movement", "x", None, {"ok": True})]
    connection = FakeConnection(rows)
    snapshot = capture_foundation_snapshot(
        connection,
        database_fingerprint=logical_database_fingerprint(database_name="nba", server_version=170002),
    )
    assert tuple(snapshot.tables) == tuple(table.name for table in FOUNDATION_TABLES)
    assert snapshot.tables["source_record"][0]["source_record_id"] == "source-1"
    assert connection.cursor_instance.queries[0] == "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    selects = connection.cursor_instance.queries[1:]
    assert len(selects) == 21
    for table, query in zip(FOUNDATION_TABLES, selects, strict=True):
        assert query == f"SELECT {', '.join(table.columns)} FROM foundation.{table.name} ORDER BY {', '.join(table.key_columns)}"
    assert connection.rollbacks == 1


def test_snapshot_write_load_is_deterministic_and_rejects_tamper(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(mode=0o700)
    artifact_dir = create_refresh_artifact_directory(repo_root, "refresh-2026-08-16")
    snapshot = _empty_snapshot()
    target = write_foundation_snapshot(artifact_dir, snapshot)
    assert target.name == SNAPSHOT_FILE_NAME
    assert target.stat().st_mode & 0o077 == 0
    assert load_foundation_snapshot(target, expected_digest=snapshot.digest).digest == snapshot.digest
    target.write_bytes(b"{}")
    with pytest.raises(RefreshSafetyError):
        load_foundation_snapshot(target, expected_digest=snapshot.digest)


def test_artifact_directory_is_repo_local_private_and_no_overwrite(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(mode=0o700)
    directory = create_refresh_artifact_directory(repo_root, "refresh-a")
    with pytest.raises(RefreshSafetyError, match="overwrite"):
        create_refresh_artifact_directory(repo_root, "refresh-a")
    with pytest.raises(RefreshSafetyError, match="unsafe"):
        create_refresh_artifact_directory(repo_root, "../escape")
    write_foundation_snapshot(directory, _empty_snapshot())
    with pytest.raises(RefreshSafetyError, match="overwrite"):
        write_foundation_snapshot(directory, _empty_snapshot())


def test_snapshot_payload_is_closed_to_all_21_manifest_tables() -> None:
    payload = snapshot_payload(_empty_snapshot())
    assert [table["name"] for table in payload["tables"]] == [table.name for table in FOUNDATION_TABLES]
    assert len(payload["tables"]) == 21


def test_manifest_foreign_keys_reference_closed_parent_columns() -> None:
    by_name = {table.name: table for table in FOUNDATION_TABLES}
    for table in FOUNDATION_TABLES:
        for foreign_key in table.foreign_keys:
            assert foreign_key.column in table.columns
            assert foreign_key.parent_table in by_name
            assert foreign_key.parent_column in by_name[foreign_key.parent_table].columns
