from foundation.export import build_empty_base_export
from foundation.models import BaseGraphExport
from foundation.models import PlayerAsset


def test_build_empty_base_export_has_reset_defaults() -> None:
    export = build_empty_base_export()
    assert isinstance(export, BaseGraphExport)
    assert export.franchise == "memphis-grizzlies"
    assert export.span_start == "2016-07-01"
    assert export.span_end == "2026-06-30"
    assert export.events == []
    assert export.player_assets == []
    assert export.pick_assets == []
    assert export.transitions == []
    assert export.roster_snapshots == []


def test_player_asset_contract_supports_roster_baseline_metadata() -> None:
    asset = PlayerAsset(
        asset_id="asset:player:ja-morant",
        player_id="player:ja-morant",
        display_name="Ja Morant",
        baseline_order=1,
        years_experience=6,
    )
    assert asset.baseline_order == 1
    assert asset.years_experience == 6
