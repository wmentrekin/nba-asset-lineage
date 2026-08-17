"""Sealed local artifacts for the foundation refresh command surface.

The operational commands deliberately receive an artifact *directory*, not a
collection of user chosen files.  This module owns the closed files in that
directory and validates them before a future adapter is allowed to connect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Mapping

from foundation.foundation_table_manifest import foundation_table
from foundation.refresh_mutations import (
    DeleteKeys, FoundationMutationPlan, InsertMissingRows, PatchRows,
    ReplaceAll, ReplacePartitions, UpsertRows,
)
from foundation.refresh_projection import APPROVED_PROJECTION_ORDER, canonical_projection_digest
from foundation.refresh_safety import (
    ApprovedRefreshPlans, ApprovedRefreshStep, RefreshSafetyError,
    canonical_database_value, canonical_safety_digest, validate_refresh_artifact_directory,
)
from foundation.source_payloads import SUPPORTED_SOURCE_KINDS, load_source_bundle


REFRESH_REQUEST_SCHEMA_VERSION = "refresh_request_v1"
REFRESH_PLAN_SCHEMA_VERSION = "refresh_plan_v1"
REFRESH_RECONCILIATION_SCHEMA_VERSION = "refresh_reconciliation_v1"
REFRESH_REQUEST_FILE_NAME = "refresh-request.json"
REFRESH_PLAN_FILE_NAME = "refresh-plan.json"
RECONCILIATION_FILE_NAME = "refresh-reconciliation.json"
PROJECTION_REPORT_FILE_NAME = "projection-report.json"
SOURCE_KINDS = tuple(sorted(SUPPORTED_SOURCE_KINDS))
FIXTURE_SLOT_NAMES = ("draft_resolution", "historical_checksum", "roster_baseline", "two_way_status")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REFRESH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class RefreshArtifactError(RefreshSafetyError):
    """Raised for an unsafe, unsealed, or stale operational artifact."""


@dataclass(frozen=True)
class RefreshRequest:
    refresh_id: str
    as_of_date: date
    bundle_digests: Mapping[str, str]
    fixture_digests: Mapping[str, str]

    @property
    def digest(self) -> str:
        return _digest("refresh-request", request_payload(self, include_digest=False))


@dataclass(frozen=True)
class RefreshReconciliation:
    request_digest: str
    baseline_digest: str
    historical_checksum: str
    fixture_digest: str
    source_bundle_digest: str

    @property
    def digest(self) -> str:
        return _digest("refresh-reconciliation", reconciliation_payload(self, include_digest=False))


@dataclass(frozen=True)
class SealedRefreshPlan:
    request_digest: str
    reconciliation_digest: str
    baseline_digest: str
    historical_checksum: str
    plans: ApprovedRefreshPlans

    @property
    def digest(self) -> str:
        return _digest("refresh-plan", refresh_plan_payload(self, include_digest=False))


def request_payload(request: RefreshRequest, *, include_digest: bool = True) -> dict[str, object]:
    _validate_request(request)
    payload: dict[str, object] = {
        "schema_version": REFRESH_REQUEST_SCHEMA_VERSION,
        "refresh_id": request.refresh_id,
        "as_of_date": request.as_of_date.isoformat(),
        "source_bundles": [
            {"source_kind": kind, "relative_path": f"bundles/{kind}", "bundle_sha256": request.bundle_digests[kind]}
            for kind in SOURCE_KINDS
        ],
        "fixtures": [
            {"name": name, "relative_path": f"fixtures/{name}.json", "sha256": request.fixture_digests[name]}
            for name in FIXTURE_SLOT_NAMES
        ],
    }
    if include_digest:
        payload["request_sha256"] = _digest("refresh-request", payload)
    return payload


def reconciliation_payload(value: RefreshReconciliation, *, include_digest: bool = True) -> dict[str, object]:
    _validate_reconciliation(value)
    payload: dict[str, object] = {
        "schema_version": REFRESH_RECONCILIATION_SCHEMA_VERSION,
        "request_digest": value.request_digest,
        "baseline_digest": value.baseline_digest,
        "historical_checksum": value.historical_checksum,
        "fixture_digest": value.fixture_digest,
        "source_bundle_digest": value.source_bundle_digest,
    }
    if include_digest:
        payload["reconciliation_sha256"] = _digest("refresh-reconciliation", payload)
    return payload


def refresh_plan_payload(value: SealedRefreshPlan, *, include_digest: bool = True) -> dict[str, object]:
    _validate_sealed_plan(value)
    payload: dict[str, object] = {
        "schema_version": REFRESH_PLAN_SCHEMA_VERSION,
        "request_digest": value.request_digest,
        "reconciliation_digest": value.reconciliation_digest,
        "baseline_digest": value.baseline_digest,
        "historical_checksum": value.historical_checksum,
        "steps": [
            {"name": step.name, "plan": mutation_plan_payload(step.plan)} for step in value.plans.steps
        ],
    }
    if include_digest:
        payload["plan_sha256"] = _digest("refresh-plan", payload)
    return payload


def mutation_plan_payload(plan: FoundationMutationPlan) -> dict[str, object]:
    payload = _mutation_plan_payload(plan)
    # Reconstructing performs the existing table/policy validation too.
    mutation_plan_from_payload(payload)
    return payload


def _mutation_plan_payload(plan: FoundationMutationPlan) -> dict[str, object]:
    operations: list[dict[str, object]] = []
    for operation in plan.operations:
        base = {"table": operation.table}
        if isinstance(operation, UpsertRows):
            operations.append({**base, "type": "upsert_rows", "rows": _rows(operation.table, operation.rows), "policies": _policies(operation.policies)})
        elif isinstance(operation, InsertMissingRows):
            operations.append({**base, "type": "insert_missing_rows", "rows": _rows(operation.table, operation.rows)})
        elif isinstance(operation, DeleteKeys):
            operations.append({**base, "type": "delete_keys", "keys": [_key(operation.table, key) for key in operation.keys]})
        elif isinstance(operation, ReplacePartitions):
            operations.append({**base, "type": "replace_partitions", "partition_columns": list(operation.partition_columns), "partition_values": [_values(values) for values in operation.partition_values], "rows": _rows(operation.table, operation.rows)})
        elif isinstance(operation, ReplaceAll):
            operations.append({**base, "type": "replace_all", "rows": _rows(operation.table, operation.rows)})
        elif isinstance(operation, PatchRows):
            operations.append({**base, "type": "patch_rows", "patches": [{"key": _key(operation.table, key), "row": _row(operation.table, row)} for key, row in operation.patches], "policies": _policies(operation.policies)})
        else:  # pragma: no cover - keeps this codec closed if the union grows.
            raise RefreshArtifactError("Unknown foundation mutation operation")
    return {"operation_timestamp": plan.operation_timestamp, "operations": operations}


def mutation_plan_from_payload(payload: object) -> FoundationMutationPlan:
    if not isinstance(payload, dict) or set(payload) != {"operation_timestamp", "operations"} or not isinstance(payload["operations"], list):
        raise RefreshArtifactError("Foundation mutation plan does not match the closed schema")
    operations = []
    for raw in payload["operations"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("type"), str) or not isinstance(raw.get("table"), str):
            raise RefreshArtifactError("Foundation mutation operation is invalid")
        table = raw["table"]
        kind = raw["type"]
        if kind == "upsert_rows" and set(raw) == {"type", "table", "rows", "policies"}:
            operations.append(UpsertRows(table, _read_rows(table, raw["rows"]), _read_policies(raw["policies"])))
        elif kind == "insert_missing_rows" and set(raw) == {"type", "table", "rows"}:
            operations.append(InsertMissingRows(table, _read_rows(table, raw["rows"])))
        elif kind == "delete_keys" and set(raw) == {"type", "table", "keys"}:
            operations.append(DeleteKeys(table, _read_keys(table, raw["keys"])))
        elif kind == "replace_partitions" and set(raw) == {"type", "table", "partition_columns", "partition_values", "rows"}:
            columns = _read_columns(table, raw["partition_columns"])
            values = _read_value_tuples(raw["partition_values"], len(columns))
            operations.append(ReplacePartitions(table, columns, values, _read_rows(table, raw["rows"])))
        elif kind == "replace_all" and set(raw) == {"type", "table", "rows"}:
            operations.append(ReplaceAll(table, _read_rows(table, raw["rows"])))
        elif kind == "patch_rows" and set(raw) == {"type", "table", "patches", "policies"}:
            if not isinstance(raw["patches"], list):
                raise RefreshArtifactError("Patch rows are invalid")
            patches = tuple((_read_key(table, item.get("key")), _read_row(table, item.get("row"))) for item in raw["patches"] if isinstance(item, dict) and set(item) == {"key", "row"})
            if len(patches) != len(raw["patches"]):
                raise RefreshArtifactError("Patch rows are invalid")
            operations.append(PatchRows(table, patches, _read_policies(raw["policies"])))
        else:
            raise RefreshArtifactError("Foundation mutation operation does not match the closed schema")
    try:
        plan = FoundationMutationPlan(tuple(operations), payload["operation_timestamp"])
    except (TypeError, ValueError) as error:
        raise RefreshArtifactError("Foundation mutation plan is invalid") from error
    if _mutation_plan_payload(plan) != payload:
        raise RefreshArtifactError("Foundation mutation plan is noncanonical")
    return plan


def write_refresh_request(directory: Path, request: RefreshRequest) -> Path:
    return _write(directory, REFRESH_REQUEST_FILE_NAME, request_payload(request))


def write_reconciliation(directory: Path, value: RefreshReconciliation) -> Path:
    return _write(directory, RECONCILIATION_FILE_NAME, reconciliation_payload(value))


def write_refresh_plan(directory: Path, value: SealedRefreshPlan) -> Path:
    return _write(directory, REFRESH_PLAN_FILE_NAME, refresh_plan_payload(value))


def load_refresh_request(directory: Path) -> RefreshRequest:
    payload = _load(directory, REFRESH_REQUEST_FILE_NAME)
    required = {"schema_version", "refresh_id", "as_of_date", "source_bundles", "fixtures", "request_sha256"}
    if not isinstance(payload, dict) or set(payload) != required or payload["schema_version"] != REFRESH_REQUEST_SCHEMA_VERSION:
        raise RefreshArtifactError("Refresh request does not match the closed schema")
    bundles = _slots(payload["source_bundles"], "source_kind", SOURCE_KINDS, "bundles", lambda n: n, "bundle_sha256")
    fixtures = _slots(payload["fixtures"], "name", FIXTURE_SLOT_NAMES, "fixtures", lambda n: f"{n}.json", "sha256")
    try:
        request = RefreshRequest(payload["refresh_id"], date.fromisoformat(payload["as_of_date"]), bundles, fixtures)
    except (TypeError, ValueError) as error:
        raise RefreshArtifactError("Refresh request is invalid") from error
    if payload["request_sha256"] != request.digest:
        raise RefreshArtifactError("Refresh request digest does not match its contents")
    _validate_request_material(directory, request)
    return request


def load_reconciliation(directory: Path, *, request: RefreshRequest) -> RefreshReconciliation:
    payload = _load(directory, RECONCILIATION_FILE_NAME)
    required = {"schema_version", "request_digest", "baseline_digest", "historical_checksum", "fixture_digest", "source_bundle_digest", "reconciliation_sha256"}
    if not isinstance(payload, dict) or set(payload) != required or payload["schema_version"] != REFRESH_RECONCILIATION_SCHEMA_VERSION:
        raise RefreshArtifactError("Refresh reconciliation does not match the closed schema")
    value = RefreshReconciliation(*(payload[field] for field in ("request_digest", "baseline_digest", "historical_checksum", "fixture_digest", "source_bundle_digest")))
    if payload["reconciliation_sha256"] != value.digest or value.request_digest != request.digest:
        raise RefreshArtifactError("Refresh reconciliation is not bound to this request")
    if value.fixture_digest != _set_digest("fixtures", request.fixture_digests) or value.source_bundle_digest != _set_digest("bundles", request.bundle_digests):
        raise RefreshArtifactError("Refresh reconciliation inputs drifted")
    return value


def load_refresh_plan(directory: Path, *, request: RefreshRequest, reconciliation: RefreshReconciliation) -> SealedRefreshPlan:
    payload = _load(directory, REFRESH_PLAN_FILE_NAME)
    required = {"schema_version", "request_digest", "reconciliation_digest", "baseline_digest", "historical_checksum", "steps", "plan_sha256"}
    if not isinstance(payload, dict) or set(payload) != required or payload["schema_version"] != REFRESH_PLAN_SCHEMA_VERSION or not isinstance(payload["steps"], list):
        raise RefreshArtifactError("Refresh plan does not match the closed schema")
    try:
        plans = ApprovedRefreshPlans(tuple(ApprovedRefreshStep(step["name"], mutation_plan_from_payload(step["plan"])) for step in payload["steps"] if isinstance(step, dict) and set(step) == {"name", "plan"}))
        if len(plans.steps) != len(payload["steps"]):
            raise ValueError("invalid steps")
        value = SealedRefreshPlan(payload["request_digest"], payload["reconciliation_digest"], payload["baseline_digest"], payload["historical_checksum"], plans)
    except (TypeError, ValueError, RefreshSafetyError) as error:
        raise RefreshArtifactError("Refresh plan is invalid") from error
    if payload["plan_sha256"] != value.digest or value.request_digest != request.digest or value.reconciliation_digest != reconciliation.digest:
        raise RefreshArtifactError("Refresh plan is not bound to this artifact chain")
    if value.baseline_digest != reconciliation.baseline_digest or value.historical_checksum != reconciliation.historical_checksum:
        raise RefreshArtifactError("Refresh plan reconciliation bindings drifted")
    return value


def validate_artifact_chain(directory: Path) -> tuple[RefreshRequest, RefreshReconciliation, SealedRefreshPlan]:
    """Validate every untrusted artifact and input before a caller connects."""
    validate_refresh_artifact_directory(directory)
    request = load_refresh_request(directory)
    reconciliation = load_reconciliation(directory, request=request)
    return request, reconciliation, load_refresh_plan(directory, request=request, reconciliation=reconciliation)


def load_sealed_projection_report(
    directory: Path, *, request: RefreshRequest, reconciliation: RefreshReconciliation, plan: SealedRefreshPlan
) -> Mapping[str, object]:
    """Load the sanitized report only when it names this exact sealed chain."""
    report = _load(directory, PROJECTION_REPORT_FILE_NAME)
    if not isinstance(report, dict) or report.get("report_digest") != canonical_projection_digest(
        "report", {key: value for key, value in report.items() if key != "report_digest"}
    ):
        raise RefreshArtifactError("Projection report digest does not match its contents")
    bindings = report.get("artifact_bindings")
    expected = {
        "request_digest": request.digest,
        "reconciliation_digest": reconciliation.digest,
        "plan_digest": plan.digest,
    }
    if bindings != expected:
        raise RefreshArtifactError("Projection report is not bound to this artifact chain")
    return report


def reject_projection_report_blockers(report: Mapping[str, object]) -> None:
    """Reject execution when a sealed candidate report has unresolved blockers."""

    blockers = report.get("blockers")
    if not isinstance(blockers, list) or any(not isinstance(item, str) or not item for item in blockers):
        raise RefreshArtifactError("Projection report blockers do not match the closed schema")
    if blockers:
        raise RefreshArtifactError("Sealed projection report contains blockers; refresh execution is forbidden")


def _digest(domain: str, value: object) -> str:
    return canonical_safety_digest(domain, value)


def _validate_request(request: RefreshRequest) -> None:
    if not isinstance(request.refresh_id, str) or not _REFRESH_ID.fullmatch(request.refresh_id):
        raise RefreshArtifactError("Refresh request identifier is invalid")
    if not isinstance(request.as_of_date, date):
        raise RefreshArtifactError("Refresh request cutoff is invalid")
    _validate_digest_slots(request.bundle_digests, SOURCE_KINDS, "source bundle")
    _validate_digest_slots(request.fixture_digests, FIXTURE_SLOT_NAMES, "fixture")


def _validate_reconciliation(value: RefreshReconciliation) -> None:
    for item in (value.request_digest, value.baseline_digest, value.historical_checksum, value.fixture_digest, value.source_bundle_digest):
        _require_digest(item)


def _validate_sealed_plan(value: SealedRefreshPlan) -> None:
    for item in (value.request_digest, value.reconciliation_digest, value.baseline_digest, value.historical_checksum):
        _require_digest(item)
    # ApprovedRefreshPlans does the exact names/order check in __post_init__.
    if tuple(step.name for step in value.plans.steps) != APPROVED_PROJECTION_ORDER:
        raise RefreshArtifactError("Refresh plan steps are not the closed runner order")
    if value.plans.steps[-1].plan.operations:
        raise RefreshArtifactError("Final audit/export verification plan must be empty")


def _validate_digest_slots(value: Mapping[str, str], names: tuple[str, ...], label: str) -> None:
    if not isinstance(value, Mapping) or tuple(value) != names:
        raise RefreshArtifactError(f"Refresh request {label} slots do not match the closed schema")
    for digest in value.values():
        _require_digest(digest)


def _validate_request_material(directory: Path, request: RefreshRequest) -> None:
    _private_directory(directory)
    for kind in SOURCE_KINDS:
        load_source_bundle(directory / "bundles" / kind, expected_digest=request.bundle_digests[kind], expected_source_kind=kind)
    for name in FIXTURE_SLOT_NAMES:
        path = directory / "fixtures" / f"{name}.json"
        _private_file(path)
        if sha256(path.read_bytes()).hexdigest() != request.fixture_digests[name]:
            raise RefreshArtifactError("Refresh request fixture bytes drifted")


def _slots(raw: object, name_key: str, names: tuple[str, ...], parent: str, leaf, digest_key: str) -> dict[str, str]:
    if not isinstance(raw, list) or len(raw) != len(names):
        raise RefreshArtifactError("Refresh request slots are invalid")
    result: dict[str, str] = {}
    for expected, item in zip(names, raw, strict=True):
        if not isinstance(item, dict) or set(item) != {name_key, "relative_path", digest_key} or item[name_key] != expected or item["relative_path"] != f"{parent}/{leaf(expected)}":
            raise RefreshArtifactError("Refresh request paths are not allowlisted")
        _require_digest(item[digest_key])
        result[expected] = item[digest_key]
    return result


def _rows(table: str, rows) -> list[dict[str, object]]:
    return [_row(table, row) for row in rows]


def _row(table: str, row: Mapping[str, object]) -> dict[str, object]:
    contract = foundation_table(table)
    if not isinstance(row, Mapping) or set(row).difference(contract.columns):
        raise RefreshArtifactError("Mutation row has unsupported columns")
    return {column: canonical_database_value(row[column]) for column in contract.columns if column in row}


def _key(table: str, key) -> list[object]:
    contract = foundation_table(table)
    if not isinstance(key, tuple) or len(key) != len(contract.key_columns):
        raise RefreshArtifactError("Mutation key is invalid")
    return _values(key)


def _values(values) -> list[object]:
    return [canonical_database_value(value) for value in values]


def _policies(policies) -> list[list[str]]:
    return [[column, policy] for column, policy in sorted(policies)]


def _read_rows(table: str, raw: object):
    if not isinstance(raw, list):
        raise RefreshArtifactError("Mutation rows are invalid")
    return tuple(_read_row(table, item) for item in raw)


def _read_row(table: str, raw: object):
    contract = foundation_table(table)
    if not isinstance(raw, dict) or not set(raw).issubset(contract.columns) or not set(contract.key_columns).issubset(raw):
        raise RefreshArtifactError("Mutation row does not match its table")
    return {column: _decode(raw[column]) for column in contract.columns if column in raw}


def _read_keys(table: str, raw: object):
    if not isinstance(raw, list):
        raise RefreshArtifactError("Mutation keys are invalid")
    return tuple(_read_key(table, item) for item in raw)


def _read_key(table: str, raw: object):
    contract = foundation_table(table)
    values = _read_values(raw)
    if len(values) != len(contract.key_columns):
        raise RefreshArtifactError("Mutation key width is invalid")
    return values


def _read_columns(table: str, raw: object):
    contract = foundation_table(table)
    if not isinstance(raw, list) or not raw or len(set(raw)) != len(raw) or any(not isinstance(item, str) or item not in contract.columns for item in raw):
        raise RefreshArtifactError("Partition columns are invalid")
    return tuple(raw)


def _read_value_tuples(raw: object, width: int):
    if not isinstance(raw, list):
        raise RefreshArtifactError("Partition values are invalid")
    values = tuple(_read_values(item) for item in raw)
    if any(len(item) != width for item in values):
        raise RefreshArtifactError("Partition value width is invalid")
    return values


def _read_values(raw: object):
    if not isinstance(raw, list):
        raise RefreshArtifactError("Tagged values are invalid")
    return tuple(_decode(item) for item in raw)


def _read_policies(raw: object):
    allowed = {"excluded", "coalesce_excluded_existing", "preserve_existing", "append_once", "constant", "operation_timestamp"}
    if not isinstance(raw, list) or any(not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str) or item[1] not in allowed for item in raw):
        raise RefreshArtifactError("Mutation policies are invalid")
    result = tuple((item[0], item[1]) for item in raw)
    if list(result) != sorted(result) or len(set(column for column, _ in result)) != len(result):
        raise RefreshArtifactError("Mutation policies are noncanonical")
    return result


def _decode(value: object):
    # ``canonical_database_value`` has a deliberately small tagged grammar.
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise RefreshArtifactError("Tagged mutation value is invalid")
    kind = value["type"]
    if kind == "null" and set(value) == {"type"}: return None
    if kind == "bool" and set(value) == {"type", "value"} and isinstance(value["value"], bool): return value["value"]
    if kind == "int" and set(value) == {"type", "value"} and isinstance(value["value"], str): return int(value["value"])
    if kind == "str" and set(value) == {"type", "value"} and isinstance(value["value"], str): return value["value"]
    if kind == "object" and set(value) == {"type", "value"} and isinstance(value["value"], dict):
        if not all(isinstance(key, str) for key in value["value"]):
            raise RefreshArtifactError("Tagged mutation object keys are invalid")
        return {key: _decode(item) for key, item in value["value"].items()}
    if kind == "array" and set(value) == {"type", "value"} and isinstance(value["value"], list): return [_decode(item) for item in value["value"]]
    # Plans very rarely contain these, but preserve the full tagged surface by
    # asking the safety parser to validate them rather than stringify them.
    from foundation.refresh_safety import _decode_database_value
    try:
        return _decode_database_value(value)
    except (RefreshSafetyError, ValueError, TypeError) as error:
        raise RefreshArtifactError("Tagged mutation value is invalid") from error


def _set_digest(domain: str, values: Mapping[str, str]) -> str:
    return _digest(domain, {key: values[key] for key in sorted(values)})


def _require_digest(value: object) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise RefreshArtifactError("Artifact digest is invalid")


def _private_directory(path: Path) -> None:
    try: info = path.lstat()
    except OSError as error: raise RefreshArtifactError("Artifact directory is missing") from error
    if path.is_symlink() or not path.is_dir() or info.st_mode & 0o077:
        raise RefreshArtifactError("Artifact directory is unsafe")


def _private_file(path: Path) -> None:
    try: info = path.lstat()
    except OSError as error: raise RefreshArtifactError("Artifact file is missing") from error
    if path.is_symlink() or not path.is_file() or info.st_mode & 0o077 or info.st_nlink != 1:
        raise RefreshArtifactError("Artifact file is unsafe")


def _write(directory: Path, name: str, payload: Mapping[str, object]) -> Path:
    _private_directory(directory)
    path = directory / name
    if path.exists() or path.is_symlink():
        raise RefreshArtifactError("Refusing to overwrite an artifact")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(body); handle.flush(); os.fsync(handle.fileno())
    return path


def _load(directory: Path, name: str):
    _private_directory(directory)
    path = directory / name
    _private_file(path)
    try:
        raw = path.read_bytes(); payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RefreshArtifactError("Artifact is not UTF-8 JSON") from error
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    if raw != canonical:
        raise RefreshArtifactError("Artifact is not canonically encoded")
    return payload
