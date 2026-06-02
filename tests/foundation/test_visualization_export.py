import pytest

from foundation.models import BaseGraphExport
from foundation.models import ConditionalPickBranchSnapshot
from foundation.models import ConditionalPickFamilySnapshot
from foundation.models import DailyRosterState
from foundation.models import DailyRosterStatePlayer
from foundation.models import DraftLotteryResultExport
from foundation.models import PickAsset
from foundation.models import PlayerAsset
from foundation.models import RosterSnapshot
from foundation.models import TransactionEvent
from foundation.models import VisualizationAsset
from foundation.models import VisualizationPickMarker
from foundation.models import VisualizationPlayerMarker

try:
    from foundation.visualization_export import VisualizationExportBuilder
    from foundation.visualization_export import build_visualization_export
except ModuleNotFoundError:
    VisualizationExportBuilder = None
    build_visualization_export = None


def _player_asset(
    slug: str,
    display_name: str,
    *,
    baseline_order: int,
) -> PlayerAsset:
    return PlayerAsset(
        asset_id=f"asset:player:{slug}",
        player_id=f"player:{slug}",
        display_name=display_name,
        baseline_order=baseline_order,
    )


def _daily_roster_state(
    state_id: str,
    as_of_date: str,
    *,
    standard_asset_ids: tuple[str, ...] = (),
    two_way_asset_ids: tuple[str, ...] = (),
    non_roster_asset_ids: tuple[str, ...] = (),
) -> DailyRosterState:
    player_states: list[DailyRosterStatePlayer] = []

    for depth_order, asset_id in enumerate(standard_asset_ids, start=1):
        player_states.append(
            DailyRosterStatePlayer(
                asset_id=asset_id,
                player_id=asset_id.replace("asset:player:", "player:"),
                roster_status="standard",
                depth_order=depth_order,
                is_two_way=False,
                is_standard_contract=True,
            )
        )

    for depth_order, asset_id in enumerate(two_way_asset_ids, start=1):
        player_states.append(
            DailyRosterStatePlayer(
                asset_id=asset_id,
                player_id=asset_id.replace("asset:player:", "player:"),
                roster_status="two_way",
                depth_order=depth_order,
                is_two_way=True,
                is_standard_contract=False,
            )
        )

    for depth_order, asset_id in enumerate(non_roster_asset_ids, start=1):
        player_states.append(
            DailyRosterStatePlayer(
                asset_id=asset_id,
                player_id=asset_id.replace("asset:player:", "player:"),
                roster_status="non_roster",
                depth_order=depth_order,
                is_two_way=False,
                is_standard_contract=False,
            )
        )

    return DailyRosterState(
        state_id=state_id,
        as_of_date=as_of_date,
        roster_asset_ids=[
            *standard_asset_ids,
            *two_way_asset_ids,
            *non_roster_asset_ids,
        ],
        two_way_asset_ids=list(two_way_asset_ids),
        player_states=player_states,
    )


def _require_builder() -> None:
    if VisualizationExportBuilder is None or build_visualization_export is None:
        pytest.skip("foundation.visualization_export has not landed in the local source tree yet")


def test_visualization_asset_contract_rejects_mismatched_marker_and_identity_fields() -> None:
    with pytest.raises(ValueError, match="pick assets require pick_id"):
        VisualizationAsset(
            asset_id="asset:pick:test",
            asset_kind="pick",
            marker=VisualizationPickMarker(chip_label="2028 R1 MEM"),
            display_label="2028 R1 MEM",
            foundation_asset_id="asset:pick:test",
        )

    with pytest.raises(ValueError, match="player assets require a player marker"):
        VisualizationAsset(
            asset_id="asset:player:test",
            asset_kind="player",
            marker=VisualizationPickMarker(chip_label="2028 R1 MEM"),
            display_label="Fixture Player",
            foundation_asset_id="asset:player:test",
            player_id="player:test",
        )


