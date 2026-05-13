import foundation.audit as audit
from foundation.audit import build_known_gaps, fetch_draft_metrics


def test_fetch_draft_metrics_counts_lottery_results_without_draft_selection(monkeypatch) -> None:
    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, sql: str, params: object | None = None) -> None:
            self.sql = sql

        def fetchone(self) -> tuple[int]:
            assert "foundation.draft_lottery_result" in self.sql
            return (4,)

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

    monkeypatch.setattr(
        audit,
        "table_exists",
        lambda connection, table_name: table_name == "draft_lottery_result",
    )

    metrics = fetch_draft_metrics(FakeConnection())

    assert metrics["selections"] == 0
    assert metrics["lottery_results"] == 4
    assert metrics["by_year"] == []


def test_build_known_gaps_surfaces_current_foundation_caveats() -> None:
    gaps = build_known_gaps(
        {
            "counts": {
                "canonical_event": 388,
                "event_asset_transition": 528,
            },
            "event_span": {
                "start_date": "2016-07-07",
                "end_date": "2026-04-10",
            },
            "graph_export_span": {
                "start_date": "2016-07-07",
                "end_date": "2026-04-10",
            },
            "source_coverage": [
                {
                    "source_system": "basketball_reference",
                    "source_type": "transactions_page",
                    "records": 10,
                }
            ],
            "snapshots": {
                "snapshots": 40,
                "pick_rows": 0,
                "date_aware_reconstruction": 0,
                "derived_from_roster_baseline": 40,
                "contract_status": [
                    {
                        "roster_status": "standard",
                        "rows": 888,
                        "two_way_rows": 0,
                    }
                ],
            },
            "draft": {
                "selections": 20,
                "unlinked_pick_rows": 20,
                "resolved_pick_rows": 0,
                "lottery_results": 0,
            },
        }
    )

    gap_text = " ".join(gap["gap"] for gap in gaps)
    assert "graph export span starts after the requested summer 2016 anchor" in gap_text
    assert "Roster checkpoint snapshots are approximate" in gap_text
    assert "Future pick inventory snapshots are empty" in gap_text
    assert "Two-way roster status is not populated" in gap_text
    assert "Draft selections are not fully linked back to pick assets" in gap_text
    assert "Draft lottery results are not loaded" in gap_text


def test_build_known_gaps_preserves_seed_two_way_coverage_caveat() -> None:
    gaps = build_known_gaps(
        {
            "counts": {
                "canonical_event": 10,
                "event_asset_transition": 20,
            },
            "event_span": {
                "start_date": "2016-07-01",
                "end_date": "2026-06-30",
            },
            "graph_export_span": {
                "start_date": "2016-07-01",
                "end_date": "2026-06-30",
            },
            "source_coverage": [
                {
                    "source_system": "nba_stats",
                    "source_type": "common_team_roster",
                    "records": 10,
                }
            ],
            "snapshots": {
                "snapshots": 40,
                "pick_rows": 40,
                "date_aware_reconstruction": 40,
                "derived_from_roster_baseline": 0,
                "contract_status": [
                    {
                        "roster_status": "two_way",
                        "rows": 20,
                        "two_way_rows": 20,
                    }
                ],
            },
            "draft": {
                "selections": 20,
                "unlinked_pick_rows": 0,
                "resolved_pick_rows": 20,
                "lottery_results": 5,
            },
        }
    )

    assert len(gaps) == 2
    assert gaps[0]["severity"] == "low"
    assert "seed-loaded" in gaps[0]["gap"]
    assert gaps[1]["severity"] == "low"
    assert "Draft lottery results are seed-loaded contextual metadata" in gaps[1]["gap"]


def test_build_known_gaps_accepts_graph_span_even_when_canonical_starts_later() -> None:
    gaps = build_known_gaps(
        {
            "counts": {
                "canonical_event": 388,
                "event_asset_transition": 528,
            },
            "event_span": {
                "start_date": "2016-07-07",
                "end_date": "2026-04-10",
            },
            "graph_export_span": {
                "start_date": "2016-06-23",
                "end_date": "2026-04-10",
            },
            "source_coverage": [
                {
                    "source_system": "nba_stats",
                    "source_type": "common_team_roster",
                    "records": 10,
                }
            ],
            "snapshots": {
                "snapshots": 40,
                "pick_rows": 40,
                "date_aware_reconstruction": 40,
                "derived_from_roster_baseline": 0,
                "contract_status": [
                    {
                        "roster_status": "two_way",
                        "rows": 20,
                        "two_way_rows": 20,
                    }
                ],
            },
            "draft": {
                "selections": 20,
                "unlinked_pick_rows": 0,
                "resolved_pick_rows": 20,
                "lottery_results": 5,
            },
        }
    )

    gap_text = " ".join(gap["gap"] for gap in gaps)
    assert "graph export span starts after the requested summer 2016 anchor" not in gap_text


def test_build_known_gaps_clears_empty_lottery_gap_but_preserves_seed_caveat() -> None:
    gaps = build_known_gaps(
        {
            "counts": {
                "canonical_event": 10,
                "event_asset_transition": 20,
            },
            "graph_export_span": {
                "start_date": "2016-07-01",
                "end_date": "2026-06-30",
            },
            "source_coverage": [
                {
                    "source_system": "nba_stats",
                    "source_type": "common_team_roster",
                    "records": 10,
                }
            ],
            "snapshots": {
                "snapshots": 40,
                "pick_rows": 40,
                "date_aware_reconstruction": 40,
                "derived_from_roster_baseline": 0,
                "contract_status": [
                    {
                        "roster_status": "two_way",
                        "rows": 20,
                        "two_way_rows": 20,
                    }
                ],
            },
            "draft": {
                "selections": 20,
                "unlinked_pick_rows": 0,
                "resolved_pick_rows": 20,
                "lottery_results": 4,
            },
        }
    )

    gap_text = " ".join(gap["gap"] for gap in gaps)
    assert "Draft lottery results are not loaded" not in gap_text
    assert "Draft lottery results are seed-loaded contextual metadata" in gap_text
