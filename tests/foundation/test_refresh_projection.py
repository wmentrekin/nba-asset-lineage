from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os

import pytest

from foundation.refresh_mutations import FoundationMutationPlan, UpsertRows, empty_table_state
from foundation.refresh_projection import (
    APPROVED_PROJECTION_ORDER,
    FoundationBaseline,
    ProjectionReportInputs,
    ProjectionStage,
    RefreshProjection,
    RefreshProjectionRequest,
    build_projection_report,
    canonical_foundation_state_digest,
    load_read_only_baseline,
    project_refresh,
    write_projection_report,
)


@dataclass
class FakeReadOnlyLoader:
    baseline: FoundationBaseline
    calls: int = 0

    def load(self) -> FoundationBaseline:
        self.calls += 1
        return self.baseline


def _stage(name: str, rows: tuple[dict[str, object], ...] = (), blockers: tuple[str, ...] = ()) -> ProjectionStage:
    return ProjectionStage(
        name=name,
        blockers=blockers,
        plan=FoundationMutationPlan(
            operations=(UpsertRows("source_event", rows),) if rows else (),
            operation_timestamp="2026-08-16T00:00:00Z",
        ),
    )


def test_projection_reads_baseline_once_then_applies_only_shared_plans() -> None:
    loader = FakeReadOnlyLoader(FoundationBaseline(empty_table_state(), "historical-ok"))
    baseline = load_read_only_baseline(loader)
    stages = tuple(
        _stage(
            name,
            (
                {
                    "source_event_id": "event:one",
                    "source_record_id": "source:one",
                    "event_date": "2026-08-16",
                    "event_type": "trade",
                    "label": "candidate",
                    "team_scope": "MEM",
                    "source_group_hint": None,
                    "normalized_payload": {},
                },
            )
            if name == "Approved locked source loads"
            else (),
        )
        for name in APPROVED_PROJECTION_ORDER[:-1]
    )
    result = project_refresh(
        baseline,
        RefreshProjectionRequest(
            source_overlay=stages[0],
            derived_stages=stages[1:],
            as_of_date=date(2026, 8, 16),
            expected_historical_checksum="historical-ok",
        ),
    )

    assert loader.calls == 1
    assert result.writes_to_database is False
    assert [prefix.name for prefix in result.prefixes] == list(APPROVED_PROJECTION_ORDER[:-1])
    assert ("event:one",) in result.final_state["source_event"]


def test_projection_propagates_cutoff_historical_and_domain_blockers() -> None:
    stages = tuple(
        _stage(
            name,
            (
                {
                    "source_event_id": "event:after-cutoff",
                    "source_record_id": "source:one",
                    "event_date": "2026-08-17",
                    "event_type": "trade",
                    "label": "candidate",
                    "team_scope": "MEM",
                    "source_group_hint": None,
                    "normalized_payload": {},
                },
            )
            if name == "Approved locked source loads"
            else (),
            ("unresolved alias: example",) if name == "Derived entities" else (),
        )
        for name in APPROVED_PROJECTION_ORDER[:-1]
    )
    result = project_refresh(
        FoundationBaseline(empty_table_state(), "actual"),
        RefreshProjectionRequest(
            source_overlay=stages[0],
            derived_stages=stages[1:],
            as_of_date=date(2026, 8, 16),
            expected_historical_checksum="expected",
        ),
    )

    assert any("historical checksum" in blocker for blocker in result.blockers)
    assert any("exceeds as_of_date" in blocker for blocker in result.blockers)
    assert "unresolved alias: example" in result.blockers


def test_projection_report_is_deterministic_and_never_exposes_rows_or_payloads() -> None:
    baseline_state = empty_table_state()
    baseline_state["source_event"][("event:one",)] = {
        "source_event_id": "event:one",
        "source_record_id": "source:one",
        "event_date": "2026-08-16",
        "event_type": "trade",
        "label": "before",
        "team_scope": "MEM",
        "source_group_hint": None,
        "normalized_payload": {"private": "do-not-report"},
    }
    stages = tuple(
        _stage(
            name,
            (
                {
                    **baseline_state["source_event"][("event:one",)],
                    "label": "after",
                    "normalized_payload": {"private": "still-not-reported"},
                },
            )
            if name == "Approved locked source loads"
            else (),
        )
        for name in APPROVED_PROJECTION_ORDER[:-1]
    )
    projection = project_refresh(
        FoundationBaseline(baseline_state, "a" * 64),
        RefreshProjectionRequest(
            source_overlay=stages[0], derived_stages=stages[1:], as_of_date=date(2026, 8, 16)
        ),
    )

    report = build_projection_report(
        projection,
        inputs=ProjectionReportInputs(
            source_bundle_digests=("b" * 64,), fixture_digests=("c" * 64,)
        ),
    )
    assert report == build_projection_report(
        projection,
        inputs=ProjectionReportInputs(
            source_bundle_digests=("b" * 64,), fixture_digests=("c" * 64,)
        ),
    )
    rendered = json.dumps(report, sort_keys=True)
    assert "do-not-report" not in rendered
    assert "still-not-reported" not in rendered
    assert "normalized_payload" in rendered  # field-name-only changed-field reporting is intentional.
    changed = next(item for item in report["surface_diffs"] if item["table"] == "source_event")["changed"]
    assert changed == [
        {
            "identifier": "event:one",
            "changed_fields": ["label", "normalized_payload"],
            "before_hash": changed[0]["before_hash"],
            "after_hash": changed[0]["after_hash"],
        }
    ]


def test_projection_report_has_distinct_semantic_and_full_state_checksums() -> None:
    first = empty_table_state()
    second = empty_table_state()
    first["daily_roster_state"][("state:one",)] = {
        "roster_state_id": "state:one",
        "updated_at": "2026-08-16T00:00:00Z",
    }
    second["daily_roster_state"][("state:one",)] = {
        "roster_state_id": "state:one",
        "updated_at": "2026-08-17T00:00:00Z",
    }
    assert canonical_foundation_state_digest(first, semantic=True) == canonical_foundation_state_digest(
        second, semantic=True
    )
    assert canonical_foundation_state_digest(first, semantic=False) != canonical_foundation_state_digest(
        second, semantic=False
    )


def test_projection_report_persists_only_to_private_non_overwriting_path(tmp_path) -> None:
    os.chmod(tmp_path, 0o700)
    projection = RefreshProjection(
        baseline=FoundationBaseline(empty_table_state(), "a" * 64),
        prefixes=(),
        blockers=(),
        base_export=None,
        visualization_export=None,
    )
    report = build_projection_report(projection)
    path = tmp_path / "projection-report.json"
    write_projection_report(path, report)
    assert json.loads(path.read_text()) == report
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="overwrite"):
        write_projection_report(path, report)
