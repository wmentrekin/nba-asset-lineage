import foundation.audit as audit
from foundation.canonical import derive_foundation_canonical_bundle
from foundation.audit import build_draft_lineage_limitations
from foundation.audit import build_event_span_currentness
from foundation.audit import build_known_gaps
from foundation.audit import build_pick_inventory_fixture_gap_report
from foundation.audit import build_source_corroboration_report
from foundation.audit import build_source_coverage_report
from foundation.audit import CORROBORATING_SOURCE_SYSTEMS
from foundation.audit import fetch_draft_metrics
from foundation.audit import infer_corroboration_fact_type
from foundation.audit import infer_corroboration_fact_type_for_event_row
from foundation.ingest import SourceEventRow, derive_foundation_entities_from_source_events
from foundation.sources import CORROBORATION_REPORT_EVENT_FIELDS


def test_corroborating_source_systems_include_curated_fixture() -> None:
    assert "curated_fixture" in CORROBORATING_SOURCE_SYSTEMS


def test_corroboration_only_nba_movement_rows_do_not_affect_canonical_or_assets() -> None:
    source_events = [
        SourceEventRow(
            source_event_id="bref:mem:2024-02-08:trade",
            source_record_id="bref:mem:2024-02-08",
            event_date="2024-02-08",
            event_type="trade",
            label="Memphis acquired a source-backed player",
            team_scope="MEM",
            source_group_hint="bref:2024-02-08:trade",
            normalized_payload={
                "player_names_in": ["Source Backed Player"],
                "player_names_out": [],
                "pick_details_in": [],
                "pick_details_out": [],
            },
        ),
        SourceEventRow(
            source_event_id="nba_player_movement:fixture-only",
            source_record_id="nba_player_movement:memphis",
            event_date="2024-02-08",
            event_type="signing",
            label="Memphis signed NBA-only Fixture Player",
            team_scope="MEM",
            source_group_hint=None,
            normalized_payload={
                "corroboration_only": True,
                "canonical_exclusion_reason": "nba_player_movement_requires_reconciliation",
                "player_names_in": ["NBA Only Fixture Player"],
                "player_names_out": [],
                "pick_details_in": [],
                "pick_details_out": [
                    {"raw_text": "2030 second-round pick", "draft_year": 2030, "round_number": 2}
                ],
            },
        ),
    ]

    canonical = derive_foundation_canonical_bundle(source_events)
    derived = derive_foundation_entities_from_source_events(source_events)

    assert len(canonical.canonical_events) == 1
    assert len(canonical.canonical_event_members) == 1
    assert canonical.canonical_event_members[0].source_event_id == "bref:mem:2024-02-08:trade"
    assert all("nba_player_movement" not in row.source_event_id for row in canonical.canonical_event_members)
    assert all(player.display_name != "NBA Only Fixture Player" for player in derived.players)
    assert derived.picks == []
    assert all(asset.player_id != "player:nba-only-fixture-player" for asset in derived.assets)


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


def test_build_event_span_currentness_reports_verified_quiet_interval() -> None:
    currentness = build_event_span_currentness(
        {
            "source": "foundation.canonical_event",
            "start_date": "2016-07-07",
            "end_date": "2026-04-10",
            "event_count": 388,
        }
    )

    assert currentness["status"] == "verified_quiet_interval"
    assert currentness["loaded_event_end_date"] == "2026-04-10"
    assert currentness["last_verified_event_date"] == "2026-04-10"
    assert currentness["verified_through"] == "2026-05-14"
    assert currentness["source_basis"]