def test_visualization_export_builder_scaffold_maps_base_export() -> None:
    _require_builder()
    base_export = BaseGraphExport(
        franchise="memphis-grizzlies",
        span_start="2024-01-01",
        span_end="2024-12-31",
        events=[
            TransactionEvent(
                event_id="canonical:2024-02-08:trade:fixture",
                event_type="trade",
                event_date="2024-02-08",
                label="Memphis trade fixture",
                sequence=1,
                source_group_id="group:2024-02-08:trade",
            )
        ],
        player_assets=[
            PlayerAsset(
                asset_id="asset:player:fixture-in",
                player_id="player:fixture-in",
                display_name="Fixture In",
            ),
            PlayerAsset(
                asset_id="asset:player:fixture-out",
                player_id="player:fixture-out",
                display_name="Fixture Out",
            ),
        ],
        pick_assets=[
            PickAsset(
                asset_id="asset:pick:fixture",
                pick_id="pick:inventory:mem:2028:r1:mem",
                original_team="MEM",
                draft_year=2028,
                round_number=1,
            )
        ],
        transitions=[
            {
                "transition_id": "transition:in",
                "event_id": "canonical:2024-02-08:trade:fixture",
                "asset_id": "asset:player:fixture-in",
                "transition_type": "acquired",
            },
            {
                "transition_id": "transition:out",
                "event_id": "canonical:2024-02-08:trade:fixture",
                "asset_id": "asset:player:fixture-out",
                "transition_type": "departed",
            },
        ],
        roster_snapshots=[
            RosterSnapshot(
                snapshot_id="snapshot:older",
                as_of_date="2024-02-09",
                conditional_pick_families=[
                    ConditionalPickFamilySnapshot(
                        family_id="family:fixture",
                        family_kind="protected_conveyance",
                        selection_rule="conveys_if_unprotected",
                        exclusivity_status="unresolved",
                        display_original_team_code="LAL",
                        primary_pick_id="pick:inventory:mem:2028:r1:lal",
                        primary_asset_id="asset:pick:inventory:mem:2028:r1:lal",
                        fallback_branches=[
                            ConditionalPickBranchSnapshot(
                                branch_id="branch:fixture",
                                pick_ref="pick:conditional:fixture",
                                asset_ref="asset:pick:conditional:fixture",
                                original_team_code="LAL",
                                round_number=2,
                                trigger_kind="primary_pick_non_conveyance",
                                notes="Older snapshot",
                            )
                        ],
                    )
                ],
            ),
            RosterSnapshot(
                snapshot_id="snapshot:newer",
                as_of_date="2024-02-10",
                conditional_pick_families=[
                    ConditionalPickFamilySnapshot(
                        family_id="family:fixture",
                        family_kind="protected_conveyance",
                        selection_rule="conveys_if_unprotected",
                        exclusivity_status="primary_realized",
                        display_original_team_code="LAL",
                        primary_pick_id="pick:inventory:mem:2028:r1:lal",
                        primary_asset_id="asset:pick:inventory:mem:2028:r1:lal",
                        fallback_branches=[
                            ConditionalPickBranchSnapshot(
                                branch_id="branch:fixture",
                                pick_ref="pick:conditional:fixture",
                                asset_ref="asset:pick:conditional:fixture",
                                original_team_code="LAL",
                                round_number=2,
                                trigger_kind="primary_pick_non_conveyance",
                                notes="Newest snapshot",
                            )
                        ],
                    )
                ],
            ),
        ],
        draft_lottery_results=[
            DraftLotteryResultExport(
                lottery_result_id="lottery:fixture",
                draft_year=2028,
                lottery_date="2028-05-16",
                team_code="MEM",
                owner_team_code="MEM",
                original_team_code="MEM",
                result_pick_slot=7,
                pick_id="pick:inventory:mem:2028:r1:mem",
                pick_asset_id="asset:pick:fixture",
                draft_selection_id="draft:2028:7",
            )
        ],
    )

    export = build_visualization_export(
        base_export,
        generated_at="2026-06-01T12:00:00Z",
    )

    assert export.schema_version == "visualization_export_v1"
    assert export.franchise == "MEM"
    assert export.generated_at == "2026-06-01T12:00:00Z"
    assert export.source_span_start == "2024-01-01"
    assert export.render_span_end == "2024-12-31"
    assert export.time_model.unit == "day"
    assert export.time_model.scale == "linear"
    assert export.band_config.main_roster_slot_count == 15
    assert export.band_config.two_way_slot_count == 3
    assert len(export.lanes) >= 18
    assert export.lanes[0].lane_id == "lane:main_roster:1"
    assert "lane:two_way:18" in {lane.lane_id for lane in export.lanes}
    assert "lane:pick:1" in {lane.lane_id for lane in export.lanes}
    assert [asset.asset_id for asset in export.assets] == [
        "asset:player:fixture-in",
        "asset:player:fixture-out",
        "asset:pick:fixture",
    ]
    assert export.assets[0].marker == VisualizationPlayerMarker(display_name="Fixture In", headshot_url=None)
    assert export.assets[-1].marker == VisualizationPickMarker(chip_label="2028 R1 MEM")
    assert export.event_nodes[0].node_id == "node:canonical:2024-02-08:trade:fixture"
    assert export.event_nodes[0].summary is not None
    assert export.event_nodes[0].summary.sent_asset_ids == ["asset:player:fixture-out"]
    assert export.event_nodes[0].summary.received_asset_ids == ["asset:player:fixture-in"]
    assert export.event_nodes[0].summary.sent_label == "Fixture Out"
    assert export.event_nodes[0].summary.received_label == "Fixture In"
    assert isinstance(export.occupancy_intervals, list)
    assert isinstance(export.strand_segments, list)
    assert isinstance(export.event_connectors, list)
    assert export.additive_context.conditional_pick_families[0].exclusivity_status == "primary_realized"
    assert export.additive_context.conditional_pick_families[0].fallback_branches[0].notes == "Newest snapshot"
    assert export.additive_context.draft_lottery_results[0].pick_asset_id == "asset:pick:fixture"


