import pytest

from foundation.export import DraftResolutionExportRow
from foundation.export import DraftLotteryResultDatabaseRow
from foundation.export import PickInventoryObligationExportRow
from foundation.export import build_base_export
from foundation.export import build_conditional_pick_family_snapshots
from foundation.export import build_draft_lottery_export_rows
from foundation.export import build_draft_resolution_export_items
from foundation.export import build_empty_base_export
from foundation.export import draft_resolution_event_date
from foundation.models import BaseGraphExport
from foundation.models import DraftLotteryResultExport
from foundation.models import DailyRosterState
from foundation.models import DailyRosterStatePlayer
from foundation.models import DraftPriorOwnerLineage
from foundation.models import FuturePickSnapshot
from foundation.models import FoundationExportInputs
from foundation.models import PickAsset
from foundation.models import PlayerAsset
from foundation.models import RosterSnapshot


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
    assert export.daily_roster_states == []
    assert export.draft_prior_owner_lineages == []
    assert export.draft_lottery_results == []


def test_pure_base_export_builder_preserves_the_base_graph_contract() -> None:
    inputs = FoundationExportInputs(
        span_start="2024-02-09",
        span_end="2024-02-10",
        events=[
            {
                "event_id": "event:later",
                "event_type": "trade",
                "event_date": "2024-02-10",
                "label": "Later",
                "sequence": 2,
            },
            {
                "event_id": "event:earlier",
                "event_type": "trade",
                "event_date": "2024-02-09",
                "label": "Earlier",
                "sequence": 1,
            },
        ],
        player_assets=[
            PlayerAsset(
                asset_id="asset:player:fixture",
                player_id="player:fixture",
                display_name="Fixture Player",
            )
        ],
    )

    export = build_base_export(inputs)

    assert isinstance(export, BaseGraphExport)
    assert [event.event_id for event in export.events] == ["event:earlier", "event:later"]
    assert export.player_assets == inputs.player_assets
    assert export.span_start == "2024-02-09"
    assert export.span_end == "2024-02-10"


def test_foundation_export_inputs_round_trip_through_the_pure_builder() -> None:
    existing = BaseGraphExport(
        franchise="memphis-grizzlies",
        span_start="2024-01-01",
        span_end="2024-12-31",
        events=[
            {
                "event_id": "event:fixture",
                "event_type": "trade",
                "event_date": "2024-02-08",
                "label": "Fixture",
            }
        ],
    )

    assert build_base_export(FoundationExportInputs.from_base_graph_export(existing)) == existing


def test_database_wrapper_matches_the_pure_builder_for_typed_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    from foundation import export as export_module

    existing = BaseGraphExport(
        franchise="memphis-grizzlies",
        span_start="2024-01-01",
        span_end="2024-12-31",
        events=[
            {
                "event_id": "event:fixture",
                "event_type": "trade",
                "event_date": "2024-02-08",
                "label": "Fixture",
            }
        ],
    )
    monkeypatch.setattr(
        export_module,
        "_read_base_graph_export_from_database",
        lambda database_url: existing,
    )

    assert export_module.build_base_export_from_database("postgresql://fixture") == build_base_export(
        FoundationExportInputs.from_base_graph_export(existing)
    )


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


def test_roster_snapshot_contract_preserves_future_pick_metadata_and_asset_ids() -> None:
    snapshot = RosterSnapshot(
        snapshot_id="snapshot:mem:2026-27:post_draft",
        as_of_date="2026-07-01",
        snapshot_kind="post_draft",
        season="2026-27",
        future_pick_asset_ids=["asset:pick:inventory:mem:2028:r1:orl"],
        future_picks=[
            FuturePickSnapshot(
                asset_id="asset:pick:inventory:mem:2028:r1:orl",
                pick_id="pick:inventory:mem:2028:r1:orl",
                holding_status="owned",
                display_order=1,
                source_obligation_id="obligation:ready",
                confidence="validated",
                notes="Curated test obligation.",
            )
        ],
    )

    payload = snapshot.model_dump(mode="json")

    assert payload["future_pick_asset_ids"] == ["asset:pick:inventory:mem:2028:r1:orl"]
    assert payload["future_picks"][0]["holding_status"] == "owned"
    assert payload["future_picks"][0]["source_obligation_id"] == "obligation:ready"


