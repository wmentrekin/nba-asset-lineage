from foundation.export import build_empty_base_export
from foundation.canonical import derive_foundation_canonical_bundle
from foundation.ingest import build_foundation_ingest_sample_bundle
from foundation.models import BaseGraphExport
from foundation.models import PickAsset
from foundation.models import PlayerAsset
from foundation.models import TransactionEvent
from foundation.models import draft_event_date
from foundation.sources import get_default_source_plan


def test_empty_base_export_defaults() -> None:
    export = build_empty_base_export()
    assert export.franchise == "memphis-grizzlies"
    assert export.events == []
    assert export.player_assets == []
    assert export.pick_assets == []
    assert export.transitions == []
    assert export.roster_snapshots == []


def test_draft_event_date_covers_reset_span_draft_years() -> None:
    assert draft_event_date(2017, 1) == "2017-06-22"
    assert draft_event_date(2017, 2) == "2017-06-22"


def test_base_graph_export_contract_accepts_first_graph_ready_shape() -> None:
    bundle = build_foundation_ingest_sample_bundle()
    canonical = derive_foundation_canonical_bundle(bundle.source_events)

    export = BaseGraphExport(
        franchise="memphis-grizzlies",
        span_start="2016-07-01",
        span_end="2026-06-30",
        events=[
            TransactionEvent(
                event_id=row.canonical_event_id,
                event_type=row.event_type,
                event_date=row.event_date,
                label=row.label,
                sequence=row.sequence_on_date,
                source_group_id=row.canonical_event_id if row.is_grouped_event else None,
            )
            for row in canonical.canonical_events
        ],
        player_assets=[
            PlayerAsset(
                asset_id=asset.asset_id,
                player_id=asset.player_id,
                display_name=player.display_name,
            )
            for asset in bundle.assets
            if asset.asset_kind == "player" and asset.player_id is not None
            for player in bundle.players
            if player.player_id == asset.player_id
        ],
        pick_assets=[
            PickAsset(
                asset_id=asset.asset_id,
                original_team=pick.original_team or "unknown",
                draft_year=pick.draft_year,
                round_number=pick.round_number,
                protections=pick.protection_text,
                swap_detail=pick.swap_text,
            )
            for asset in bundle.assets
            if asset.asset_kind == "pick" and asset.pick_id is not None
            for pick in bundle.picks
            if pick.pick_id == asset.pick_id
        ],
        transitions=[
            {
                "transition_id": row.transition_id,
                "event_id": row.canonical_event_id,
                "asset_id": row.asset_id,
                "transition_type": row.transition_type,
            }
            for row in canonical.event_asset_transitions
        ],
        roster_snapshots=[],
    )

    assert export.events
    assert export.player_assets
    assert export.pick_assets
    assert export.transitions
    assert export.roster_snapshots == []
    assert {event.event_id for event in export.events} == {
        row.canonical_event_id for row in canonical.canonical_events
    }
    assert {asset.asset_id for asset in export.player_assets} == {
        asset.asset_id for asset in bundle.assets if asset.asset_kind == "player"
    }
    assert {asset.asset_id for asset in export.pick_assets} == {
        asset.asset_id for asset in bundle.assets if asset.asset_kind == "pick"
    }


def test_default_source_plan_includes_required_families() -> None:
    plan = get_default_source_plan()
    source_ids = {definition.source_id for definition in plan.source_definitions}
    assert source_ids == {
        "transactions_log",
        "player_reference",
        "pick_reference",
        "roster_state",
    }