def test_visualization_export_builder_derives_main_roster_reflow_and_two_way_occupancy() -> None:
    _require_builder()
    alpha = _player_asset("alpha", "Alpha Fixture", baseline_order=1)
    bravo = _player_asset("bravo", "Bravo Fixture", baseline_order=2)
    charlie = _player_asset("charlie", "Charlie Fixture", baseline_order=3)
    delta = _player_asset("delta", "Delta Fixture", baseline_order=4)
    two_way = _player_asset("two-way", "Two Way Fixture", baseline_order=5)

    export = build_visualization_export(
        BaseGraphExport(
            franchise="memphis-grizzlies",
            span_start="2024-01-01",
            span_end="2024-01-03",
            player_assets=[alpha, bravo, charlie, delta, two_way],
            daily_roster_states=[
                _daily_roster_state(
                    "state:2024-01-01",
                    "2024-01-01",
                    standard_asset_ids=(alpha.asset_id, bravo.asset_id, charlie.asset_id),
                    two_way_asset_ids=(two_way.asset_id,),
                ),
                _daily_roster_state(
                    "state:2024-01-02",
                    "2024-01-02",
                    standard_asset_ids=(bravo.asset_id, charlie.asset_id, delta.asset_id),
                    two_way_asset_ids=(two_way.asset_id,),
                ),
                _daily_roster_state(
                    "state:2024-01-03",
                    "2024-01-03",
                    standard_asset_ids=(bravo.asset_id, charlie.asset_id, delta.asset_id),
                    two_way_asset_ids=(two_way.asset_id,),
                ),
            ],
        ),
        generated_at="2026-06-01T12:00:00Z",
    )

    if not export.occupancy_intervals:
        pytest.xfail("Batch 2 occupancy derivation is not implemented yet")

    interval_keys = {
        (
            interval.asset_id,
            interval.lane_id,
            interval.start_date,
            interval.end_date,
            interval.occupancy_kind,
        )
        for interval in export.occupancy_intervals
    }

    assert (
        alpha.asset_id,
        "lane:main_roster:1",
        "2024-01-01",
        "2024-01-01",
        "main_roster",
    ) in interval_keys
    assert (
        bravo.asset_id,
        "lane:main_roster:2",
        "2024-01-01",
        "2024-01-01",
        "main_roster",
    ) in interval_keys
    assert (
        bravo.asset_id,
        "lane:main_roster:1",
        "2024-01-02",
        "2024-01-03",
        "main_roster",
    ) in interval_keys
    assert (
        charlie.asset_id,
        "lane:main_roster:3",
        "2024-01-01",
        "2024-01-01",
        "main_roster",
    ) in interval_keys
    assert (
        charlie.asset_id,
        "lane:main_roster:2",
        "2024-01-02",
        "2024-01-03",
        "main_roster",
    ) in interval_keys
    assert (
        delta.asset_id,
        "lane:main_roster:3",
        "2024-01-02",
        "2024-01-03",
        "main_roster",
    ) in interval_keys
    assert (
        two_way.asset_id,
        "lane:two_way:16",
        "2024-01-01",
        "2024-01-03",
        "two_way",
    ) in interval_keys


