from foundation.ingest import build_foundation_ingest_sample_bundle


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