def test_roster_snapshot_contract_exposes_composite_right_metadata_for_known_pick_families() -> None:
    snapshot = RosterSnapshot(
        snapshot_id="snapshot:mem:2026-27:post_deadline",
        as_of_date="2027-02-10",
        snapshot_kind="post_deadline",
        season="2026-27",
        future_pick_asset_ids=["asset:pick:inventory:mem:2027:r1:lal"],
        future_picks=[
            FuturePickSnapshot(
                asset_id="asset:pick:inventory:mem:2027:r1:lal",
                pick_id="pick:inventory:mem:2027:r1:lal",
                holding_status="owned",
                source_obligation_id="mem-pick-obligation:2026-02-03:lal-2027-r1-to-mem",
                confidence="validated",
            )
        ],
    )

    payload = snapshot.model_dump(mode="json")
    composite_right = payload["future_picks"][0]["composite_right"]

    assert composite_right["family_kind"] == "protected_conveyance"
    assert composite_right["selection_rule"] == "conveys_if_unprotected"
    assert composite_right["protected_pick_start"] == 1
    assert composite_right["protected_pick_end"] == 4
    assert composite_right["fallback_branches"][0]["projectable"] is False


def test_pick_asset_contract_exposes_tiered_swap_metadata_for_known_slots() -> None:
    asset = PickAsset(
        asset_id="asset:pick:inventory:mem:2030:r1:phx",
        pick_id="pick:inventory:mem:2030:r1:phx",
        original_team="PHX",
        draft_year=2030,
        round_number=1,
        swap_detail="Memphis receives the more favorable of Memphis and the less favorable of Phoenix/Washington.",
    )

    payload = asset.model_dump(mode="json")

    assert payload["composite_right"]["family_kind"] == "tiered_swap_ladder"
    assert payload["composite_right"]["candidate_original_team_codes"] == ["MEM"]
    assert payload["composite_right"]["secondary_candidate_original_team_codes"] == ["PHX", "WAS"]


def test_roster_snapshot_contract_exposes_conditional_pick_family_surface() -> None:
    future_pick = FuturePickSnapshot(
        asset_id="asset:pick:inventory:mem:2027:r1:lal",
        pick_id="pick:inventory:mem:2027:r1:lal",
        holding_status="owned",
        source_obligation_id="mem-pick-obligation:2026-02-03:lal-2027-r1-to-mem",
        confidence="validated",
    )
    conditional_families = build_conditional_pick_family_snapshots(
        future_picks=[future_pick],
        obligation_rows=[
            PickInventoryObligationExportRow(
                obligation_id="mem-pick-obligation:2026-02-03:lal-2027-r2-fallback-to-mem-doc",
                effective_date="2026-02-03",
                perspective_team_code="MEM",
                owner_team_code="MEM",
                original_team_code="LAL",
                draft_year=2027,
                round_number=2,
                direction="incoming",
                holding_status="conditional",
                obligation_type="conditional_fallback",
                confidence="uncertain",
                condition_text="Fallback second if the protected first does not convey.",
                notes="Persisted non-projectable fallback branch.",
                loadable=False,
            )
        ],
    )
    snapshot = RosterSnapshot(
        snapshot_id="snapshot:mem:2026-27:post_deadline",
        as_of_date="2027-02-10",
        snapshot_kind="post_deadline",
        season="2026-27",
        future_pick_asset_ids=[future_pick.asset_id],
        future_picks=[future_pick],
        conditional_pick_families=conditional_families,
    )

    payload = snapshot.model_dump(mode="json")
    family = payload["conditional_pick_families"][0]

    assert family["family_id"] == "family:mem:2027:r1:lal-protected-conveyance"
    assert family["exclusivity_status"] == "unresolved"
    assert family["primary_pick_id"] == "pick:inventory:mem:2027:r1:lal"
    assert family["fallback_branches"][0]["pick_ref"] == (
        "pick:conditional:family:mem:2027:r1:lal-protected-conveyance:r2:lal"
    )
    assert family["fallback_branches"][0]["projectable"] is False


def test_draft_resolution_event_date_handles_two_night_drafts() -> None:
    assert draft_resolution_event_date(2024, 1) == "2024-06-26"
    assert draft_resolution_event_date(2024, 2) == "2024-06-27"
    assert draft_resolution_event_date(2025, 1) == "2025-06-25"
    assert draft_resolution_event_date(2025, 2) == "2025-06-26"


def test_draft_resolution_event_date_requires_known_draft_date() -> None:
    with pytest.raises(ValueError, match="Missing draft event date"):
        draft_resolution_event_date(2030, 1)


def test_daily_roster_state_contract_preserves_depth_and_two_way_metadata() -> None:
    state = DailyRosterState(
        state_id="roster-state-day:mem:2024-02-10",
        as_of_date="2024-02-10",
        season="2023-24",
        roster_asset_ids=["asset:player:desmond-bane"],
        two_way_asset_ids=["asset:player:gg-jackson-ii"],
        player_states=[
            DailyRosterStatePlayer(
                asset_id="asset:player:desmond-bane",
                player_id="player:desmond-bane",
                depth_order=2,
            ),
            DailyRosterStatePlayer(
                asset_id="asset:player:gg-jackson-ii",
                player_id="player:gg-jackson-ii",
                roster_status="two_way",
                depth_order=16,
                is_two_way=True,
                is_standard_contract=False,
            ),
        ],
    )

    payload = state.model_dump(mode="json")

    assert payload["player_states"][1]["roster_status"] == "two_way"
    assert payload["player_states"][1]["depth_order"] == 16
    assert payload["two_way_asset_ids"] == ["asset:player:gg-jackson-ii"]


