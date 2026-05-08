from foundation.ingest import (
    RosterBaselinePlayerRow,
    build_foundation_ingest_sample_bundle,
    derive_foundation_entities_from_source_events,
)


def test_build_foundation_ingest_sample_bundle_has_core_row_sets() -> None:
    bundle = build_foundation_ingest_sample_bundle()
    assert len(bundle.source_records) == 5
    assert len(bundle.source_events) == 4
    assert len(bundle.players) >= 6
    assert len(bundle.picks) >= 5
    assert len(bundle.assets) == len(bundle.players) + len(bundle.picks)


def test_source_events_are_wired_to_workbench_payloads() -> None:
    bundle = build_foundation_ingest_sample_bundle()
    trade_events = [row for row in bundle.source_events if row.event_type == "trade"]
    assert trade_events
    assert any("player_names_in" in row.normalized_payload for row in trade_events)
    assert any("pick_details_in" in row.normalized_payload for row in trade_events)


def test_assets_point_to_exactly_one_entity_type() -> None:
    bundle = build_foundation_ingest_sample_bundle()
    for asset in bundle.assets:
        if asset.asset_kind == "player":
            assert asset.player_id is not None
            assert asset.pick_id is None
        else:
            assert asset.pick_id is not None
            assert asset.player_id is None


def test_derive_foundation_entities_from_source_events_builds_expected_row_sets() -> None:
    bundle = build_foundation_ingest_sample_bundle()
    derived = derive_foundation_entities_from_source_events(bundle.source_events)
    assert len(derived.players) >= 6
    assert len(derived.picks) >= 5
    assert len(derived.assets) == len(derived.players) + len(derived.picks)


def test_derived_player_and_pick_rows_keep_source_event_alignment() -> None:
    bundle = build_foundation_ingest_sample_bundle()
    derived = derive_foundation_entities_from_source_events(bundle.source_events)
    source_player_names = {
        player_name
        for row in bundle.source_events
        for key in ("player_names_in", "player_names_out")
        for player_name in row.normalized_payload.get(key, [])
    }
    assert any(player.display_name in source_player_names for player in derived.players)
    assert any(pick.draft_year >= 2024 and pick.round_number in (1, 2) for pick in derived.picks)
    assert any(asset.start_source_event_id is not None for asset in derived.assets)


def test_baseline_players_are_merged_into_derived_entities() -> None:
    bundle = build_foundation_ingest_sample_bundle()
    derived = derive_foundation_entities_from_source_events(
        bundle.source_events,
        baseline_players=[
            RosterBaselinePlayerRow(
                season="2023-24",
                team_code="MEM",
                player_id="player:ja-morant",
                display_name="Ja Morant",
                source_record_id="bref:mem:2024:roster",
                roster_order=1,
                nba_player_ref="moranja01",
                position_text="PG",
                years_experience=4,
            )
        ],
    )
    assert any(player.display_name == "Ja Morant" for player in derived.players)
    assert any(asset.player_id == "player:ja-morant" for asset in derived.assets)
