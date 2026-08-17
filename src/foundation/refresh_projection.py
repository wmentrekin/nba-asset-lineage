"""Pure, no-write candidate projection for a foundation refresh.

This module deliberately accepts a *loaded* baseline rather than a database URL.
The caller may perform one read-only baseline load, but the resulting projector
has no connection or write-helper dependency.  Every state transition is an
immutable :class:`FoundationMutationPlan` applied through the shared in-memory
adapter used by the later runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from typing import Callable, Protocol

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
