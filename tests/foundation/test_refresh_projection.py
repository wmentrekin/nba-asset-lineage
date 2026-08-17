from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from foundation.refresh_mutations import FoundationMutationPlan, UpsertRows, empty_table_state
from foundation.refresh_projection import (
    APPROVED_PROJECTION_ORDER,
    FoundationBaseline,
    ProjectionStage,
    RefreshProjectionRequest,
    load_read_only_baseline,
    project_refresh,
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