def test_draft_prior_owner_lineage_contract_preserves_pick_origin_metadata() -> None:
    lineage = DraftPriorOwnerLineage(
        draft_selection_id="draft:2024:39",
        pick_id="pick:inventory:mem:2024:r2:tor",
        pick_asset_id="asset:pick:inventory:mem:2024:r2:tor",
        player_id="player:jaylen-wells",
        player_asset_id="asset:player:jaylen-wells",
        draft_year=2024,
        round_number=2,
        pick_overall=39,
        owner_team_code="MEM",
        original_team_code="TOR",
        source_obligation_id="obligation:2024-r2-tor",
        resolution_kind="inventory_exact_pick",
        confidence="high",
        notes="Selected using Toronto's second-round pick.",
    )

    payload = lineage.model_dump(mode="json")

    assert payload["original_team_code"] == "TOR"
    assert payload["source_obligation_id"] == "obligation:2024-r2-tor"
    assert payload["resolution_kind"] == "inventory_exact_pick"


def test_draft_lottery_export_rows_link_to_pick_truth_without_becoming_events() -> None:
    lottery_rows = build_draft_lottery_export_rows(
        lottery_rows=[
            DraftLotteryResultDatabaseRow(
                lottery_result_id="draft-lottery-result:mem:2024",
                draft_year=2024,
                lottery_date="2024-05-12",
                team_code="MEM",
                owner_team_code="MEM",
                original_team_code="MEM",
                lottery_position=7,
                result_pick_slot=9,
                pre_lottery_odds="6.0%",
                notes="Memphis moves to No. 9.",
            )
        ],
        pick_assets=[
            PickAsset(
                asset_id="asset:pick:inventory:mem:2024:r1:own",
                pick_id="pick:inventory:mem:2024:r1:own",
                original_team="MEM",
                draft_year=2024,
                round_number=1,
            ),
            PickAsset(
                asset_id="asset:pick:slot:2024:9",
                pick_id="pick:slot:2024:9",
                original_team="MEM",
                draft_year=2024,
                round_number=1,
            ),
        ],
        prior_owner_lineages=[
            DraftPriorOwnerLineage(
                draft_selection_id="draft:2024:9",
                pick_id="pick:inventory:mem:2024:r1:own",
                pick_asset_id="asset:pick:inventory:mem:2024:r1:own",
                player_id="player:zach-edey",
                player_asset_id="asset:player:zach-edey",
                draft_year=2024,
                round_number=1,
                pick_overall=9,
                owner_team_code="MEM",
                original_team_code="MEM",
                resolution_kind="team_default_fallback",
                confidence="high",
            )
        ],
    )

    assert lottery_rows == [
        DraftLotteryResultExport(
            lottery_result_id="draft-lottery-result:mem:2024",
            draft_year=2024,
            lottery_date="2024-05-12",
            team_code="MEM",
            owner_team_code="MEM",
            original_team_code="MEM",
            lottery_position=7,
            result_pick_slot=9,
            pre_lottery_odds="6.0%",
            notes="Memphis moves to No. 9.",
            pick_id="pick:inventory:mem:2024:r1:own",
            pick_asset_id="asset:pick:inventory:mem:2024:r1:own",
            draft_selection_id="draft:2024:9",
            draft_selection_player_id="player:zach-edey",
            player_asset_id="asset:player:zach-edey",
        )
    ]


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


def test_build_draft_resolution_export_items_reuses_canonical_draft_event() -> None:
    rows = [
        DraftResolutionExportRow(
            draft_pick_resolution_id="resolution:2024:9",
            draft_selection_id="draft:2024:9",
            pick_asset_id="asset:pick:slot:2024:9",
            player_asset_id="asset:player:zach-edey",
            player_name="Zach Edey",
            draft_year=2024,
            round_number=1,
            pick_overall=9,
            source_bundle_id="source-bundle:2024-draft",
            source_event_id="bref:draft:2024:pick:009",
            canonical_event_id="canonical:2024-06-26:draft:abc123",
        )
    ]

    events, transitions = build_draft_resolution_export_items(rows)

    assert events == []
    assert len(transitions) == 1
    assert transitions[0].event_id == "canonical:2024-06-26:draft:abc123"
    assert transitions[0].transition_id == (
        "canonical:2024-06-26:draft:abc123:"
        "pick-to-player:asset:pick:slot:2024:9:to:asset:player:zach-edey"
    )
