from foundation.audit import build_known_gaps


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
    assert "canonical event span starts after the requested summer 2016 anchor" in gap_text
    assert "Roster checkpoint snapshots are approximate" in gap_text
    assert "Future pick inventory snapshots are empty" in gap_text
    assert "Two-way roster status is not populated" in gap_text
    assert "Draft selections are not fully linked back to pick assets" in gap_text


def test_build_known_gaps_accepts_covered_foundation_metrics() -> None:
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

    assert gaps == []
