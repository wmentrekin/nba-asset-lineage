import pytest

from foundation.export import DraftResolutionExportRow
from foundation.export import build_draft_resolution_export_items
from foundation.export import build_empty_base_export
from foundation.export import draft_resolution_event_date
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


def test_draft_resolution_event_date_handles_two_night_drafts() -> None:
    assert draft_resolution_event_date(2024, 1) == "2024-06-26"
    assert draft_resolution_event_date(2024, 2) == "2024-06-27"
    assert draft_resolution_event_date(2025, 1) == "2025-06-25"
    assert draft_resolution_event_date(2025, 2) == "2025-06-26"


def test_draft_resolution_event_date_requires_known_draft_date() -> None:
    with pytest.raises(ValueError, match="Missing draft event date"):
        draft_resolution_event_date(2030, 1)


def test_build_draft_resolution_export_items_emits_pick_to_player_transition() -> None:
    rows = [
        DraftResolutionExportRow(
            draft_pick_resolution_id="resolution:2024:9",
            draft_selection_id="selection:2024:9",
            pick_asset_id="asset:pick:slot:2024:9",
            player_asset_id="asset:player:zach-edey",
            player_name="Zach Edey",
            draft_year=2024,
            round_number=1,
            pick_overall=9,
            source_bundle_id="source-bundle:2024-draft",
            notes="curated Memphis draft slot",
        )
    ]

    events, transitions = build_draft_resolution_export_items(rows)

    assert len(events) == 1
    assert events[0].event_id == "draft-resolution:selection:2024:9"
    assert events[0].event_type == "draft"
    assert events[0].event_date == "2024-06-26"
    assert events[0].label == "Memphis drafts Zach Edey at No. 9"
    assert len(transitions) == 1
    assert transitions[0].transition_type == "pick_to_player"
    assert transitions[0].asset_id == "asset:pick:slot:2024:9"
    assert transitions[0].from_state == "asset:pick:slot:2024:9"
    assert transitions[0].to_state == "asset:player:zach-edey"
    assert transitions[0].notes == "curated Memphis draft slot"
