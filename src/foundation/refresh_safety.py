"""Closed local artifacts and read-only foundation preimage snapshots.

The safety surface intentionally has no database URL or configuration loader.
Callers supply an already-open connection, while this module limits every query
to the fixed foundation manifest and never emits credentials into an artifact.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Callable, Mapping, Protocol, Sequence
import re
import stat
import uuid
from importlib.metadata import PackageNotFoundError, version

from foundation.foundation_table_manifest import (
    DELETE_ORDER,
    FOUNDATION_TABLES,
    RESTORE_INSERT_ORDER,
    TABLE_BY_NAME,
    foundation_schema_contract,
)
from foundation.refresh_mutations import FoundationMutationPlan, execute_plan
from foundation.refresh_projection import APPROVED_PROJECTION_ORDER


REFRESH_SNAPSHOT_SCHEMA_VERSION = "foundation_refresh_snapshot_v1"
REFRESH_APPROVAL_SCHEMA_VERSION = "refresh_approval_v1"
REFRESH_EXECUTION_STATE_SCHEMA_VERSION = "refresh_execution_state_v1"
SNAPSHOT_FILE_NAME = "foundation-snapshot.json"
APPROVAL_FILE_NAME = "refresh-approval.json"
EXECUTION_STATE_FILE_NAME = "refresh-execution-state.json"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REFRESH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_DATABASE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")

# This is deliberately explicit rather than an open-ended map.  A reviewed
# approval may not gain authority merely because a future caller adds a field.
APPROVAL_FINGERPRINT_FIELDS = (
    "baseline_digest",
    "payload_digest",
    "fixture_digest",
    "projection_digest",
    "reconciliation_digest",
    "snapshot_digest",
    "table_fingerprint",
    "schema_fingerprint",
    "database_fingerprint",
    "plan_fingerprint",
    "implementation_fingerprint",
    "environment_fingerprint",
    "dirty_tree_fingerprint",
)
APPROVAL_ACTIONS = frozenset({"execute_refresh", "restore_snapshot"})
EXECUTION_STATUSES = frozenset({"pending", "running", "failed", "needs_restore", "completed"})
RUNNER_STEP_NAMES = APPROVED_PROJECTION_ORDER
RUNNER_PREFIX_KEYS = ("baseline", *(f"prefix-{index:02d}" for index in range(1, len(RUNNER_STEP_NAMES) + 1)))


class RefreshSafetyError(ValueError):
    """Raised when a safety artifact or read-only snapshot is unsafe."""


class RefreshExecutionError(RefreshSafetyError):
    """Raised when an approved refresh cannot safely proceed or resume."""


class SnapshotCursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...

    def fetchall(self) -> Sequence[object]: ...

    def __enter__(self) -> "SnapshotCursor": ...

    def __exit__(self, *args: object) -> None: ...


class SnapshotConnection(Protocol):
    def cursor(self) -> SnapshotCursor: ...

    def rollback(self) -> None: ...


class RestoreConnection(Protocol):
    """Closed restore connection surface; table names never come from callers."""

    def cursor(self) -> SnapshotCursor: ...

    def transaction(self) -> Any: ...


@dataclass(frozen=True)
class FoundationSnapshot:
    """An in-memory exact preimage of the closed 21-table foundation surface."""

    tables: Mapping[str, tuple[Mapping[str, object], ...]]
    schema_fingerprint: str
    database_fingerprint: str

    @property
    def digest(self) -> str:
        return canonical_safety_digest("foundation-snapshot", snapshot_payload(self, include_digest=False))


@dataclass(frozen=True)
class RefreshApproval:
    """A human-recorded, closed approval for exactly one destructive action."""

    action: str
    approved_by: str
    user_go_reference: str
    fingerprints: Mapping[str, str]
    prefix_fingerprints: Mapping[str, str]

    @property
    def digest(self) -> str:
        return canonical_safety_digest("refresh-approval", refresh_approval_payload(self, include_digest=False))


@dataclass(frozen=True)
class RefreshExecutionState:
    """Closed, monotonic local record of one approved forward refresh."""

    approval_digest: str
    sequence: int
    status: str
    step_index: int
    receipts: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True)
class ApprovedRefreshStep:
    """One immutable plan bound to its closed runner-step identity."""

    name: str
    plan: FoundationMutationPlan


@dataclass(frozen=True)
class ApprovedRefreshPlans:
    """The complete ordered, labeled plan set accepted by the forward runner."""

    steps: tuple[ApprovedRefreshStep, ...]

    def __post_init__(self) -> None:
        _validate_approved_refresh_plans(self)


def refresh_approval_payload(approval: RefreshApproval, *, include_digest: bool = True) -> dict[str, object]:
    """Serialize a closed approval without ever manufacturing user consent."""

    _validate_refresh_approval(approval)
    payload: dict[str, object] = {
        "schema_version": REFRESH_APPROVAL_SCHEMA_VERSION,
        "action": approval.action,
        "approved_by": approval.approved_by,
        "user_go_reference": approval.user_go_reference,
        "fingerprints": {field: approval.fingerprints[field] for field in APPROVAL_FINGERPRINT_FIELDS},
        "prefix_fingerprints": dict(sorted(approval.prefix_fingerprints.items())),
    }
    if include_digest:
        payload["approval_sha256"] = canonical_safety_digest("refresh-approval", payload)
    return payload


def write_refresh_approval(artifact_directory: Path, approval: RefreshApproval) -> Path:
    """Persist a caller-supplied approval once; this function cannot create one."""

    _validate_private_directory(artifact_directory)
    target = artifact_directory / APPROVAL_FILE_NAME
    if target.exists() or target.is_symlink():
        raise RefreshSafetyError("Refusing to overwrite an existing refresh approval")
    _write_exclusive_atomic(target, _canonical_artifact_bytes(refresh_approval_payload(approval)))
    return target


def load_refresh_approval(path: Path, *, expected_digest: str | None = None) -> RefreshApproval:
    if path.name != APPROVAL_FILE_NAME or path.is_symlink() or not path.is_file():
        raise RefreshSafetyError("Refresh approval path is unsafe")
    _validate_private_directory(path.parent)
    info = path.lstat()
    if info.st_mode & 0o077 or info.st_nlink != 1:
        raise RefreshSafetyError("Refresh approval mode or link count is unsafe")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RefreshSafetyError("Refresh approval is not valid UTF-8 JSON") from error
    if raw != _canonical_artifact_bytes(payload):
        raise RefreshSafetyError("Refresh approval is not canonically encoded")
    approval = _approval_from_payload(payload)
    if payload.get("approval_sha256") != approval.digest or (expected_digest is not None and expected_digest != approval.digest):
        raise RefreshSafetyError("Refresh approval digest does not match expected immutable payload")
    return approval


def parse_refresh_approval_payload(payload: object) -> RefreshApproval:
    """Validate a user-supplied closed approval payload without recording it."""

    approval = _approval_from_payload(payload)
    if not isinstance(payload, Mapping) or payload.get("approval_sha256") != approval.digest:
        raise RefreshSafetyError("Refresh approval digest does not match immutable payload")
    return approval


def preflight_refresh_approval(
    approval: RefreshApproval,
    *,
    action: str,
    current_fingerprints: Mapping[str, str],
    current_prefix_fingerprints: Mapping[str, str],
) -> RefreshApproval:
    """Validate every approval binding before a caller opens a write connection.

    This pure function is the only T8 preflight seam.  Future runner and
    restore code must call it before acquiring any write-capable resource.
    """

    _validate_refresh_approval(approval)
    if action not in APPROVAL_ACTIONS or approval.action != action:
        raise RefreshSafetyError("Refresh approval action does not authorize this operation")
    _validate_fingerprint_mapping(current_fingerprints, "current approval fingerprints")
    _validate_prefix_fingerprints(current_prefix_fingerprints)
    if dict(current_fingerprints) != dict(approval.fingerprints):
        raise RefreshSafetyError("Refresh approval fingerprints are stale or mismatched")
    if dict(current_prefix_fingerprints) != dict(approval.prefix_fingerprints):
        raise RefreshSafetyError("Refresh approval prefix fingerprints are stale or mismatched")
    return approval


def refresh_execution_state_payload(state: RefreshExecutionState) -> dict[str, object]:
    """Serialize the closed execution-state record for atomic local persistence."""

    _validate_execution_state(state)
    return {
        "schema_version": REFRESH_EXECUTION_STATE_SCHEMA_VERSION,
        "approval_digest": state.approval_digest,
        "sequence": state.sequence,
        "status": state.status,
        "step_index": state.step_index,
        "receipts": [dict(receipt) for receipt in state.receipts],
    }


def load_refresh_execution_state(path: Path) -> RefreshExecutionState:
    """Load a canonical, restricted execution state without accepting extra fields."""

    if path.name != EXECUTION_STATE_FILE_NAME or path.is_symlink() or not path.is_file():
        raise RefreshExecutionError("Refresh execution-state path is unsafe")
    _validate_private_directory(path.parent)
    info = path.lstat()
    if info.st_mode & 0o077 or info.st_nlink != 1:
        raise RefreshExecutionError("Refresh execution-state mode or link count is unsafe")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RefreshExecutionError("Refresh execution state is not valid UTF-8 JSON") from error
    if raw != _canonical_artifact_bytes(payload):
        raise RefreshExecutionError("Refresh execution state is not canonically encoded")
    required = {"schema_version", "approval_digest", "sequence", "status", "step_index", "receipts"}
    if not isinstance(payload, dict) or set(payload) != required or payload["schema_version"] != REFRESH_EXECUTION_STATE_SCHEMA_VERSION:
        raise RefreshExecutionError("Refresh execution state does not match the closed schema")
    state = RefreshExecutionState(
        approval_digest=payload["approval_digest"],
        sequence=payload["sequence"],
        status=payload["status"],
        step_index=payload["step_index"],
        receipts=tuple(payload["receipts"]) if isinstance(payload["receipts"], list) else (),
    )
    _validate_execution_state(state)
    return state


def run_approved_foundation_refresh(
    connection: Any,
    *,
    approval: RefreshApproval,
    current_fingerprints: Mapping[str, str],
    current_prefix_fingerprints: Mapping[str, str],
    plans: ApprovedRefreshPlans,
    execution_state_path: Path,
    prefix_fingerprint_reader: Callable[[Any], str],
) -> RefreshExecutionState:
    """Run or resume the one approved sequence; subsets and reordered steps do not exist.

    ``prefix_fingerprint_reader`` is deliberately injected by the later command
    adapter.  It must read the closed foundation surface and return the same
    digest algorithm used by the approved projection; this module never accepts
    a generic table or SQL selector from a caller.
    """

    # Repeat the closed-plan check at the runner boundary.  This stays ahead of
    # execution-state creation, advisory locking, transactions, and mutations
    # even if an in-process caller has bypassed dataclass immutability.
    _validate_approved_refresh_plans(plans)
    _validate_runner_approval(approval, current_fingerprints, current_prefix_fingerprints)
    if execution_state_path.exists():
        state = load_refresh_execution_state(execution_state_path)
        if state.approval_digest != approval.digest:
            raise RefreshExecutionError("Execution state belongs to a different approval")
    else:
        _validate_private_directory(execution_state_path.parent)
        state = RefreshExecutionState(approval.digest, 0, "pending", 0)
        _write_execution_state(execution_state_path, state, previous_sequence=None)

    if state.status == "completed":
        return state
    if state.status == "needs_restore":
        raise RefreshExecutionError("Refresh state requires separately approved restore")

    _acquire_refresh_lock(connection)
    try:
        while state.step_index < len(RUNNER_STEP_NAMES):
            step_index = state.step_index
            expected_pre = approval.prefix_fingerprints[RUNNER_PREFIX_KEYS[step_index]]
            expected_post = approval.prefix_fingerprints[RUNNER_PREFIX_KEYS[step_index + 1]]
            actual = prefix_fingerprint_reader(connection)

            if state.status in {"running", "failed"}:
                if actual == expected_post:
                    state = _transition_execution_state(state, "pending", step_index + 1, "recovered")
                    _write_execution_state(execution_state_path, state, previous_sequence=state.sequence - 1)
                    continue
                if actual != expected_pre:
                    state = _transition_execution_state(state, "needs_restore", step_index, "unexpected-prefix")
                    _write_execution_state(execution_state_path, state, previous_sequence=state.sequence - 1)
                    raise RefreshExecutionError("Interrupted refresh no longer matches an approved prefix; restore is required")
            elif actual != expected_pre:
                state = _transition_execution_state(state, "needs_restore", step_index, "unexpected-prefix")
                _write_execution_state(execution_state_path, state, previous_sequence=state.sequence - 1)
                raise RefreshExecutionError("Refresh database state does not match the approved pre-prefix")

            state = _transition_execution_state(state, "running", step_index, "started")
            _write_execution_state(execution_state_path, state, previous_sequence=state.sequence - 1)
            try:
                _execute_plan_transactionally(connection, plans.steps[step_index].plan)
            except Exception:
                state = _transition_execution_state(state, "failed", step_index, "transaction-failed")
                _write_execution_state(execution_state_path, state, previous_sequence=state.sequence - 1)
                raise

            actual = prefix_fingerprint_reader(connection)
            if actual != expected_post:
                state = _transition_execution_state(state, "needs_restore", step_index, "post-prefix-mismatch")
                _write_execution_state(execution_state_path, state, previous_sequence=state.sequence - 1)
                raise RefreshExecutionError("Committed refresh step does not match its approved post-prefix")
            state = _transition_execution_state(state, "pending", step_index + 1, "committed")
            _write_execution_state(execution_state_path, state, previous_sequence=state.sequence - 1)

        state = _transition_execution_state(state, "completed", len(RUNNER_STEP_NAMES), "completed")
        _write_execution_state(execution_state_path, state, previous_sequence=state.sequence - 1)
        return state
    finally:
        _release_refresh_lock(connection)


def implementation_fingerprint(repo_root: Path) -> str:
    """Hash reviewed code/config bytes, including untracked and deleted entries."""

    root = _repository_root(repo_root)
    tracked = _git_lines(root, "ls-files", "-z")
    statuses = _git_lines(root, "status", "--porcelain=v1", "-z")
    paths = set(tracked)
    deleted: set[str] = set()
    for entry in statuses:
        status, path = entry[:2], entry[3:]
        if "D" in status:
            deleted.add(path)
        paths.add(path)
    records = []
    for path in sorted(paths):
        if not _implementation_path(path):
            continue
        if path in deleted:
            body = _git_bytes(root, "show", f"HEAD:{path}")
            state = "deleted"
        else:
            candidate = root / path
            if not candidate.is_file() or candidate.is_symlink():
                continue
            body, state = candidate.read_bytes(), "present"
        records.append({"path": path, "state": state, "sha256": sha256(body).hexdigest()})
    return canonical_safety_digest("implementation", {"head": _git_head(root), "files": records})


def environment_fingerprint(repo_root: Path) -> str:
    """Hash version facts only; environment variables and DSNs are never read."""

    root = _repository_root(repo_root)
    lock = root / "uv.lock"
    lock_digest = sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None
    packages = {}
    for package in ("psycopg", "pydantic", "PyYAML"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    return canonical_safety_digest("environment", {
        "python_implementation": platform.python_implementation(), "python_version": platform.python_version(),
        "os_family": platform.system(), "architecture": platform.machine(), "byteorder": sys.byteorder,
        "packages": packages, "uv_lock_sha256": lock_digest,
    })


def dirty_tree_fingerprint(repo_root: Path) -> str:
    """Hash every nonignored Git change outside tmp/, never its environment."""

    root = _repository_root(repo_root)
    records = []
    for entry in _git_lines(root, "status", "--porcelain=v1", "-z"):
        status, path = entry[:2], entry[3:]
        if path == "tmp" or path.startswith("tmp/"):
            continue
        candidate = root / path
        if candidate.is_symlink():
            digest = sha256(os.readlink(candidate).encode("utf-8")).hexdigest()
            kind = "symlink"
        elif candidate.is_file():
            digest, kind = sha256(candidate.read_bytes()).hexdigest(), "file"
        elif "D" in status:
            digest, kind = sha256(_git_bytes(root, "show", f"HEAD:{path}")).hexdigest(), "deleted"
        else:
            digest, kind = None, "missing"
        records.append({"status": status, "path": path, "kind": kind, "sha256": digest})
    return canonical_safety_digest("dirty-tree", {"head": _git_head(root), "changes": records})


def canonical_safety_bytes(value: object) -> bytes:
    """Encode closed tagged database values as deterministic UTF-8 JSON."""

    return json.dumps(
        canonical_database_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_safety_digest(domain: str, value: object) -> str:
    if not isinstance(domain, str) or not re.fullmatch(r"[a-z0-9._-]+", domain):
        raise RefreshSafetyError("Safety digest domain is invalid")
    return sha256(
        f"nba-asset-lineage:refresh-safety:{domain}:v1\0".encode("ascii") + canonical_safety_bytes(value)
    ).hexdigest()


def canonical_database_value(value: object) -> dict[str, object]:
    """Represent only accepted database value types; never silently stringify."""

    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise RefreshSafetyError("Non-finite floats are not snapshot-safe")
        return {"type": "float", "value": value.hex()}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise RefreshSafetyError("Snapshot datetimes must have a timezone")
        return {
            "type": "datetime",
            "value": value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        }
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, bytes):
        return {"type": "bytes", "base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise RefreshSafetyError("Snapshot JSON object keys must be strings")
        return {"type": "object", "value": {key: canonical_database_value(item) for key, item in value.items()}}
    if isinstance(value, (tuple, list)):
        return {"type": "array", "value": [canonical_database_value(item) for item in value]}
    raise RefreshSafetyError(f"Unsupported snapshot database value: {type(value).__name__}")


def foundation_schema_fingerprint() -> str:
    return canonical_safety_digest("foundation-schema", foundation_schema_contract())


def logical_database_fingerprint(*, database_name: str, server_version: int) -> str:
    """Hash only a constrained logical identity, never a DSN, role, or secret."""

    if not isinstance(database_name, str) or not _DATABASE_NAME.fullmatch(database_name):
        raise RefreshSafetyError("Database name is not a safe logical identifier")
    if not isinstance(server_version, int) or server_version <= 0:
        raise RefreshSafetyError("Database server version is invalid")
    return canonical_safety_digest(
        "logical-database", {"database_name": database_name, "server_version": server_version}
    )


def capture_foundation_snapshot(
    connection: SnapshotConnection,
    *,
    database_fingerprint: str,
) -> FoundationSnapshot:
    """Read all and only manifest tables in one repeatable-read read-only transaction."""

    _require_digest(database_fingerprint, "database fingerprint")
    rows_by_table: dict[str, tuple[Mapping[str, object], ...]] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            for table in FOUNDATION_TABLES:
                columns = ", ".join(table.columns)
                ordering = ", ".join(table.key_columns)
                cursor.execute(f"SELECT {columns} FROM foundation.{table.name} ORDER BY {ordering}")
                rows_by_table[table.name] = _normalize_rows(cursor.fetchall(), table.name, table.columns)
    finally:
        # A rollback closes the transaction without persisting any session work.
        connection.rollback()
    return FoundationSnapshot(
        tables=rows_by_table,
        schema_fingerprint=foundation_schema_fingerprint(),
        database_fingerprint=database_fingerprint,
    )


def snapshot_payload(snapshot: FoundationSnapshot, *, include_digest: bool = True) -> dict[str, object]:
    _validate_snapshot(snapshot)
    payload: dict[str, object] = {
        "schema_version": REFRESH_SNAPSHOT_SCHEMA_VERSION,
        "schema_fingerprint": snapshot.schema_fingerprint,
        "database_fingerprint": snapshot.database_fingerprint,
        "tables": [
            {
                "name": table.name,
                "rows": [
                    {column: canonical_database_value(row[column]) for column in table.columns}
                    for row in snapshot.tables[table.name]
                ],
            }
            for table in FOUNDATION_TABLES
        ],
    }
    if include_digest:
        payload["snapshot_sha256"] = canonical_safety_digest("foundation-snapshot", payload)
    return payload


def write_foundation_snapshot(artifact_directory: Path, snapshot: FoundationSnapshot) -> Path:
    """Publish one verified snapshot in a repository-derived private refresh directory."""

    _validate_private_directory(artifact_directory)
    target = artifact_directory / SNAPSHOT_FILE_NAME
    if target.exists() or target.is_symlink():
        raise RefreshSafetyError("Refusing to overwrite an existing foundation snapshot")
    body = _canonical_artifact_bytes(snapshot_payload(snapshot))
    _write_exclusive_atomic(target, body)
    return target


def create_refresh_artifact_directory(repo_root: Path, refresh_id: str) -> Path:
    """Create exactly ``<repo-root>/tmp/<refresh-id>`` with restrictive permissions."""

    if not _REFRESH_ID.fullmatch(refresh_id):
        raise RefreshSafetyError("Refresh identifier is unsafe")
    # Repository roots and their existing tmp/ parents are commonly group/world
    # readable.  Privacy is required for the newly-created operational leaf and
    # its contents, not for the checkout itself.  Both ancestors remain real
    # directories so a symlink can never redirect the restricted leaf.
    _validate_real_directory(repo_root)
    temporary_root = repo_root / "tmp"
    if temporary_root.exists() or temporary_root.is_symlink():
        _validate_real_directory(temporary_root)
    else:
        os.mkdir(temporary_root, 0o700)
        _validate_private_directory(temporary_root)
    destination = temporary_root / refresh_id
    if destination.exists() or destination.is_symlink():
        raise RefreshSafetyError("Refusing to overwrite an existing refresh artifact directory")
    os.mkdir(destination, 0o700)
    _validate_private_directory(destination)
    return destination


def validate_refresh_repository_root(repo_root: Path) -> Path:
    """Return a real Git checkout root suitable for refresh capture.

    Snapshot capture starts with a caller-provided repository path, before an
    artifact leaf exists.  Treat that path as an authority boundary just as
    strictly as an existing artifact directory: neither the root nor its Git
    metadata may be a symlink, and the metadata must identify a checkout.
    """

    root = Path(os.path.abspath(repo_root))
    _validate_real_directory(root)
    git_metadata = root / ".git"
    try:
        git_info = git_metadata.lstat()
    except OSError as error:
        raise RefreshSafetyError("Refresh repository root is not a Git checkout") from error
    if git_metadata.is_symlink() or not (stat.S_ISDIR(git_info.st_mode) or stat.S_ISREG(git_info.st_mode)):
        raise RefreshSafetyError("Refresh repository metadata is unsafe")
    # A .git sentinel is not proof of a checkout: an empty directory and a
    # malformed worktree file are both forgeable.  Ask Git itself for the
    # checkout top-level without a shell, then require it to be exactly the
    # caller's non-symlink directory.  This admits a legitimate worktree only
    # when Git proves that the requested directory is its worktree root.
    git_environment = {
        name: value
        for name, value in os.environ.items()
        if name not in {"GIT_DIR", "GIT_WORK_TREE"}
    }
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        check=False,
        capture_output=True,
        env=git_environment,
    )
    if result.returncode:
        raise RefreshSafetyError("Refresh repository root is not an authentic Git checkout")
    try:
        git_root = Path(os.path.abspath(result.stdout.decode("utf-8").strip()))
    except UnicodeDecodeError as error:
        raise RefreshSafetyError("Refresh repository root Git probe returned invalid output") from error
    if git_root != root:
        raise RefreshSafetyError("Refresh repository root is not the exact Git checkout top-level")
    return root


def validate_refresh_artifact_directory(artifact_directory: Path) -> Path:
    """Return the real repository root for one existing operational leaf.

    The command-facing artifact directory is an authority boundary: it must be
    the actual ``<repo>/tmp/<refresh-id>`` leaf created for a refresh, not just
    a private directory that happens to contain plausible JSON.  Check every
    ancestor with ``lstat`` rather than resolving through a possible symlink.
    This validation is intentionally usable before a caller looks up a DSN or
    opens a connection.
    """

    directory = Path(os.path.abspath(artifact_directory))
    if not _REFRESH_ID.fullmatch(directory.name) or directory.parent.name != "tmp":
        raise RefreshSafetyError("Artifact directory must be a repo-local tmp/<refresh-id> leaf")
    repository_root = directory.parent.parent
    repository_root = validate_refresh_repository_root(repository_root)
    _validate_real_directory(directory.parent)
    _validate_private_directory(directory)
    return repository_root


def load_foundation_snapshot(path: Path, *, expected_digest: str | None = None) -> FoundationSnapshot:
    """Fail closed when a restricted snapshot is changed, malformed, or unsafe."""

    if path.name != SNAPSHOT_FILE_NAME or path.is_symlink() or not path.is_file():
        raise RefreshSafetyError("Foundation snapshot path is unsafe")
    _validate_private_directory(path.parent)
    info = path.lstat()
    if info.st_mode & 0o077 or info.st_nlink != 1:
        raise RefreshSafetyError("Foundation snapshot mode or link count is unsafe")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RefreshSafetyError("Foundation snapshot is not valid UTF-8 JSON") from error
    if raw != _canonical_artifact_bytes(payload):
        raise RefreshSafetyError("Foundation snapshot is not canonically encoded")
    snapshot = _snapshot_from_payload(payload)
    digest = snapshot.digest
    if payload.get("snapshot_sha256") != digest or (expected_digest is not None and expected_digest != digest):
        raise RefreshSafetyError("Foundation snapshot digest does not match expected immutable payload")
    return snapshot


def restore_approved_foundation_snapshot(
    connection: RestoreConnection,
    *,
    approval: RefreshApproval,
    snapshot: FoundationSnapshot,
    current_fingerprints: Mapping[str, str],
    current_prefix_fingerprints: Mapping[str, str],
) -> FoundationSnapshot:
    """Restore one separately approved full preimage through the closed manifest.

    Every authorization and identity check occurs before a transaction is
    opened.  The destructive portion is then deliberately small: remove the
    fixed child-to-parent order, replay the fixed parent-to-child order, and
    prove the final full-table digest before the transaction can commit.
    """

    _validate_snapshot(snapshot)
    preflight_refresh_approval(
        approval,
        action="restore_snapshot",
        current_fingerprints=current_fingerprints,
        current_prefix_fingerprints=current_prefix_fingerprints,
    )
    _validate_restore_snapshot_binding(approval, snapshot)

    transaction = getattr(connection, "transaction", None)
    if not callable(transaction):
        raise RefreshSafetyError("Restore connection does not expose a transaction adapter")

    with transaction():
        with connection.cursor() as cursor:
            for table_name in DELETE_ORDER:
                cursor.execute(f"DELETE FROM foundation.{table_name}")
            for table_name in RESTORE_INSERT_ORDER:
                table = TABLE_BY_NAME[table_name]
                if not snapshot.tables[table_name]:
                    continue
                columns = ", ".join(table.columns)
                placeholders = ", ".join("%s" for _ in table.columns)
                statement = f"INSERT INTO foundation.{table.name} ({columns}) VALUES ({placeholders})"
                for row in snapshot.tables[table_name]:
                    cursor.execute(statement, tuple(row[column] for column in table.columns))
            restored = FoundationSnapshot(
                tables=_read_snapshot_tables(cursor),
                schema_fingerprint=snapshot.schema_fingerprint,
                database_fingerprint=snapshot.database_fingerprint,
            )
            if restored.digest != snapshot.digest:
                raise RefreshSafetyError("Restored foundation digest does not match approved snapshot")
    return snapshot


def _normalize_rows(rows: Sequence[object], table_name: str, columns: tuple[str, ...]) -> tuple[Mapping[str, object], ...]:
    normalized: list[Mapping[str, object]] = []
    for row in rows:
        if isinstance(row, Mapping):
            if set(row) != set(columns):
                raise RefreshSafetyError(f"Snapshot row columns do not match {table_name}")
            normalized.append({column: row[column] for column in columns})
        elif isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
            if len(row) != len(columns):
                raise RefreshSafetyError(f"Snapshot row width does not match {table_name}")
            normalized.append(dict(zip(columns, row, strict=True)))
        else:
            raise RefreshSafetyError(f"Snapshot row type is unsupported for {table_name}")
    return tuple(normalized)


def _read_snapshot_tables(cursor: SnapshotCursor) -> dict[str, tuple[Mapping[str, object], ...]]:
    """Read the immutable manifest without starting or ending a transaction."""

    rows_by_table: dict[str, tuple[Mapping[str, object], ...]] = {}
    for table in FOUNDATION_TABLES:
        columns = ", ".join(table.columns)
        ordering = ", ".join(table.key_columns)
        cursor.execute(f"SELECT {columns} FROM foundation.{table.name} ORDER BY {ordering}")
        rows_by_table[table.name] = _normalize_rows(cursor.fetchall(), table.name, table.columns)
    return rows_by_table


def _validate_snapshot(snapshot: FoundationSnapshot) -> None:
    _require_digest(snapshot.schema_fingerprint, "schema fingerprint")
    _require_digest(snapshot.database_fingerprint, "database fingerprint")
    if snapshot.schema_fingerprint != foundation_schema_fingerprint():
        raise RefreshSafetyError("Foundation snapshot schema fingerprint is stale")
    if set(snapshot.tables) != {table.name for table in FOUNDATION_TABLES}:
        raise RefreshSafetyError("Foundation snapshot tables do not match the closed manifest")
    for table in FOUNDATION_TABLES:
        for row in snapshot.tables[table.name]:
            if not isinstance(row, Mapping) or set(row) != set(table.columns):
                raise RefreshSafetyError(f"Foundation snapshot row does not match {table.name}")
            for column in table.columns:
                canonical_database_value(row[column])


def _validate_restore_snapshot_binding(approval: RefreshApproval, snapshot: FoundationSnapshot) -> None:
    """Bind the destructive action to this exact artifact and closed manifest."""

    expected = {
        "snapshot_digest": snapshot.digest,
        "schema_fingerprint": snapshot.schema_fingerprint,
        "database_fingerprint": snapshot.database_fingerprint,
        "table_fingerprint": foundation_schema_fingerprint(),
    }
    for field, value in expected.items():
        if approval.fingerprints[field] != value:
            raise RefreshSafetyError(f"Restore approval {field} does not match approved snapshot")


def _snapshot_from_payload(payload: object) -> FoundationSnapshot:
    required = {"schema_version", "schema_fingerprint", "database_fingerprint", "tables", "snapshot_sha256"}
    if not isinstance(payload, dict) or set(payload) != required or payload.get("schema_version") != REFRESH_SNAPSHOT_SCHEMA_VERSION:
        raise RefreshSafetyError("Foundation snapshot does not match the closed schema")
    tables_payload = payload["tables"]
    if not isinstance(tables_payload, list) or len(tables_payload) != len(FOUNDATION_TABLES):
        raise RefreshSafetyError("Foundation snapshot table payload is invalid")
    tables: dict[str, tuple[Mapping[str, object], ...]] = {}
    for expected, actual in zip(FOUNDATION_TABLES, tables_payload, strict=True):
        if not isinstance(actual, dict) or set(actual) != {"name", "rows"} or actual["name"] != expected.name:
            raise RefreshSafetyError("Foundation snapshot table order is invalid")
        if not isinstance(actual["rows"], list):
            raise RefreshSafetyError("Foundation snapshot rows are invalid")
        decoded_rows: list[Mapping[str, object]] = []
        for raw_row in actual["rows"]:
            if not isinstance(raw_row, dict) or set(raw_row) != set(expected.columns):
                raise RefreshSafetyError(f"Foundation snapshot row does not match {expected.name}")
            decoded_rows.append({column: _decode_database_value(raw_row[column]) for column in expected.columns})
        tables[expected.name] = tuple(decoded_rows)
    snapshot = FoundationSnapshot(
        tables=tables,
        schema_fingerprint=payload["schema_fingerprint"],
        database_fingerprint=payload["database_fingerprint"],
    )
    _validate_snapshot(snapshot)
    return snapshot


def _approval_from_payload(payload: object) -> RefreshApproval:
    required = {
        "schema_version", "action", "approved_by", "user_go_reference", "fingerprints", "prefix_fingerprints", "approval_sha256"
    }
    if not isinstance(payload, dict) or set(payload) != required or payload.get("schema_version") != REFRESH_APPROVAL_SCHEMA_VERSION:
        raise RefreshSafetyError("Refresh approval does not match the closed schema")
    approval = RefreshApproval(
        action=payload["action"], approved_by=payload["approved_by"], user_go_reference=payload["user_go_reference"],
        fingerprints=payload["fingerprints"], prefix_fingerprints=payload["prefix_fingerprints"],
    )
    _validate_refresh_approval(approval)
    return approval


def _validate_refresh_approval(approval: RefreshApproval) -> None:
    if approval.action not in APPROVAL_ACTIONS:
        raise RefreshSafetyError("Refresh approval action is invalid")
    for label, value in (("approved_by", approval.approved_by), ("user_go_reference", approval.user_go_reference)):
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise RefreshSafetyError(f"Refresh approval {label} is invalid")
    _validate_fingerprint_mapping(approval.fingerprints, "approval fingerprints")
    _validate_prefix_fingerprints(approval.prefix_fingerprints)


def _validate_fingerprint_mapping(value: Mapping[str, str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != set(APPROVAL_FINGERPRINT_FIELDS):
        raise RefreshSafetyError(f"{label} do not match the closed schema")
    for field in APPROVAL_FINGERPRINT_FIELDS:
        _require_digest(value[field], field)


def _validate_prefix_fingerprints(value: Mapping[str, str]) -> None:
    if not isinstance(value, Mapping) or not value or any(not isinstance(name, str) or not name for name in value):
        raise RefreshSafetyError("Refresh approval prefix fingerprints are invalid")
    for name, digest in value.items():
        _require_digest(digest, f"prefix fingerprint {name}")


def _validate_runner_approval(
    approval: RefreshApproval,
    current_fingerprints: Mapping[str, str],
    current_prefix_fingerprints: Mapping[str, str],
) -> None:
    if tuple(current_prefix_fingerprints) != RUNNER_PREFIX_KEYS or tuple(approval.prefix_fingerprints) != RUNNER_PREFIX_KEYS:
        raise RefreshExecutionError("Approved runner prefix evidence must cover the fixed closed order")
    preflight_refresh_approval(
        approval,
        action="execute_refresh",
        current_fingerprints=current_fingerprints,
        current_prefix_fingerprints=current_prefix_fingerprints,
    )


def _validate_approved_refresh_plans(plans: ApprovedRefreshPlans) -> None:
    if not isinstance(plans, ApprovedRefreshPlans) or not all(
        isinstance(step, ApprovedRefreshStep) for step in plans.steps
    ):
        raise RefreshExecutionError("Approved refresh plans must use labeled fixed runner steps")
    if tuple(step.name for step in plans.steps) != RUNNER_STEP_NAMES:
        raise RefreshExecutionError(
            "Approved refresh requires every fixed runner step exactly once in approved order"
        )
    if plans.steps[-1].plan.operations:
        raise RefreshExecutionError("Final audit/export verification plan must be empty")


def _validate_execution_state(state: RefreshExecutionState) -> None:
    _require_digest(state.approval_digest, "execution approval digest")
    if not isinstance(state.sequence, int) or state.sequence < 0:
        raise RefreshExecutionError("Execution state sequence is invalid")
    if state.status not in EXECUTION_STATUSES:
        raise RefreshExecutionError("Execution state status is invalid")
    if not isinstance(state.step_index, int) or not 0 <= state.step_index <= len(RUNNER_STEP_NAMES):
        raise RefreshExecutionError("Execution state step index is invalid")
    if state.status == "completed" and state.step_index != len(RUNNER_STEP_NAMES):
        raise RefreshExecutionError("Completed execution state has an invalid step index")
    if not isinstance(state.receipts, tuple):
        raise RefreshExecutionError("Execution state receipts are invalid")
    for receipt in state.receipts:
        if not isinstance(receipt, Mapping) or set(receipt) != {"sequence", "step_index", "outcome"}:
            raise RefreshExecutionError("Execution state receipt is invalid")
        if not isinstance(receipt["sequence"], int) or not isinstance(receipt["step_index"], int) or not isinstance(receipt["outcome"], str):
            raise RefreshExecutionError("Execution state receipt value is invalid")


def _transition_execution_state(
    state: RefreshExecutionState, status: str, step_index: int, outcome: str
) -> RefreshExecutionState:
    _validate_execution_state(state)
    allowed = {
        "pending": {"running", "needs_restore", "completed"},
        "running": {"pending", "failed", "needs_restore"},
        "failed": {"pending", "running", "needs_restore"},
        "needs_restore": set(),
        "completed": set(),
    }
    if status not in allowed[state.status] or not isinstance(outcome, str) or not outcome:
        raise RefreshExecutionError("Illegal refresh execution state transition")
    next_state = RefreshExecutionState(
        approval_digest=state.approval_digest,
        sequence=state.sequence + 1,
        status=status,
        step_index=step_index,
        receipts=(*state.receipts, {"sequence": state.sequence + 1, "step_index": step_index, "outcome": outcome}),
    )
    _validate_execution_state(next_state)
    return next_state


def _write_execution_state(path: Path, state: RefreshExecutionState, *, previous_sequence: int | None) -> None:
    _validate_execution_state(state)
    if path.exists():
        previous = load_refresh_execution_state(path)
        if previous_sequence is None or previous.sequence != previous_sequence or state.sequence <= previous.sequence:
            raise RefreshExecutionError("Execution state sequence is not monotonic")
    elif previous_sequence is not None:
        raise RefreshExecutionError("Execution state disappeared during an atomic transition")
    _replace_atomic(path, _canonical_artifact_bytes(refresh_execution_state_payload(state)))


def _execute_plan_transactionally(connection: Any, plan: FoundationMutationPlan) -> None:
    transaction = getattr(connection, "transaction", None)
    if callable(transaction):
        with transaction():
            execute_plan(connection, plan)
        return
    # In-memory test adapters have no database transaction, but execute the
    # same immutable plan. Real connections must expose ``transaction``.
    if hasattr(connection, "table_state"):
        execute_plan(connection, plan)
        return
    raise RefreshExecutionError("Approved refresh connection does not expose a transaction adapter")


def _acquire_refresh_lock(connection: Any) -> None:
    acquire = getattr(connection, "acquire_refresh_lock", None)
    if callable(acquire):
        acquire()
        return
    if hasattr(connection, "table_state"):
        return
    with connection.cursor() as cursor:
        cursor.execute("select pg_advisory_lock(hashtext(%s))", ("nba-asset-lineage:foundation-refresh",))


def _release_refresh_lock(connection: Any) -> None:
    release = getattr(connection, "release_refresh_lock", None)
    if callable(release):
        release()
        return
    if hasattr(connection, "table_state"):
        return
    with connection.cursor() as cursor:
        cursor.execute("select pg_advisory_unlock(hashtext(%s))", ("nba-asset-lineage:foundation-refresh",))


def _repository_root(repo_root: Path) -> Path:
    root = repo_root.resolve()
    if not (root / ".git").exists():
        raise RefreshSafetyError("Implementation fingerprints require a repository root")
    return root


def _git_lines(root: Path, *args: str) -> list[str]:
    output = _git_bytes(root, *args)
    return [part.decode("utf-8") for part in output.split(b"\0") if part]


def _git_bytes(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, check=False, capture_output=True)
    if result.returncode:
        raise RefreshSafetyError(f"Git fingerprint command failed: {' '.join(args)}")
    return result.stdout


def _git_head(root: Path) -> str:
    return _git_bytes(root, "rev-parse", "HEAD").decode("ascii").strip()


def _implementation_path(path: str) -> bool:
    return (
        path.startswith("src/") and path.endswith(".py")
        or path.startswith("sql/") and path.endswith(".sql")
        or path.startswith("configs/") and path.endswith(".json")
        or path in {"pyproject.toml", "uv.lock", "mise.toml"}
    )


def _decode_database_value(value: object) -> object:
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise RefreshSafetyError("Snapshot tagged database value is invalid")
    kind = value["type"]
    if kind == "null" and set(value) == {"type"}:
        return None
    if kind == "bool" and set(value) == {"type", "value"} and isinstance(value["value"], bool):
        return value["value"]
    if kind == "int" and set(value) == {"type", "value"} and isinstance(value["value"], str):
        return int(value["value"])
    if kind == "str" and set(value) == {"type", "value"} and isinstance(value["value"], str):
        return value["value"]
    if kind == "float" and set(value) == {"type", "value"} and isinstance(value["value"], str):
        return float.fromhex(value["value"])
    if kind == "decimal" and set(value) == {"type", "value"} and isinstance(value["value"], str):
        return Decimal(value["value"])
    if kind == "date" and set(value) == {"type", "value"} and isinstance(value["value"], str):
        return date.fromisoformat(value["value"])
    if kind == "datetime" and set(value) == {"type", "value"} and isinstance(value["value"], str):
        return datetime.fromisoformat(value["value"].replace("Z", "+00:00"))
    if kind == "bytes" and set(value) == {"type", "base64"} and isinstance(value["base64"], str):
        try:
            return base64.b64decode(value["base64"], validate=True)
        except ValueError as error:
            raise RefreshSafetyError("Snapshot bytes value is invalid") from error
    if kind == "object" and set(value) == {"type", "value"} and isinstance(value["value"], dict):
        return {key: _decode_database_value(item) for key, item in value["value"].items()}
    if kind == "array" and set(value) == {"type", "value"} and isinstance(value["value"], list):
        return [_decode_database_value(item) for item in value["value"]]
    raise RefreshSafetyError("Snapshot tagged database value is invalid")


def _require_digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise RefreshSafetyError(f"{label} must be a lowercase SHA-256 digest")


def _canonical_artifact_bytes(payload: object) -> bytes:
    """Encode a previously schema-validated artifact without re-tagging its fields."""

    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RefreshSafetyError("Snapshot artifact contains unsupported JSON values") from error


def _validate_private_directory(path: Path) -> None:
    info = _directory_lstat(path)
    if info.st_mode & 0o077:
        raise RefreshSafetyError(f"Operational path must be a private real directory: {path}")


def _validate_real_directory(path: Path) -> None:
    """Validate a repo-local ancestor without requiring private checkout modes."""

    _directory_lstat(path)


def _directory_lstat(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as error:
        raise RefreshSafetyError(f"Operational directory is missing: {path}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RefreshSafetyError(f"Operational path must be a real directory: {path}")
    return info


def _write_exclusive_atomic(path: Path, body: bytes) -> None:
    temporary = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as error:
        raise RefreshSafetyError("Refusing to overwrite an existing foundation snapshot") from error
    finally:
        temporary.unlink(missing_ok=True)


def _replace_atomic(path: Path, body: bytes) -> None:
    """Atomically replace a closed operational state file in its private directory."""

    temporary = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