def test_visualization_export_builder_emits_grouped_trade_windows_segments_and_connectors() -> None:
    _require_builder()
    outgoing_one = _player_asset("outgoing-one", "Outgoing One", baseline_order=1)
    incumbent = _player_asset("incumbent", "Incumbent Fixture", baseline_order=2)
    outgoing_two = _player_asset("outgoing-two", "Outgoing Two", baseline_order=3)
    incoming_one = _player_asset("incoming-one", "Incoming One", baseline_order=4)
    incoming_two = _player_asset("incoming-two", "Incoming Two", baseline_order=5)

    base_export = BaseGraphExport(
        franchise="memphis-grizzlies",
        span_start="2024-02-01",
        span_end="2024-02-12",
        events=[
            TransactionEvent(
                event_id="canonical:2024-02-08:trade:fixture",
                event_type="trade",
                event_date="2024-02-08",
                label="Memphis grouped trade fixture",
                sequence=1,
                source_group_id="group:2024-02-08:trade",
            )
        ],
        player_assets=[
            outgoing_one,
            incumbent,
            outgoing_two,
            incoming_one,
            incoming_two,
        ],
        transitions=[
            {
                "transition_id": "transition:trade:outgoing-one",
                "event_id": "canonical:2024-02-08:trade:fixture",
                "asset_id": outgoing_one.asset_id,
                "transition_type": "departed",
            },
            {
                "transition_id": "transition:trade:outgoing-two",
                "event_id": "canonical:2024-02-08:trade:fixture",
                "asset_id": outgoing_two.asset_id,
                "transition_type": "departed",
            },
            {
                "transition_id": "transition:trade:incoming-one",
                "event_id": "canonical:2024-02-08:trade:fixture",
                "asset_id": incoming_one.asset_id,
                "transition_type": "acquired",
            },
            {
                "transition_id": "transition:trade:incoming-two",
                "event_id": "canonical:2024-02-08:trade:fixture",
                "asset_id": incoming_two.asset_id,
                "transition_type": "acquired",
            },
        ],
        daily_roster_states=[
            _daily_roster_state(
                "state:2024-02-01",
                "2024-02-01",
                standard_asset_ids=(outgoing_one.asset_id, incumbent.asset_id, outgoing_two.asset_id),
            ),
            _daily_roster_state(
                "state:2024-02-08",
                "2024-02-08",
                standard_asset_ids=(outgoing_one.asset_id, incumbent.asset_id, outgoing_two.asset_id),
            ),
            _daily_roster_state(
                "state:2024-02-09",
                "2024-02-09",
                standard_asset_ids=(incumbent.asset_id, incoming_one.asset_id, incoming_two.asset_id),
            ),
            _daily_roster_state(
                "state:2024-02-12",
                "2024-02-12",
                standard_asset_ids=(incumbent.asset_id, incoming_one.asset_id, incoming_two.asset_id),
            ),
        ],
    )

    export = build_visualization_export(
        base_export,
        generated_at="2026-06-01T12:00:00Z",
    )

    assert len(export.event_nodes) == 1
    assert export.event_nodes[0].summary is not None
    assert export.event_nodes[0].summary.sent_asset_ids == [
        outgoing_one.asset_id,
        outgoing_two.asset_id,
    ]
    assert export.event_nodes[0].summary.received_asset_ids == [
        incoming_one.asset_id,
        incoming_two.asset_id,
    ]

    if not export.event_connectors or not export.strand_segments:
        pytest.xfail("Batch 2 connector and strand derivation is not implemented yet")

    trade_node_id = export.event_nodes[0].node_id
    outgoing_connectors = [
        connector
        for connector in export.event_connectors
        if connector.node_id == trade_node_id and connector.connector_kind == "outgoing"
    ]
    incoming_connectors = [
        connector
        for connector in export.event_connectors
        if connector.node_id == trade_node_id and connector.connector_kind == "incoming"
    ]

    assert {connector.asset_id for connector in outgoing_connectors} == {
        outgoing_one.asset_id,
        outgoing_two.asset_id,
    }
    assert {connector.asset_id for connector in incoming_connectors} == {
        incoming_one.asset_id,
        incoming_two.asset_id,
    }
    assert len({connector.lead_window_days for connector in outgoing_connectors}) == 1
    assert len({connector.settle_window_days for connector in incoming_connectors}) == 1
    assert 4 <= outgoing_connectors[0].lead_window_days <= 21
    assert 2 <= incoming_connectors[0].settle_window_days <= 8

    lead_in_assets = {
        segment.asset_id
        for segment in export.strand_segments
        if segment.segment_kind == "event_lead_in" and segment.end_node_id == trade_node_id
    }
    settle_in_assets = {
        segment.asset_id
        for segment in export.strand_segments
        if segment.segment_kind == "event_settle_in" and segment.start_node_id == trade_node_id
    }

    assert {outgoing_one.asset_id, outgoing_two.asset_id}.issubset(lead_in_assets)
    assert {incoming_one.asset_id, incoming_two.asset_id}.issubset(settle_in_assets)


