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
from typing import Any, Mapping, Protocol, Sequence
import re
import stat
import uuid

from foundation.foundation_table_manifest import FOUNDATION_TABLES, foundation_schema_contract


REFRESH_SNAPSHOT_SCHEMA_VERSION = "foundation_refresh_snapshot_v1"
SNAPSHOT_FILE_NAME = "foundation-snapshot.json"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REFRESH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_DATABASE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


class RefreshSafetyError(ValueError):
    """Raised when a safety artifact or read-only snapshot is unsafe."""


class SnapshotCursor(Protocol):
    def execute(self, query: str, params: object | None = None) -> object: ...

    def fetchall(self) -> Sequence[object]: ...

    def __enter__(self) -> "SnapshotCursor": ...

    def __exit__(self, *args: object) -> None: ...


class SnapshotConnection(Protocol):
    def cursor(self) -> SnapshotCursor: ...

    def rollback(self) -> None: ...


@dataclass(frozen=True)
class FoundationSnapshot:
    """An in-memory exact preimage of the closed 21-table foundation surface."""

    tables: Mapping[str, tuple[Mapping[str, object], ...]]
    schema_fingerprint: str
    database_fingerprint: str

    @property
    def digest(self) -> str:
        return canonical_safety_digest("foundation-snapshot", snapshot_payload(self, include_digest=False))


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
    _validate_private_directory(repo_root)
    temporary_root = repo_root / "tmp"
    if temporary_root.exists() or temporary_root.is_symlink():
        _validate_private_directory(temporary_root)
    else:
        os.mkdir(temporary_root, 0o700)
    destination = temporary_root / refresh_id
    if destination.exists() or destination.is_symlink():
        raise RefreshSafetyError("Refusing to overwrite an existing refresh artifact directory")
    os.mkdir(destination, 0o700)
    return destination


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
    try:
        info = path.lstat()
    except OSError as error:
        raise RefreshSafetyError(f"Operational directory is missing: {path}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise RefreshSafetyError(f"Operational path must be a private real directory: {path}")


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
