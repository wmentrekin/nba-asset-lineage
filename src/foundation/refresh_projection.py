"""Pure, no-write candidate projection for a foundation refresh.

This module deliberately accepts a *loaded* baseline rather than a database URL.
The caller may perform one read-only baseline load, but the resulting projector
has no connection or write-helper dependency.  Every state transition is an
immutable :class:`FoundationMutationPlan` applied through the shared in-memory
adapter used by the later runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Callable, Mapping, Protocol
import uuid

from foundation.export import build_base_export
from foundation.foundation_table_manifest import FOUNDATION_TABLES
from foundation.models import BaseGraphExport, FoundationExportInputs, VisualizationExportV1
from foundation.refresh_mutations import FoundationMutationPlan, TableState, apply_plan_to_snapshot


APPROVED_PROJECTION_ORDER = (
    "Approved locked source loads",
    "Derived entities",
    "Roster snapshots bounded by as_of_date",
    "Curated draft resolution",
    "Canonical rebuild",
    "Pick obligations",
    "Pick inventory snapshots",
    "Two-way status",
    "Daily roster state bounded by as_of_date",
    "Draft prior-owner lineage",
    "Roster snapshot validation",
    "Approved additive draft-lottery load",
    "Audit/export verification twice",
)

PROJECTION_REPORT_SCHEMA_VERSION = "refresh_projection_report_v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_VOLATILE_SEMANTIC_COLUMNS = frozenset(
    {"fetched_at", "retrieved_at", "created_at", "updated_at"}
)


@dataclass(frozen=True)
class FoundationBaseline:
    """Typed read-only preimage supplied by a one-shot baseline reader."""

    tables: TableState
    historical_checksum: str


class ReadOnlyBaselineLoader(Protocol):
    """A narrow seam so tests can prove the projection never reconnects."""

    def load(self) -> FoundationBaseline: ...


@dataclass(frozen=True)
class ProjectionStage:
    """One approved runner prefix and its already-constructed shared plan."""

    name: str
    plan: FoundationMutationPlan
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefreshProjectionRequest:
    """All candidate mutations and gates needed for a pure projection."""

    source_overlay: ProjectionStage
    derived_stages: tuple[ProjectionStage, ...]
    as_of_date: date
    expected_historical_checksum: str | None = None
    export_inputs: Callable[[TableState], FoundationExportInputs] | None = None
    visualization_export: Callable[[BaseGraphExport], VisualizationExportV1] | None = None


@dataclass(frozen=True)
class ProjectionPrefix:
    name: str
    state: TableState
    checksum: str


@dataclass(frozen=True)
class RefreshProjection:
    baseline: FoundationBaseline
    prefixes: tuple[ProjectionPrefix, ...]
    blockers: tuple[str, ...]
    base_export: BaseGraphExport | None
    visualization_export: VisualizationExportV1 | None
    writes_to_database: bool = False

    @property
    def final_state(self) -> TableState:
        return self.prefixes[-1].state if self.prefixes else self.baseline.tables


@dataclass(frozen=True)
class ProjectionReportInputs:
    """Safe, already-digested inputs bound into a projection report.

    Raw bundle bytes and fixture contents are deliberately absent: a report can
    identify its reviewed inputs without becoming a second source-payload store.
    """

    source_bundle_digests: tuple[str, ...] = ()
    fixture_digests: tuple[str, ...] = ()


def load_read_only_baseline(loader: ReadOnlyBaselineLoader) -> FoundationBaseline:
    """Read exactly once; callers must discard their connection before projection."""

    baseline = loader.load()
    return FoundationBaseline(
        tables=_copy_state(baseline.tables),
        historical_checksum=baseline.historical_checksum,
    )


def project_refresh(
    baseline: FoundationBaseline,
    request: RefreshProjectionRequest,
) -> RefreshProjection:
    """Apply candidate plans in the fixed approved order without any I/O."""

    blockers = list(_baseline_gate_blockers(baseline, request))
    stages = (request.source_overlay, *request.derived_stages)
    expected_names = APPROVED_PROJECTION_ORDER[:-1]
    names = tuple(stage.name for stage in stages)
    if names != expected_names:
        blockers.append(
            "projection stages must exactly match the approved runner order before audit/export verification"
        )

    state = _copy_state(baseline.tables)
    prefixes: list[ProjectionPrefix] = []
    for stage in stages:
        blockers.extend(stage.blockers)
        state = apply_plan_to_snapshot(state, stage.plan)
        if stage.name in {
            "Approved locked source loads",
            "Roster snapshots bounded by as_of_date",
            "Daily roster state bounded by as_of_date",
        }:
            blockers.extend(_cutoff_blockers(state, request.as_of_date, stage.name))
        prefixes.append(ProjectionPrefix(stage.name, state, foundation_state_checksum(state)))

    base_export = None
    visualization = None
    if request.export_inputs is not None:
        base_export = build_base_export(request.export_inputs(state))
        if request.visualization_export is not None:
            visualization = request.visualization_export(base_export)
    elif request.visualization_export is not None:
        blockers.append("visualization export requires a base-export input builder")

    return RefreshProjection(
        baseline=baseline,
        prefixes=tuple(prefixes),
        blockers=tuple(dict.fromkeys(blockers)),
        base_export=base_export,
        visualization_export=visualization,
    )


def foundation_state_checksum(state: TableState) -> str:
    """Stable internal prefix fingerprint; T6 owns report-level digest contracts."""

    rows = {
        table.name: [
            row for _, row in sorted(state.get(table.name, {}).items(), key=lambda item: repr(item[0]))
        ]
        for table in FOUNDATION_TABLES
    }
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def canonical_projection_bytes(value: object) -> bytes:
    """Encode report data with a closed, deterministic JSON contract.

    This is intentionally separate from the source-bundle manifest encoding.
    Report digests must remain stable even if bundle serialization evolves.
    """

    return json.dumps(
        _canonical_projection_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_projection_digest(domain: str, value: object) -> str:
    """Return a domain-separated SHA-256 digest for canonical report data."""

    if not isinstance(domain, str) or not re.fullmatch(r"[a-z0-9._-]+", domain):
        raise ValueError("Projection digest domain is invalid")
    return sha256(
        f"nba-asset-lineage:refresh-projection:{domain}:v1\\0".encode("ascii")
        + canonical_projection_bytes(value)
    ).hexdigest()


def build_projection_report(
    projection: RefreshProjection,
    *,
    inputs: ProjectionReportInputs = ProjectionReportInputs(),
) -> dict[str, object]:
    """Create a closed, sanitized candidate report without retaining any rows.

    Row-set differences expose table key identifiers, changed field names, and
    opaque row hashes only.  The function never opens a connection and accepts
    no raw source payloads, so its output is safe to persist locally for review.
    """

    source_bundle_digests = _validated_digests(inputs.source_bundle_digests, "source bundle")
    fixture_digests = _validated_digests(inputs.fixture_digests, "fixture")
    final_state = projection.final_state
    prefixes = [
        {
            "name": prefix.name,
            "semantic_checksum": canonical_foundation_state_digest(prefix.state, semantic=True),
            "full_state_checksum": canonical_foundation_state_digest(prefix.state, semantic=False),
        }
        for prefix in projection.prefixes
    ]
    base_export_checksum = _model_checksum(projection.base_export)
    visualization_checksum = _model_checksum(projection.visualization_export)
    report_without_digest: dict[str, object] = {
        "schema_version": PROJECTION_REPORT_SCHEMA_VERSION,
        "writes_to_database": False,
        "input_digests": {
            "baseline_semantic_checksum": canonical_foundation_state_digest(
                projection.baseline.tables, semantic=True
            ),
            "baseline_full_state_checksum": canonical_foundation_state_digest(
                projection.baseline.tables, semantic=False
            ),
            "historical_checksum": _require_digest(
                projection.baseline.historical_checksum, "historical checksum"
            ),
            "source_bundle_digests": source_bundle_digests,
            "fixture_digests": fixture_digests,
        },
        "prefix_fingerprints": prefixes,
        "surface_diffs": _surface_diffs(projection.baseline.tables, final_state),
        "final_checksums": {
            "foundation_semantic_checksum": canonical_foundation_state_digest(final_state, semantic=True),
            "foundation_full_state_checksum": canonical_foundation_state_digest(final_state, semantic=False),
            "base_export_checksum": base_export_checksum,
            "visualization_export_checksum": visualization_checksum,
        },
        "blockers": sorted(set(projection.blockers)),
    }
    return {
        **report_without_digest,
        "report_digest": canonical_projection_digest("report", report_without_digest),
    }


def write_projection_report(path: Path, report: Mapping[str, object]) -> None:
    """Atomically create one mode-restricted local report artifact.

    The parent must already be a private operational directory.  Existing files
    are never overwritten, preventing a reviewed report from being replaced.
    """

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", path.name):
        raise ValueError("Projection report file name is unsafe")
    parent = path.parent
    parent_info = parent.lstat()
    if parent.is_symlink() or not parent.is_dir() or parent_info.st_mode & 0o077:
        raise ValueError("Projection report parent must be a private real directory")
    if path.exists() or path.is_symlink():
        raise ValueError("Refusing to overwrite an existing projection report")
    _validate_projection_report(report)
    body = canonical_projection_bytes(dict(report))
    temporary = parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        # ``link`` is an atomic no-replace publication primitive.  Unlike
        # os.replace it cannot overwrite a report another process just wrote.
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ValueError("Refusing to overwrite an existing projection report") from exc
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    finally:
        temporary.unlink(missing_ok=True)


def canonical_foundation_state_digest(state: TableState, *, semantic: bool) -> str:
    """Digest all 21 closed tables using table keys rather than insertion order."""

    tables = {
        table.name: [
            _row_for_digest(table.name, row, semantic=semantic)
            for _, row in sorted(state.get(table.name, {}).items(), key=lambda item: _key_sort_value(item[0]))
        ]
        for table in FOUNDATION_TABLES
    }
    return canonical_projection_digest("foundation-semantic" if semantic else "foundation-full-state", tables)


def _surface_diffs(before: TableState, after: TableState) -> list[dict[str, object]]:
    diffs: list[dict[str, object]] = []
    for table in FOUNDATION_TABLES:
        before_rows = before.get(table.name, {})
        after_rows = after.get(table.name, {})
        added_keys = sorted(set(after_rows).difference(before_rows), key=_key_sort_value)
        removed_keys = sorted(set(before_rows).difference(after_rows), key=_key_sort_value)
        changed_keys = sorted(
            (key for key in set(before_rows).intersection(after_rows) if before_rows[key] != after_rows[key]),
            key=_key_sort_value,
        )
        diffs.append(
            {
                "table": table.name,
                "added": [
                    {"identifier": _identifier(key), "after_hash": _row_hash(table.name, after_rows[key])}
                    for key in added_keys
                ],
                "removed": [
                    {"identifier": _identifier(key), "before_hash": _row_hash(table.name, before_rows[key])}
                    for key in removed_keys
                ],
                "changed": [
                    {
                        "identifier": _identifier(key),
                        "changed_fields": sorted(
                            name
                            for name in set(before_rows[key]).union(after_rows[key])
                            if before_rows[key].get(name) != after_rows[key].get(name)
                        ),
                        "before_hash": _row_hash(table.name, before_rows[key]),
                        "after_hash": _row_hash(table.name, after_rows[key]),
                    }
                    for key in changed_keys
                ],
            }
        )
    return diffs


def _row_hash(table_name: str, row: Mapping[str, object]) -> str:
    return canonical_projection_digest(f"row-{table_name}", _row_for_digest(table_name, row, semantic=False))


def _row_for_digest(table_name: str, row: Mapping[str, object], *, semantic: bool) -> dict[str, object]:
    columns = next(table.columns for table in FOUNDATION_TABLES if table.name == table_name)
    return {
        column: row[column]
        for column in columns
        if column in row and (not semantic or column not in _VOLATILE_SEMANTIC_COLUMNS)
    }


def _model_checksum(value: BaseGraphExport | VisualizationExportV1 | None) -> str | None:
    if value is None:
        return None
    return canonical_projection_digest("base-export" if isinstance(value, BaseGraphExport) else "visualization-export", value.model_dump(mode="json"))


def _canonical_projection_value(value: object) -> object:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not value == value or value in {float("inf"), float("-inf")}:
            raise ValueError("Projection canonical JSON does not permit non-finite floats")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Projection canonical timestamps must include a timezone")
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Projection canonical JSON object keys must be strings")
        return {key: _canonical_projection_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_projection_value(item) for item in value]
    raise ValueError(f"Unsupported projection canonical JSON value: {type(value).__name__}")


def _validated_digests(values: tuple[str, ...], label: str) -> list[str]:
    normalized = sorted({_require_digest(value, label) for value in values})
    if len(normalized) != len(values):
        raise ValueError(f"Duplicate {label} digests are not allowed")
    return normalized


def _require_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _identifier(key: tuple[object, ...]) -> str:
    return "|".join(str(part) for part in key)


def _key_sort_value(key: tuple[object, ...]) -> tuple[str, ...]:
    return tuple(str(part) for part in key)


def _validate_projection_report(report: Mapping[str, object]) -> None:
    required = {
        "schema_version",
        "writes_to_database",
        "input_digests",
        "prefix_fingerprints",
        "surface_diffs",
        "final_checksums",
        "blockers",
        "report_digest",
    }
    if set(report) != required or report.get("schema_version") != PROJECTION_REPORT_SCHEMA_VERSION:
        raise ValueError("Projection report does not match the closed schema")
    without_digest = {key: value for key, value in report.items() if key != "report_digest"}
    if report.get("report_digest") != canonical_projection_digest("report", without_digest):
        raise ValueError("Projection report digest does not match its contents")


def _baseline_gate_blockers(
    baseline: FoundationBaseline, request: RefreshProjectionRequest
) -> tuple[str, ...]:
    if (
        request.expected_historical_checksum is not None
        and baseline.historical_checksum != request.expected_historical_checksum
    ):
        return ("historical checksum does not match the approved projection gate",)
    return ()


def _cutoff_blockers(state: TableState, as_of_date: date, stage_name: str) -> tuple[str, ...]:
    cutoff = as_of_date.isoformat()
    dated_tables = {
        "source_event": "event_date",
        "roster_snapshot": "snapshot_date",
        "daily_roster_state": "state_date",
    }
    blockers: list[str] = []
    for table_name, date_column in dated_tables.items():
        for row in state.get(table_name, {}).values():
            value = row.get(date_column)
            if isinstance(value, str) and value > cutoff:
                blockers.append(f"{stage_name}: {table_name} {row} exceeds as_of_date {cutoff}")
    return tuple(blockers)


def _copy_state(state: TableState) -> TableState:
    return {
        table.name: {key: dict(row) for key, row in state.get(table.name, {}).items()}
        for table in FOUNDATION_TABLES
    }