def test_build_known_gaps_flags_event_span_not_current() -> None:
    gaps = build_known_gaps(
        {
            "counts": {
                "canonical_event": 10,
                "event_asset_transition": 20,
            },
            "event_span_currentness": {
                "status": "behind_verified_last_event",
                "evidence": "Loaded event end date is 2026-03-01.",
            },
            "graph_export_span": {
                "start_date": "2016-07-01",
                "end_date": "2026-03-01",
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
                "validation_rows": 40,
                "source_missing": 0,
                "contract_status": [
                    {
                        "roster_status": "two_way",
                        "rows": 20,
                        "two_way_rows": 20,
                    }
                ],
            },
            "pick_inventory": {
                "obligations": 20,
                "uncertain_rows": 0,
                "documented_only_rows": 0,
                "unknown_owner_rows": 0,
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
    assert "Loaded event span is not current to the latest verified Memphis roster event" in gap_text


def test_build_known_gaps_flags_missing_official_roster_checkpoint_validation() -> None:
    gaps = build_known_gaps(
        {
            "counts": {
                "canonical_event": 10,
                "event_asset_transition": 20,
            },
            "event_span_currentness": {
                "status": "verified_quiet_interval",
                "evidence": "quiet",
            },
            "graph_export_span": {
                "start_date": "2016-07-01",
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
                "validation_rows": 0,
                "source_missing": 0,
                "contract_status": [
                    {
                        "roster_status": "two_way",
                        "rows": 20,
                        "two_way_rows": 20,
                    }
                ],
            },
            "pick_inventory": {
                "obligations": 20,
                "uncertain_rows": 0,
                "documented_only_rows": 0,
                "unknown_owner_rows": 0,
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
    assert "Roster checkpoint snapshots are not yet validated against official season roster references" in gap_text


def test_build_known_gaps_accepts_official_fixture_roster_reference_coverage() -> None:
    gaps = build_known_gaps(
        {
            "counts": {
                "canonical_event": 10,
                "event_asset_transition": 20,
            },
            "event_span_currentness": {
                "status": "verified_quiet_interval",
                "evidence": "quiet",
            },
            "graph_export_span": {
                "start_date": "2016-07-01",
                "end_date": "2026-04-10",
            },
            "source_coverage": [
                {
                    "source_system": "curated_fixture",
                    "source_type": "official_roster_reference",
                    "records": 10,
                }
            ],
            "snapshots": {
                "snapshots": 40,
                "pick_rows": 40,
                "date_aware_reconstruction": 40,
                "derived_from_roster_baseline": 0,
                "validation_rows": 40,
                "source_missing": 0,
                "contract_status": [
                    {
                        "roster_status": "two_way",
                        "rows": 20,
                        "two_way_rows": 20,
                    }
                ],
            },
            "pick_inventory": {
                "obligations": 20,
                "uncertain_rows": 0,
                "documented_only_rows": 0,
                "unknown_owner_rows": 0,
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
    assert "Official roster reference data is not present in the loaded source records" not in gap_text


def test_build_source_coverage_report_flags_missing_corrob_source() -> None:
    report = build_source_coverage_report(
        [
            {
                "source_system": "basketball_reference",
                "source_type": "transactions_page",
                "records": 10,
            }
        ]
    )

    assert report["loaded_source_systems"] == ["basketball_reference"]
    assert report["has_basketball_reference"] is True
    assert report["has_official_or_corrob_source"] is False
    assert report["gaps"][0]["gap"] == "Official or corroborating source coverage is not systematic in loaded records."


def test_build_source_coverage_report_counts_recognized_corrob_providers() -> None:
    report = build_source_coverage_report(
        [
            {
                "source_system": "nba_player_movement",
                "source_type": "transactions_json",
                "records": 2,
            },
            {
                "source_system": "realgm",
                "source_type": "future_draft_picks",
                "records": 1,
            },
        ]
    )

    assert report["loaded_source_systems"] == ["nba_player_movement", "realgm"]
    assert report["has_basketball_reference"] is False
    assert report["has_official_or_corrob_source"] is True
    assert [gap["gap"] for gap in report["gaps"]] == [
        "Basketball-Reference transaction source coverage is absent."
    ]


def test_infer_corroboration_fact_type_maps_supported_event_families() -> None:
    assert infer_corroboration_fact_type("trade") == "player_movement"
    assert infer_corroboration_fact_type("10-day") == "player_movement"
    assert infer_corroboration_fact_type("conversion") == "player_movement"
    assert infer_corroboration_fact_type("two way signing") == "player_movement"
    assert infer_corroboration_fact_type("draft") == "pick_right_detail"
    assert infer_corroboration_fact_type("pick_swap") == "pick_right_detail"
    assert infer_corroboration_fact_type("roster_snapshot") == "roster_snapshot"
    assert infer_corroboration_fact_type("player_reference") == "player_identity"
    assert infer_corroboration_fact_type("unknown_editorial_marker") == "out_of_scope"


def test_infer_corroboration_fact_type_for_event_row_marks_manual_out_of_scope_ids() -> None:
    assert (
        infer_corroboration_fact_type_for_event_row(
            {
                "canonical_event_id": "canonical:2019-07-08:signing:2627d7a402fc",
                "event_type": "signing",
                "_participant_signature": {
                    "player_names_in": {"delon wright"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        )
        == "out_of_scope"
    )


def test_infer_corroboration_fact_type_for_event_row_marks_assetless_player_movement_out_of_scope() -> None:
    assert (
        infer_corroboration_fact_type_for_event_row(
            {
                "canonical_event_id": "canonical:2020-11-22:signing:b1ec41f0d851",
                "event_type": "signing",
                "_participant_signature": {
                    "player_names_in": set(),
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        )
        == "out_of_scope"
    )


def test_build_source_corroboration_report_reconciles_unique_nba_movement_match_to_meets_minimum() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2025-01-01:signing:1",
                "event_date": "2025-01-01",
                "event_type": "signing",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "signing",
                "_participant_signature": {
                    "player_names_in": {"vince williams jr"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2025-01-01",
                "event_type": "signing",
                "_matching_event_type": "signing",
                "_source_event_ids": ["nba_player_movement:abc123"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": {"vince williams jr"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    report = build_source_corroboration_report(event_rows)

    event = report["events"][0]
    assert event["loaded_source_systems"] == ["basketball_reference", "nba_player_movement"]
    assert event["loaded_source_types"] == ["transactions_json", "transactions_page"]
    assert event["corroboration_status"] == "meets_minimum"
    assert event["conflict_status"] == "no_conflict_detected"
    assert any("rows from nba_player_movement" in note for note in event["notes"])
    assert any(
        state["role"] == "structured_player_movement" and state["state"] == "supports_event"
        for state in event["evidence_states"]
    )
    assert any(
        state["role"] == "official_confirmation" and state["state"] == "recognized_provider"
        for state in event["evidence_states"]
    )


def test_build_source_corroboration_report_reconciles_unique_nba_official_match_to_meets_minimum() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2025-02-06:trade:1",
                "event_date": "2025-02-06",
                "event_type": "trade",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "trade",
                "_participant_signature": {
                    "player_names_in": {"marvin bagley iii", "johnny davis"},
                    "player_names_out": {"marcus smart"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2025-02-06",
                "event_type": "trade",
                "_matching_event_type": "trade",
                "_source_event_ids": ["nba_official:wizards-acquire-smart"],
                "loaded_source_systems": ["nba_official"],
                "loaded_source_types": ["transaction_page"],
                "_participant_signature": {
                    "player_names_in": {"marvin bagley iii", "johnny davis"},
                    "player_names_out": {"marcus smart"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference", "nba_official"]
    assert event["corroboration_status"] == "meets_minimum"
    assert event["conflict_status"] == "no_conflict_detected"
    assert any("rows from nba_official" in note for note in event["notes"])


def test_build_source_corroboration_report_allows_multiple_exact_corroborating_sources_for_one_event() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2025-01-01:signing:1",
                "event_date": "2025-01-01",
                "event_type": "signing",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "signing",
                "_participant_signature": {
                    "player_names_in": {"vince williams jr"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2025-01-01",
                "event_type": "signing",
                "_matching_event_type": "signing",
                "_source_event_ids": ["nba_player_movement:abc123"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": {"vince williams jr"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            },
            {
                "event_date": "2025-01-01",
                "event_type": "signing",
                "_matching_event_type": "signing",
                "_source_event_ids": ["nba_official:vince-williams"],
                "loaded_source_systems": ["nba_official"],
                "loaded_source_types": ["news_release_article"],
                "_participant_signature": {
                    "player_names_in": {"vince williams jr"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            },
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference", "nba_official", "nba_player_movement"]
    assert event["corroboration_status"] == "meets_minimum"
    assert event["conflict_status"] == "no_conflict_detected"


def test_build_corroboration_candidate_groups_merge_equivalent_sources() -> None:
    candidate_groups = audit.build_corroboration_candidate_groups(
        [
            (
                "nba_player_movement:jonas",
                "2019-07-11",
                "signing",
                None,
                {
                    "player_names_in": ["Jonas Valanciunas"],
                    "player_names_out": [],
                    "pick_details_in": [],
                    "pick_details_out": [],
                },
                "nba_player_movement",
                "transactions_json",
            ),
            (
                "team_official:jonas",
                "2019-07-11",
                "signing",
                None,
                {
                    "player_names_in": ["Jonas Valanciunas"],
                    "player_names_out": [],
                    "pick_details_in": [],
                    "pick_details_out": [],
                },
                "team_official",
                "transaction_page",
            ),
        ]
    )

    assert len(candidate_groups) == 1
    assert candidate_groups[0]["loaded_source_systems"] == ["nba_player_movement", "team_official"]
    assert candidate_groups[0]["_source_event_ids"] == ["nba_player_movement:jonas", "team_official:jonas"]


def test_build_source_corroboration_report_reconciles_diacritic_name_variant() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2019-07-11:signing:jonas",
                "event_date": "2019-07-11",
                "event_type": "signing",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "signing",
                "_participant_signature": {
                    "player_names_in": {"jonas valančiūnas"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2019-07-11",
                "event_type": "signing",
                "_matching_event_type": "signing",
                "_source_event_ids": ["team_official:jonas"],
                "loaded_source_systems": ["team_official"],
                "loaded_source_types": ["transaction_page"],
                "_participant_signature": {
                    "player_names_in": {"jonas valanciunas"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference", "team_official"]
    assert event["conflict_status"] == "no_conflict_detected"
    assert event["corroboration_status"] == "meets_minimum"
    assert any(
        state["role"] == "official_confirmation" and state["state"] == "supports_event"
        for state in event["evidence_states"]
    )
    assert any(
        state["role"] == "structured_player_movement" and state["state"] == "recognized_provider"
        for state in event["evidence_states"]
    )


def test_build_source_corroboration_report_reconciles_suffix_variant_match() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2018-02-08:waiver:1",
                "event_date": "2018-02-08",
                "event_type": "waiver",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "waiver",
                "_participant_signature": {
                    "player_names_in": set(),
                    "player_names_out": {"james ennis"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2018-02-08",
                "event_type": "release",
                "_matching_event_type": "waiver",
                "_source_event_ids": ["nba_player_movement:james-ennis-iii"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": set(),
                    "player_names_out": {"james ennis iii"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference", "nba_player_movement"]
    assert event["conflict_status"] == "no_conflict_detected"
    assert any("rows from nba_player_movement" in note for note in event["notes"])


def test_build_source_corroboration_report_reconciles_safe_first_name_variant_match() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2018-01-15:signing:1",
                "event_date": "2018-01-15",
                "event_type": "signing",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "signing",
                "_participant_signature": {
                    "player_names_in": {"vince hunter"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2018-01-15",
                "event_type": "signing",
                "_matching_event_type": "signing",
                "_source_event_ids": ["nba_player_movement:vincent-hunter"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": {"vincent hunter"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference", "nba_player_movement"]
    assert event["conflict_status"] == "no_conflict_detected"
    assert any("rows from nba_player_movement" in note for note in event["notes"])


def test_build_source_corroboration_report_reconciles_grouped_trade_rows() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2024-02-08:trade:grouped",
                "event_date": "2024-02-08",
                "event_type": "trade",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "trade",
                "_participant_signature": {
                    "player_names_in": {"player a", "player b"},
                    "player_names_out": {"player c", "player d"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2024-02-08",
                "event_type": "trade",
                "_matching_event_type": "trade",
                "_source_event_ids": ["nba_player_movement:part1"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": {"player a"},
                    "player_names_out": {"player c"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            },
            {
                "event_date": "2024-02-08",
                "event_type": "trade",
                "_matching_event_type": "trade",
                "_source_event_ids": ["nba_player_movement:part2"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": {"player b"},
                    "player_names_out": {"player d"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            },
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference", "nba_player_movement"]
    assert event["conflict_status"] == "no_conflict_detected"
    assert any("grouped same-day" in note for note in event["notes"])


def test_build_source_corroboration_report_reconciles_unique_nearby_signing_match() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2025-01-04:signing:nearby",
                "event_date": "2025-01-04",
                "event_type": "signing",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "signing",
                "_participant_signature": {
                    "player_names_in": {"player x"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2025-01-03",
                "event_type": "signing",
                "_matching_event_type": "signing",
                "_source_event_ids": ["nba_player_movement:player-x"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": {"player x"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference", "nba_player_movement"]
    assert event["conflict_status"] == "no_conflict_detected"
    assert any("offset by 1 day" in note for note in event["notes"])


def test_build_source_corroboration_report_does_not_force_ambiguous_nearby_signing_match() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2025-01-04:signing:ambiguous",
                "event_date": "2025-01-04",
                "event_type": "signing",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "signing",
                "_participant_signature": {
                    "player_names_in": {"player x"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2025-01-03",
                "event_type": "signing",
                "_matching_event_type": "signing",
                "_source_event_ids": ["nba_player_movement:player-x:1"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": {"player x"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            },
            {
                "event_date": "2025-01-05",
                "event_type": "signing",
                "_matching_event_type": "signing",
                "_source_event_ids": ["nba_player_movement:player-x:2"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": {"player x"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            },
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference"]
    assert event["corroboration_status"] == "bref_only"
    assert event["conflict_status"] == "not_evaluated"


def test_build_source_corroboration_report_flags_nba_movement_mismatch_without_overlinking() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2024-02-08:trade:1",
                "event_date": "2024-02-08",
                "event_type": "trade",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "trade",
                "_participant_signature": {
                    "player_names_in": {"marcus smart", "jake laravia"},
                    "player_names_out": {"luke kennard"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2024-02-08",
                "event_type": "trade",
                "_matching_event_type": "trade",
                "_source_event_ids": ["nba_player_movement:def456"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": {"marcus smart"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    report = build_source_corroboration_report(event_rows)

    event = report["events"][0]
    assert event["loaded_source_systems"] == ["basketball_reference"]
    assert event["corroboration_status"] == "bref_only"
    assert event["conflict_status"] == "conflict_suspected"
    assert any("do not fully align" in note for note in event["notes"])


def test_build_source_corroboration_report_does_not_force_trade_match_from_variant_overlap() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2018-02-08:trade:1",
                "event_date": "2018-02-08",
                "event_type": "trade",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
                "_matching_event_type": "trade",
                "_participant_signature": {
                    "player_names_in": {"vincent hunter", "ben mclemore"},
                    "player_names_out": {"james ennis"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2018-02-08",
                "event_type": "trade",
                "_matching_event_type": "trade",
                "_source_event_ids": ["nba_player_movement:vince-hunter-only"],
                "loaded_source_systems": ["nba_player_movement"],
                "loaded_source_types": ["transactions_json"],
                "_participant_signature": {
                    "player_names_in": {"vince hunter"},
                    "player_names_out": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference"]
    assert event["corroboration_status"] == "bref_only"
    assert event["conflict_status"] == "conflict_suspected"


def test_build_source_corroboration_report_flags_bref_only_events() -> None:
    report = build_source_corroboration_report(
        [
            {
                "canonical_event_id": "canonical:2024-02-08:trade:1",
                "event_date": "2024-02-08",
                "event_type": "trade",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
            }
        ]
    )

    assert report["policy_version"]
    assert report["summary"]["reporting_unit"] == "canonical_event"
    assert report["summary"]["event_fields"] == list(CORROBORATION_REPORT_EVENT_FIELDS)
    assert report["summary"]["bref_only_events"] == 1

    event = report["events"][0]
    assert set(event) == set(CORROBORATION_REPORT_EVENT_FIELDS)
    assert event["canonical_event_id"] == "canonical:2024-02-08:trade:1"
    assert event["fact_type"] == "player_movement"
    assert event["loaded_source_systems"] == ["basketball_reference"]
    assert event["recognized_provider_roles"] == [
        "chronology_spine",
        "structured_player_movement",
        "official_confirmation",
    ]
    assert event["required_source_roles"] == ["chronology_spine"]
    assert event["missing_roles"] == []
    assert event["corroboration_status"] == "bref_only"
    assert event["conflict_status"] == "not_evaluated"
    assert any(
        state["role"] == "structured_player_movement" and state["state"] == "recognized_provider"
        for state in event["evidence_states"]
    )


def test_build_source_corroboration_report_reconciles_exact_draft_match_with_safe_alias() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2023-06-22:draft:45",
                "event_date": "2023-06-22",
                "event_type": "draft",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["draft_results"],
                "_matching_event_type": "draft",
                "_participant_signature": {
                    "player_names_in": {"gregory jackson ii"},
                    "player_names_out": set(),
                    "draft_selection_ids": {"draft:2023:45"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2023-06-22",
                "event_type": "draft",
                "_matching_event_type": "draft",
                "_source_event_ids": ["curated_fixture:draft:2023:45"],
                "loaded_source_systems": ["curated_fixture"],
                "loaded_source_types": ["draft_pick_detail"],
                "_participant_signature": {
                    "player_names_in": {"gg jackson ii"},
                    "player_names_out": set(),
                    "draft_selection_ids": {"draft:2023:45"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference", "curated_fixture"]
    assert event["loaded_source_types"] == ["draft_pick_detail", "draft_results"]
    assert event["corroboration_status"] == "meets_minimum"
    assert event["conflict_status"] == "no_conflict_detected"
    assert any("rows from curated_fixture" in note for note in event["notes"])
    assert any(
        state["role"] == "secondary_pick_detail" and state["state"] == "supports_event"
        for state in event["evidence_states"]
    )
    assert any(
        state["role"] == "official_confirmation" and state["state"] == "recognized_provider"
        for state in event["evidence_states"]
    )


def test_build_source_corroboration_report_reuses_exact_draft_match_for_duplicate_same_day_rows() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2024-06-26:draft:39:a",
                "event_date": "2024-06-26",
                "event_type": "draft",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["draft_results"],
                "_matching_event_type": "draft",
                "_participant_signature": {
                    "player_names_in": {"jaylen wells"},
                    "player_names_out": set(),
                    "draft_selection_ids": {"draft:2024:39"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            },
            {
                "canonical_event_id": "canonical:2024-06-26:draft:39:b",
                "event_date": "2024-06-26",
                "event_type": "draft",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["draft_results"],
                "_matching_event_type": "draft",
                "_participant_signature": {
                    "player_names_in": {"jaylen wells"},
                    "player_names_out": set(),
                    "draft_selection_ids": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 2,
            },
        ],
        [
            {
                "event_date": "2024-06-26",
                "event_type": "draft",
                "_matching_event_type": "draft",
                "_source_event_ids": ["curated_fixture:draft:2024:39"],
                "loaded_source_systems": ["curated_fixture"],
                "loaded_source_types": ["draft_pick_detail"],
                "_participant_signature": {
                    "player_names_in": {"jaylen wells"},
                    "player_names_out": set(),
                    "draft_selection_ids": {"draft:2024:39"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    events = build_source_corroboration_report(event_rows)["events"]

    assert len(events) == 2
    by_id = {event["canonical_event_id"]: event for event in events}
    for event in events:
        assert event["loaded_source_systems"] == ["basketball_reference", "curated_fixture"]
        assert event["corroboration_status"] == "meets_minimum"
        assert event["conflict_status"] == "no_conflict_detected"
        assert any(
            state["role"] == "official_confirmation" and state["state"] == "recognized_provider"
            for state in event["evidence_states"]
        )
    assert any(
        "duplicate canonical draft rows" in note
        for note in by_id["canonical:2024-06-26:draft:39:b"]["notes"]
    )


def test_build_source_corroboration_report_reuses_exact_draft_match_for_nearby_day_duplicate_rows() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2025-06-26:draft:48:a",
                "event_date": "2025-06-26",
                "event_type": "draft",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["draft_results"],
                "_matching_event_type": "draft",
                "_participant_signature": {
                    "player_names_in": {"javon small"},
                    "player_names_out": set(),
                    "draft_selection_ids": {"draft:2025:48"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            },
            {
                "canonical_event_id": "canonical:2025-06-25:draft:48:b",
                "event_date": "2025-06-25",
                "event_type": "draft",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["team_transactions_page"],
                "_matching_event_type": "draft",
                "_participant_signature": {
                    "player_names_in": {"javon small"},
                    "player_names_out": set(),
                    "draft_selection_ids": set(),
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 2,
            },
        ],
        [
            {
                "event_date": "2025-06-26",
                "event_type": "draft",
                "_matching_event_type": "draft",
                "_source_event_ids": ["curated_fixture:draft:2025:48"],
                "loaded_source_systems": ["curated_fixture"],
                "loaded_source_types": ["draft_pick_detail"],
                "_participant_signature": {
                    "player_names_in": {"javon small"},
                    "player_names_out": set(),
                    "draft_selection_ids": {"draft:2025:48"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    events = build_source_corroboration_report(event_rows)["events"]

    assert len(events) == 2
    by_id = {event["canonical_event_id"]: event for event in events}
    for event in events:
        assert event["loaded_source_systems"] == ["basketball_reference", "curated_fixture"]
        assert event["corroboration_status"] == "meets_minimum"
        assert event["conflict_status"] == "no_conflict_detected"
        assert any(
            state["role"] == "official_confirmation" and state["state"] == "recognized_provider"
            for state in event["evidence_states"]
        )
    assert any(
        "duplicate canonical draft rows" in note
        for note in by_id["canonical:2025-06-25:draft:48:b"]["notes"]
    )


def test_build_source_corroboration_report_keeps_draft_matching_selection_exact() -> None:
    event_rows = audit.reconcile_corroboration_report_event_rows(
        [
            {
                "canonical_event_id": "canonical:2024-06-26:draft:39",
                "event_date": "2024-06-26",
                "event_type": "draft",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["draft_results"],
                "_matching_event_type": "draft",
                "_participant_signature": {
                    "player_names_in": {"jaylen wells"},
                    "player_names_out": set(),
                    "draft_selection_ids": {"draft:2024:39"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
                "_sequence_on_date": 1,
            }
        ],
        [
            {
                "event_date": "2024-06-26",
                "event_type": "draft",
                "_matching_event_type": "draft",
                "_source_event_ids": ["curated_fixture:draft:2024:45"],
                "loaded_source_systems": ["curated_fixture"],
                "loaded_source_types": ["draft_pick_detail"],
                "_participant_signature": {
                    "player_names_in": {"jaylen wells"},
                    "player_names_out": set(),
                    "draft_selection_ids": {"draft:2024:45"},
                    "pick_details_in": set(),
                    "pick_details_out": set(),
                },
            }
        ],
    )

    event = build_source_corroboration_report(event_rows)["events"][0]

    assert event["loaded_source_systems"] == ["basketball_reference"]
    assert event["missing_roles"] == ["secondary_pick_detail"]
    assert event["corroboration_status"] == "missing_required_evidence"
    assert event["conflict_status"] == "conflict_suspected"
    assert any("Missing required source roles: secondary_pick_detail." in note for note in event["notes"])
    assert any("curated_fixture" in note for note in event["notes"])


def test_build_source_corroboration_report_uses_pick_policy_for_draft_events() -> None:
    report = build_source_corroboration_report(
        [
            {
                "canonical_event_id": "canonical:2024-06-26:draft:1",
                "event_date": "2024-06-26",
                "event_type": "draft",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["draft_results"],
            }
        ]
    )

    event = report["events"][0]
    assert event["fact_type"] == "pick_right_detail"
    assert event["recognized_provider_roles"] == [
        "secondary_pick_detail",
        "official_confirmation",
    ]
    assert event["required_source_roles"] == ["secondary_pick_detail"]
    assert event["missing_roles"] == ["secondary_pick_detail"]
    assert event["corroboration_status"] == "missing_required_evidence"


def test_build_source_corroboration_report_marks_unsupported_events_out_of_scope() -> None:
    report = build_source_corroboration_report(
        [
            {
                "canonical_event_id": "canonical:2024-01-01:chapter_marker:1",
                "event_date": "2024-01-01",
                "event_type": "chapter_marker",
                "loaded_source_systems": ["basketball_reference"],
                "loaded_source_types": ["transactions_page"],
            }
        ]
    )

    event = report["events"][0]
    assert event["fact_type"] == "out_of_scope"
    assert event["recognized_provider_roles"] == []
    assert event["required_source_roles"] == []
    assert event["corroboration_status"] == "out_of_scope"
    assert event["conflict_status"] == "not_evaluated"


def test_build_source_corroboration_report_does_not_count_planned_providers_as_loaded() -> None:
    report = build_source_corroboration_report(
        [
            {
                "canonical_event_id": "canonical:2025-01-01:signing:1",
                "event_date": "2025-01-01",
                "event_type": "signing",
                "loaded_source_systems": [],
                "loaded_source_types": [],
            }
        ]
    )

    event = report["events"][0]
    assert event["loaded_source_systems"] == []
    assert event["recognized_provider_roles"] == [
        "chronology_spine",
        "structured_player_movement",
        "official_confirmation",
    ]
    assert event["missing_roles"] == ["chronology_spine"]
    assert event["corroboration_status"] == "missing_required_evidence"
    assert any(
        state["role"] == "chronology_spine" and state["state"] == "missing_required_evidence"
        for state in event["evidence_states"]
    )
    assert all(
        state["loaded_source_systems"] == []
        for state in event["evidence_states"]
    )


def test_build_pick_inventory_fixture_gap_report_surfaces_non_loadable_and_unknown_owner(tmp_path) -> None:
    fixture_path = tmp_path / "pick_obligations.json"
    fixture_path.write_text(
        """
        {
          "fixture_id": "test",
          "team_code": "MEM",
          "rows": [
            {
              "obligation_id": "obligation:unknown-owner",
              "effective_date": "2026-06-15",
              "perspective_team_code": "MEM",
              "owner_team_code": "UNKNOWN",
              "original_team_code": "ORL",
              "draft_year": 2028,
              "round_number": 1,
              "direction": "outgoing",
              "holding_status": "owed_out",
              "obligation_type": "traded_pick",
              "source_urls": ["https://example.test/unknown"],
              "source_labels": ["Example"],
              "retrieved_at": "2026-05-14T00:00:00Z",
              "confidence": "validated",
              "loadable": true
            },
            {
              "obligation_id": "obligation:fallback",
              "effective_date": "2026-06-15",
              "perspective_team_code": "MEM",
              "owner_team_code": "MEM",
              "original_team_code": "LAL",
              "draft_year": 2027,
              "round_number": 2,
              "direction": "incoming",
              "holding_status": "conditional",
              "obligation_type": "conditional_fallback",
              "source_urls": ["https://example.test/fallback"],
              "source_labels": ["Example"],
              "retrieved_at": "2026-05-14T00:00:00Z",
              "confidence": "uncertain",
              "loadable": false,
              "notes": "Fallback row, not active projection."
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    report = build_pick_inventory_fixture_gap_report(fixture_path)

    assert report["fixture_rows"] == 2
    assert report["loadable_rows"] == 1
    assert report["non_loadable_rows"] == 1
    assert report["unknown_owner_rows"] == 1
    assert report["non_loadable_samples"][0]["obligation_id"] == "obligation:fallback"
    assert report["unknown_owner_samples"][0]["obligation_id"] == "obligation:unknown-owner"


def test_build_known_gaps_surfaces_pick_inventory_reporting_details() -> None:
    gaps = build_known_gaps(
        {
            "counts": {
                "canonical_event": 10,
                "event_asset_transition": 20,
            },
            "graph_export_span": {
                "start_date": "2016-07-01",
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
                "validation_rows": 40,
                "source_missing": 0,
                "contract_status": [
                    {
                        "roster_status": "two_way",
                        "rows": 20,
                        "two_way_rows": 20,
                    }
                ],
            },
            "pick_inventory": {
                "obligations": 20,
                "uncertain_rows": 0,
                "documented_only_rows": 0,
                "unknown_owner_rows": 1,
            },
            "pick_inventory_fixture_gap_report": {
                "unknown_owner_rows": 1,
                "non_loadable_rows": 2,
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
    assert "Future pick obligation ledger has UNKNOWN owner rows" in gap_text
    assert "Future pick obligation fixture has UNKNOWN owner rows" in gap_text
    assert "Future pick obligation fixture includes non-loadable fallback documentation rows" in gap_text


def test_build_draft_lineage_limitations_clears_once_prior_owner_rows_cover_all_selections() -> None:
    limitations = build_draft_lineage_limitations(
        {
            "draft": {
                "selections": 20,
                "resolved_pick_rows": 20,
                "prior_owner_lineage_rows": 20,
            }
        }
    )

    assert limitations == []


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
                "validation_rows": 40,
                "source_missing": 0,
                "contract_status": [
                    {
                        "roster_status": "two_way",
                        "rows": 20,
                        "two_way_rows": 20,
                    }
                ],
            },
            "daily_roster_state": {
                "days": 3653,
                "span_start": "2016-07-01",
                "span_end": "2026-06-30",
                "internal_missing_days": 0,
                "coverage_complete": True,
            },
            "pick_inventory": {
                "obligations": 20,
                "uncertain_rows": 0,
                "documented_only_rows": 0,
            },
            "draft": {
                "selections": 20,
                "unlinked_pick_rows": 0,
                "resolved_pick_rows": 20,
                "prior_owner_lineage_rows": 20,
                "lottery_results": 5,
            },
        }
    )

    assert len(gaps) == 2
    assert gaps[0]["severity"] == "low"
    assert "seed-loaded" in gaps[0]["gap"]


def test_build_known_gaps_clears_two_way_gap_once_fixture_is_complete() -> None:
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
                "validation_rows": 40,
                "source_missing": 0,
                "contract_status": [
                    {
                        "roster_status": "two_way",
                        "rows": 20,
                        "two_way_rows": 20,
                    }
                ],
            },
            "two_way_status": {
                "status": "complete_historical_coverage",
                "fixture_rows": 17,
                "loadable_fixture_rows": 17,
                "non_loadable_fixture_rows": 0,
                "loaded_two_way_rows": 20,
            },
            "daily_roster_state": {
                "days": 3653,
                "span_start": "2016-07-01",
                "span_end": "2026-06-30",
                "internal_missing_days": 0,
                "coverage_complete": True,
            },
            "pick_inventory": {
                "obligations": 20,
                "uncertain_rows": 0,
                "documented_only_rows": 0,
            },
            "draft": {
                "selections": 20,
                "unlinked_pick_rows": 0,
                "resolved_pick_rows": 20,
                "prior_owner_lineage_rows": 20,
                "lottery_results": 5,
            },
        }
    )

    gap_text = " ".join(gap["gap"] for gap in gaps)
    assert "Two-way roster status" not in gap_text


def test_build_known_gaps_flags_incomplete_contract_semantics() -> None:
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
                "validation_rows": 40,
                "source_missing": 0,
                "contract_status": [
                    {
                        "roster_status": "two_way",
                        "rows": 20,
                        "two_way_rows": 20,
                    }
                ],
            },
            "two_way_status": {
                "status": "complete_historical_coverage",
                "fixture_rows": 17,
                "loadable_fixture_rows": 17,
                "non_loadable_fixture_rows": 0,
                "loaded_two_way_rows": 20,
            },
            "contract_semantics": {
                "status": "incomplete",
                "candidate_event_count": 20,
                "missing_required_field_count": 3,
            },
            "daily_roster_state": {
                "days": 3653,
                "span_start": "2016-07-01",
                "span_end": "2026-06-30",
                "internal_missing_days": 0,
                "coverage_complete": True,
            },
            "pick_inventory": {
                "obligations": 20,
                "uncertain_rows": 0,
                "documented_only_rows": 0,
            },
            "draft": {
                "selections": 20,
                "unlinked_pick_rows": 0,
                "resolved_pick_rows": 20,
                "prior_owner_lineage_rows": 20,
                "lottery_results": 5,
            },
        }
    )

    gap_text = " ".join(gap["gap"] for gap in gaps)
    assert "Structured contract-semantics coverage is incomplete" in gap_text
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
            "pick_inventory": {
                "obligations": 20,
                "uncertain_rows": 0,
                "documented_only_rows": 0,
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
            "pick_inventory": {
                "obligations": 20,
                "uncertain_rows": 0,
                "documented_only_rows": 0,
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
