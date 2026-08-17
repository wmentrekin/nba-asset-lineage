from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from contextlib import contextmanager
from hashlib import sha256

import pytest

from foundation.foundation_table_manifest import FOUNDATION_TABLES
from foundation.foundation_table_manifest import DELETE_ORDER, RESTORE_INSERT_ORDER, TABLE_BY_NAME
from foundation.refresh_safety import (
    APPROVAL_FINGERPRINT_FIELDS,
    APPROVAL_FILE_NAME,
    FoundationSnapshot,
    RefreshApproval,
    ApprovedRefreshStep,
    ApprovedRefreshPlans,
    EXECUTION_STATE_FILE_NAME,
    RefreshSafetyError,
    RefreshExecutionError,
    RUNNER_PREFIX_KEYS,
    RUNNER_STEP_NAMES,
    SNAPSHOT_FILE_NAME,
    canonical_database_value,
    canonical_safety_digest,
    capture_foundation_snapshot,
    create_refresh_artifact_directory,
    validate_refresh_artifact_directory,
    foundation_schema_fingerprint,
    load_foundation_snapshot,
    load_refresh_approval,
    preflight_refresh_approval,
    run_approved_foundation_refresh,
    load_refresh_execution_state,
    refresh_approval_payload,
    restore_approved_foundation_snapshot,
    logical_database_fingerprint,
    snapshot_payload,
    write_foundation_snapshot,
    write_refresh_approval,
)
from foundation.refresh_mutations import FoundationMutationPlan, UpsertRows, apply_plan_to_snapshot, empty_table_state


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