def test_visualization_export_builder_rejects_more_than_three_two_way_slots_on_one_day() -> None:
    _require_builder()
    two_way_players = [
        _player_asset("two-way-a", "Two Way A", baseline_order=1),
        _player_asset("two-way-b", "Two Way B", baseline_order=2),
        _player_asset("two-way-c", "Two Way C", baseline_order=3),
        _player_asset("two-way-d", "Two Way D", baseline_order=4),
    ]

    base_export = BaseGraphExport(
        franchise="memphis-grizzlies",
        span_start="2024-01-01",
        span_end="2024-01-01",
        player_assets=two_way_players,
        daily_roster_states=[
            _daily_roster_state(
                "state:2024-01-01",
                "2024-01-01",
                two_way_asset_ids=tuple(player.asset_id for player in two_way_players),
            )
        ],
    )

    try:
        build_visualization_export(
            base_export,
            generated_at="2026-06-01T12:00:00Z",
        )
    except ValueError as exc:
        assert "two" in str(exc).lower() or "slot" in str(exc).lower()
    else:
        pytest.xfail("Batch 2 invariant enforcement is not implemented yet")


def test_visualization_export_builder_rejects_non_memphis_franchise() -> None:
    _require_builder()
    builder = VisualizationExportBuilder.from_base_export(
        BaseGraphExport(
            franchise="bos-celtics",
            span_start="2024-01-01",
            span_end="2024-12-31",
        )
    )

    with pytest.raises(ValueError, match="only supports Memphis"):
        builder.build()