def _approval(*, action: str = "execute_refresh") -> RefreshApproval:
    fingerprints = {field: f"{index:064x}" for index, field in enumerate(APPROVAL_FINGERPRINT_FIELDS, start=1)}
    return RefreshApproval(
        action=action,
        approved_by="Wes",
        user_go_reference="conversation:2026-08-17:proceed",
        fingerprints=fingerprints,
        prefix_fingerprints={"approved-source-loads": "f" * 64},
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


def test_artifact_directory_allows_normal_repo_and_tmp_ancestor_modes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(mode=0o755)
    temporary_root = repo_root / "tmp"
    temporary_root.mkdir(mode=0o755)
    directory = create_refresh_artifact_directory(repo_root, "normal-root")

    assert directory == temporary_root / "normal-root"
    assert directory.stat().st_mode & 0o777 == 0o700
    assert not directory.is_symlink()


def test_artifact_directory_validation_requires_the_real_repo_local_leaf(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(mode=0o755)
    (repo_root / ".git").mkdir()
    directory = create_refresh_artifact_directory(repo_root, "refresh-a")
    assert validate_refresh_artifact_directory(directory) == repo_root

    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    with pytest.raises(RefreshSafetyError, match="repo-local tmp/<refresh-id> leaf"):
        validate_refresh_artifact_directory(outside)


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


def test_closed_action_specific_approval_round_trip_and_preflight(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(mode=0o700)
    directory = create_refresh_artifact_directory(repo_root, "approval-a")
    approval = _approval()
    path = write_refresh_approval(directory, approval)
    assert path.name == APPROVAL_FILE_NAME
    loaded = load_refresh_approval(path, expected_digest=approval.digest)
    assert preflight_refresh_approval(
        loaded,
        action="execute_refresh",
        current_fingerprints=approval.fingerprints,
        current_prefix_fingerprints=approval.prefix_fingerprints,
    ) == approval
    with pytest.raises(RefreshSafetyError, match="does not authorize"):
        preflight_refresh_approval(
            loaded,
            action="restore_snapshot",
            current_fingerprints=approval.fingerprints,
            current_prefix_fingerprints=approval.prefix_fingerprints,
        )


def test_approval_rejects_missing_extra_or_stale_fingerprints_before_any_write(tmp_path: Path) -> None:
    approval = _approval()
    incomplete = dict(approval.fingerprints)
    incomplete.pop("snapshot_digest")
    with pytest.raises(RefreshSafetyError, match="closed schema"):
        RefreshApproval(
            action=approval.action,
            approved_by=approval.approved_by,
            user_go_reference=approval.user_go_reference,
            fingerprints=incomplete,
            prefix_fingerprints=approval.prefix_fingerprints,
        ).digest
    stale = dict(approval.fingerprints)
    stale["dirty_tree_fingerprint"] = "0" * 64
    with pytest.raises(RefreshSafetyError, match="stale or mismatched"):
        preflight_refresh_approval(
            approval,
            action="execute_refresh",
            current_fingerprints=stale,
            current_prefix_fingerprints=approval.prefix_fingerprints,
        )
    payload = refresh_approval_payload(approval)
    payload["unexpected"] = True
    path = tmp_path / APPROVAL_FILE_NAME
    path.write_text(__import__("json").dumps(payload), encoding="utf-8")
    with pytest.raises(RefreshSafetyError):
        load_refresh_approval(path)


class FakeRefreshConnection:
    def __init__(self, *, crash: str | None = None) -> None:
        self.table_state = empty_table_state()
        self.crash = crash
        self.lock_calls: list[str] = []

    def acquire_refresh_lock(self) -> None:
        self.lock_calls.append("acquire")

    def release_refresh_lock(self) -> None:
        self.lock_calls.append("release")

    @contextmanager
    def transaction(self):
        if self.crash == "before":
            self.crash = None
            raise RuntimeError("crash before commit")
        yield
        if self.crash == "after":
            self.crash = None
            raise RuntimeError("crash after commit")


def _state_digest(connection: FakeRefreshConnection) -> str:
    keys = sorted(key[0] for key in connection.table_state["source_record"])
    return sha256("|".join(keys).encode("utf-8")).hexdigest()


def _runner_fixture() -> tuple[RefreshApproval, ApprovedRefreshPlans, dict[str, str]]:
    plans = ApprovedRefreshPlans(
        tuple(
            ApprovedRefreshStep(
                name=step_name,
                plan=FoundationMutationPlan(
                    operations=(
                        ()
                        if step_name == RUNNER_STEP_NAMES[-1]
                        else (UpsertRows("source_record", ({"source_record_id": f"step:{index}", "source_system": "test"},)),)
                    ),
                    operation_timestamp="2026-08-17T00:00:00Z",
                ),
            )
            for index, step_name in enumerate(RUNNER_STEP_NAMES)
        )
    )
    state = empty_table_state()
    prefixes = [_state_digest(type("State", (), {"table_state": state})())]
    for step in plans.steps:
        state = apply_plan_to_snapshot(state, step.plan)
        prefixes.append(_state_digest(type("State", (), {"table_state": state})()))
    prefix_fingerprints = dict(zip(RUNNER_PREFIX_KEYS, prefixes, strict=True))
    approval = RefreshApproval(
        action="execute_refresh",
        approved_by="Wes",
        user_go_reference="conversation:proceed",
        fingerprints={field: f"{index:064x}" for index, field in enumerate(APPROVAL_FINGERPRINT_FIELDS, start=1)},
        prefix_fingerprints=prefix_fingerprints,
    )
    return approval, plans, prefix_fingerprints


@pytest.mark.parametrize("crash", ["before", "after"])
def test_fixed_runner_recovers_only_approved_pre_or_post_prefixes(tmp_path: Path, crash: str) -> None:
    directory = tmp_path / "artifacts"
    directory.mkdir(mode=0o700)
    approval, plans, prefixes = _runner_fixture()
    connection = FakeRefreshConnection(crash=crash)
    path = directory / EXECUTION_STATE_FILE_NAME

    with pytest.raises(RuntimeError):
        run_approved_foundation_refresh(
            connection,
            approval=approval,
            current_fingerprints=approval.fingerprints,
            current_prefix_fingerprints=prefixes,
            plans=plans,
            execution_state_path=path,
            prefix_fingerprint_reader=_state_digest,
        )
    assert load_refresh_execution_state(path).status == "failed"
    completed = run_approved_foundation_refresh(
        connection,
        approval=approval,
        current_fingerprints=approval.fingerprints,
        current_prefix_fingerprints=prefixes,
        plans=plans,
        execution_state_path=path,
        prefix_fingerprint_reader=_state_digest,
    )
    assert completed.status == "completed"
    assert completed.step_index == len(RUNNER_STEP_NAMES)
    assert connection.lock_calls == ["acquire", "release", "acquire", "release"]


def test_fixed_runner_rejects_reordered_or_unexpected_prefix_state_before_writes(tmp_path: Path) -> None:
    directory = tmp_path / "artifacts"
    directory.mkdir(mode=0o700)
    approval, plans, prefixes = _runner_fixture()
    connection = FakeRefreshConnection()
    connection.table_state["source_record"][("outside",)] = {"source_record_id": "outside", "source_system": "test"}
    path = directory / EXECUTION_STATE_FILE_NAME
    with pytest.raises(RefreshExecutionError, match="pre-prefix"):
        run_approved_foundation_refresh(
            connection,
            approval=approval,
            current_fingerprints=approval.fingerprints,
            current_prefix_fingerprints=prefixes,
            plans=plans,
            execution_state_path=path,
            prefix_fingerprint_reader=_state_digest,
        )
    assert load_refresh_execution_state(path).status == "needs_restore"
    with pytest.raises(RefreshExecutionError, match="every fixed runner step"):
        ApprovedRefreshPlans(plans.steps[:-1])


@pytest.mark.parametrize(
    "steps",
    [
        lambda steps: (steps[1], steps[0], *steps[2:]),
        lambda steps: (steps[0], steps[0], *steps[2:]),
        lambda steps: steps[:-1],
        lambda steps: (*steps, steps[0]),
    ],
    ids=["reordered", "duplicate", "missing", "extra"],
)
def test_runner_rejects_any_non_closed_labeled_plan_set_before_connection_write(
    tmp_path: Path,
    steps: object,
) -> None:
    approval, approved_plans, prefixes = _runner_fixture()
    invalid_steps = steps(approved_plans.steps)  # type: ignore[operator]
    with pytest.raises(RefreshExecutionError, match="every fixed runner step"):
        ApprovedRefreshPlans(invalid_steps)

    connection = FakeRefreshConnection()
    state_path = tmp_path / EXECUTION_STATE_FILE_NAME
    object.__setattr__(approved_plans, "steps", invalid_steps)
    with pytest.raises(RefreshExecutionError, match="every fixed runner step"):
        run_approved_foundation_refresh(
            connection,
            approval=approval,
            current_fingerprints=approval.fingerprints,
            current_prefix_fingerprints=prefixes,
            plans=approved_plans,
            execution_state_path=state_path,
            prefix_fingerprint_reader=_state_digest,
        )
    assert connection.lock_calls == []
    assert not state_path.exists()


def test_runner_rejects_a_mutating_final_audit_plan_before_any_side_effect(tmp_path: Path) -> None:
    approval, plans, prefixes = _runner_fixture()
    final_step = plans.steps[-1]
    malicious = ApprovedRefreshStep(
        final_step.name,
        FoundationMutationPlan(
            (UpsertRows("source_record", ({"source_record_id": "audit:mutation", "source_system": "test"},)),),
            "2026-08-17T00:00:00Z",
        ),
    )
    object.__setattr__(plans, "steps", (*plans.steps[:-1], malicious))
    connection = FakeRefreshConnection()
    state_path = tmp_path / EXECUTION_STATE_FILE_NAME

    with pytest.raises(RefreshExecutionError, match="audit/export verification plan must be empty"):
        run_approved_foundation_refresh(
            connection,
            approval=approval,
            current_fingerprints=approval.fingerprints,
            current_prefix_fingerprints=prefixes,
            plans=plans,
            execution_state_path=state_path,
            prefix_fingerprint_reader=_state_digest,
        )

    assert connection.lock_calls == []
    assert not state_path.exists()
    assert connection.table_state["source_record"] == {}


class FakeRestoreCursor:
    def __init__(self, connection: "FakeRestoreConnection") -> None:
        self.connection = connection
        self.queries: list[str] = []
        self.current_rows: list[object] = []

    def __enter__(self) -> "FakeRestoreCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> None:
        self.queries.append(query)
        if self.connection.fail_on and self.connection.fail_on in query:
            raise RuntimeError("restore write failed")
        if query.startswith("DELETE FROM foundation."):
            self.connection.rows[query.removeprefix("DELETE FROM foundation.")] = []
        elif query.startswith("INSERT INTO foundation."):
            table_name = query.split("foundation.", 1)[1].split(" ", 1)[0]
            table = TABLE_BY_NAME[table_name]
            assert isinstance(params, tuple)
            self.connection.rows[table_name].append(dict(zip(table.columns, params, strict=True)))
        elif query.startswith("SELECT"):
            table_name = query.split("foundation.", 1)[1].split(" ", 1)[0]
            self.current_rows = list(self.connection.rows[table_name])
            if self.connection.tamper_final_read and table_name == "source_record":
                self.current_rows = []

    def fetchall(self) -> list[object]:
        return self.current_rows


class FakeRestoreConnection:
    def __init__(
        self,
        rows: dict[str, list[object]],
        *,
        fail_on: str | None = None,
        tamper_final_read: bool = False,
    ) -> None:
        self.rows = {name: list(table_rows) for name, table_rows in rows.items()}
        self.fail_on = fail_on
        self.tamper_final_read = tamper_final_read
        self.cursor_instance = FakeRestoreCursor(self)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeRestoreCursor:
        return self.cursor_instance

    @contextmanager
    def transaction(self):
        original = {name: list(rows) for name, rows in self.rows.items()}
        try:
            yield
        except Exception:
            self.rows = original
            self.rollbacks += 1
            raise
        else:
            self.commits += 1


def _restore_approval(snapshot: FoundationSnapshot, *, action: str = "restore_snapshot") -> RefreshApproval:
    fingerprints = {field: f"{index:064x}" for index, field in enumerate(APPROVAL_FINGERPRINT_FIELDS, start=1)}
    fingerprints.update(
        snapshot_digest=snapshot.digest,
        schema_fingerprint=snapshot.schema_fingerprint,
        database_fingerprint=snapshot.database_fingerprint,
        table_fingerprint=foundation_schema_fingerprint(),
    )
    return RefreshApproval(
        action=action,
        approved_by="Wes",
        user_go_reference="conversation:restore-approved",
        fingerprints=fingerprints,
        prefix_fingerprints={"approved-source-loads": "f" * 64},
    )


def _restore_snapshot() -> FoundationSnapshot:
    tables = {table.name: () for table in FOUNDATION_TABLES}
    tables["source_record"] = (
        {"source_record_id": "restore:source", "source_system": "test", "source_type": "fixture", "source_locator": "fixture", "fetched_at": None, "raw_payload": {"ok": True}},
    )
    tables["player"] = (
        {"player_id": "restore:player", "display_name": "Restore Player", "nba_player_ref": None, "birth_date": None, "position_text": None},
    )
    return FoundationSnapshot(
        tables=tables,
        schema_fingerprint=foundation_schema_fingerprint(),
        database_fingerprint=logical_database_fingerprint(database_name="nba", server_version=170002),
    )


def test_restore_requires_separate_snapshot_bound_approval_before_delete() -> None:
    snapshot = _restore_snapshot()
    approval = _restore_approval(snapshot, action="execute_refresh")
    connection = FakeRestoreConnection({table.name: [{"unexpected": True}] for table in FOUNDATION_TABLES})
    with pytest.raises(RefreshSafetyError, match="does not authorize"):
        restore_approved_foundation_snapshot(
            connection, approval=approval, snapshot=snapshot,
            current_fingerprints=approval.fingerprints, current_prefix_fingerprints=approval.prefix_fingerprints,
        )
    assert not connection.cursor_instance.queries


@pytest.mark.parametrize("field", ["snapshot_digest", "schema_fingerprint", "database_fingerprint"])
def test_restore_rejects_mismatched_snapshot_identity_before_delete(field: str) -> None:
    snapshot = _restore_snapshot()
    approval = _restore_approval(snapshot)
    current = dict(approval.fingerprints)
    current[field] = "0" * 64
    connection = FakeRestoreConnection({table.name: [{"unexpected": True}] for table in FOUNDATION_TABLES})
    with pytest.raises(RefreshSafetyError):
        restore_approved_foundation_snapshot(
            connection, approval=approval, snapshot=snapshot,
            current_fingerprints=current, current_prefix_fingerprints=approval.prefix_fingerprints,
        )
    assert not connection.cursor_instance.queries


def test_restore_uses_fixed_orders_and_commits_only_exact_snapshot() -> None:
    snapshot = _restore_snapshot()
    approval = _restore_approval(snapshot)
    connection = FakeRestoreConnection({table.name: [{"unexpected": True}] for table in FOUNDATION_TABLES})
    restored = restore_approved_foundation_snapshot(
        connection, approval=approval, snapshot=snapshot,
        current_fingerprints=approval.fingerprints, current_prefix_fingerprints=approval.prefix_fingerprints,
    )
    assert restored.digest == snapshot.digest
    deletes = [query for query in connection.cursor_instance.queries if query.startswith("DELETE")]
    assert deletes == [f"DELETE FROM foundation.{name}" for name in DELETE_ORDER]
    inserts = [query for query in connection.cursor_instance.queries if query.startswith("INSERT")]
    assert [query.split("foundation.", 1)[1].split(" ", 1)[0] for query in inserts] == ["source_record", "player"]
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_restore_rolls_back_when_a_manifest_insert_or_final_checksum_fails() -> None:
    snapshot = _restore_snapshot()
    approval = _restore_approval(snapshot)
    initial = {table.name: [{"unexpected": True}] for table in FOUNDATION_TABLES}
    connection = FakeRestoreConnection(initial, fail_on="INSERT INTO foundation.player")
    with pytest.raises(RuntimeError, match="restore write failed"):
        restore_approved_foundation_snapshot(
            connection, approval=approval, snapshot=snapshot,
            current_fingerprints=approval.fingerprints, current_prefix_fingerprints=approval.prefix_fingerprints,
        )
    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert connection.rows == initial

    checksum_connection = FakeRestoreConnection(initial, tamper_final_read=True)
    with pytest.raises(RefreshSafetyError, match="digest"):
        restore_approved_foundation_snapshot(
            checksum_connection, approval=approval, snapshot=snapshot,
            current_fingerprints=approval.fingerprints, current_prefix_fingerprints=approval.prefix_fingerprints,
        )
    assert checksum_connection.rollbacks == 1
    assert checksum_connection.commits == 0
    assert checksum_connection.rows == initial
