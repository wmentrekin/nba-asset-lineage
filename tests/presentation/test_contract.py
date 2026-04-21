from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime

from canonical.models import (
    AssetState,
    CanonicalAsset,
    CanonicalEvent,
    CanonicalPickAsset,
    CanonicalPickResolution,
    CanonicalPlayerIdentity,
    CanonicalPlayerTenure,
)
from presentation.contract import build_presentation_contract, presentation_contract_to_json
from presentation.validate import validate_presentation_contract


NOW = datetime(2026, 4, 20, 12, 0, 0)


def _event(event_id: str, event_type: str, event_date: str, order: int, label: str) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        event_date=date.fromisoformat(event_date),
        event_order=order,
        event_label=label,
        description=label,
        transaction_group_key=event_id,
        is_compound=False,
        notes=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _identity(player_id: str, name: str) -> CanonicalPlayerIdentity:
    return CanonicalPlayerIdentity(
        player_id=player_id,
        display_name=name,
        normalized_name=name.lower(),
        nba_person_id=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _tenure(
    tenure_id: str,
    player_id: str,
    start: str,
    end: str | None,
    entry_event_id: str,
    exit_event_id: str | None,
) -> CanonicalPlayerTenure:
    return CanonicalPlayerTenure(
        player_tenure_id=tenure_id,
        player_id=player_id,
        tenure_start_date=date.fromisoformat(start),
        tenure_end_date=date.fromisoformat(end) if end else None,
        entry_event_id=entry_event_id,
        exit_event_id=exit_event_id,
        tenure_type="signing",
        roster_path_type="free_agency",
        created_at=NOW,
        updated_at=NOW,
    )


def _asset(asset_id: str, kind: str, label: str, tenure_id: str | None = None, pick_id: str | None = None) -> CanonicalAsset:
    return CanonicalAsset(
        asset_id=asset_id,
        asset_kind=kind,
        player_tenure_id=tenure_id,
        pick_asset_id=pick_id,
        asset_label=label,
        created_at=NOW,
        updated_at=NOW,
    )


def _pick_asset(pick_id: str, current_stage: str = "drafted_player") -> CanonicalPickAsset:
    return CanonicalPickAsset(
        pick_asset_id=pick_id,
        origin_team_code="UTA",
        draft_year=2024,
        draft_round=2,
        protection_summary=None,
        protection_payload={},
        drafted_player_id="player_gg",
        current_pick_stage=current_stage,
        created_at=NOW,
        updated_at=NOW,
    )


def _pick_resolution(
    resolution_id: str,
    pick_id: str,
    state_type: str,
    start: str,
    source_event_id: str | None,
    drafted_player_id: str | None = None,
    state_payload: dict[str, object] | None = None,
) -> CanonicalPickResolution:
    return CanonicalPickResolution(
        pick_resolution_id=resolution_id,
        pick_asset_id=pick_id,
        state_type=state_type,
        effective_start_date=date.fromisoformat(start),
        effective_end_date=None,
        overall_pick_number=45 if state_type in {"resolved_pick", "drafted_player"} else None,
        lottery_context=None,
        drafted_player_id=drafted_player_id,
        source_event_id=source_event_id,
        state_payload=state_payload or {"state_type": state_type},
        created_at=NOW,
        updated_at=NOW,
    )


def _build(**overrides):
    inputs = {
        "events": [],
        "assets": [],
        "player_identities": [],
        "player_tenures": [],
        "pick_assets": [],
        "pick_resolutions": [],
        "asset_states": [],
        "built_at": NOW,
    }
    inputs.update(overrides)
    return build_presentation_contract(**inputs)


def test_simple_player_line_from_signing_to_open_boundary():
    events = [_event("event_sign", "signing", "2024-01-01", 1, "Memphis signs John Doe")]
    result = _build(
        events=events,
        player_identities=[_identity("player_john", "John Doe")],
        player_tenures=[_tenure("tenure_john_1", "player_john", "2024-01-01", None, "event_sign", None)],
        assets=[_asset("asset_john_1", "player_tenure", "John Doe Memphis tenure 1", tenure_id="tenure_john_1")],
    )

    assert [edge.edge_type for edge in result.edges] == ["player_line"]
    edge = result.edges[0]
    assert edge.source_node_id != edge.target_node_id
    assert edge.lane_group == "main_roster"
    assert edge.payload["player_name"] == "John Doe"
    assert edge.end_date == NOW.date()

    report = validate_presentation_contract(nodes=result.nodes, edges=result.edges, lanes=result.lanes, canonical_events=events)
    assert report.ok


def test_returning_player_renders_as_separate_tenure_segments():
    events = [
        _event("event_sign_1", "signing", "2024-01-01", 1, "Memphis signs John Doe"),
        _event("event_waive_1", "waiver", "2024-02-01", 1, "Memphis waives John Doe"),
        _event("event_sign_2", "signing", "2024-03-01", 1, "Memphis re-signs John Doe"),
    ]
    result = _build(
        events=events,
        player_identities=[_identity("player_john", "John Doe")],
        player_tenures=[
            _tenure("tenure_john_1", "player_john", "2024-01-01", "2024-02-01", "event_sign_1", "event_waive_1"),
            _tenure("tenure_john_2", "player_john", "2024-03-01", None, "event_sign_2", None),
        ],
        assets=[
            _asset("asset_john_1", "player_tenure", "John Doe Memphis tenure 1", tenure_id="tenure_john_1"),
            _asset("asset_john_2", "player_tenure", "John Doe Memphis tenure 2", tenure_id="tenure_john_2"),
        ],
    )

    player_edges = [edge for edge in result.edges if edge.payload.get("player_id") == "player_john"]
    assert len(player_edges) == 2
    assert {edge.asset_id for edge in player_edges} == {"asset_john_1", "asset_john_2"}
    assert player_edges[0].end_date < player_edges[1].start_date

    report = validate_presentation_contract(nodes=result.nodes, edges=result.edges, lanes=result.lanes, canonical_events=events)
    assert report.ok


def test_pick_to_player_transition_is_renderable_without_frontend_inference():
    events = [
        _event("event_trade_pick", "trade", "2024-01-10", 1, "Memphis acquires Utah second"),
        _event("event_draft", "draft", "2024-06-26", 1, "Memphis drafts GG Jackson"),
    ]
    result = _build(
        events=events,
        assets=[_asset("asset_pick_45", "pick_continuity", "Utah 2024 round 2 pick", pick_id="pick_45")],
        player_identities=[_identity("player_gg", "GG Jackson")],
        pick_assets=[_pick_asset("pick_45")],
        pick_resolutions=[
            _pick_resolution("resolution_future", "pick_45", "future_pick", "2024-01-10", "event_trade_pick"),
            _pick_resolution("resolution_drafted", "pick_45", "drafted_player", "2024-06-26", "event_draft", "player_gg"),
        ],
    )

    assert [edge.edge_type for edge in result.edges] == ["pick_line", "transition_line"]
    transition = result.edges[1]
    assert transition.asset_id == "asset_pick_45"
    assert transition.lane_group == "main_roster"
    assert transition.payload["drafted_player_id"] == "player_gg"
    assert transition.payload["drafted_player_name"] == "GG Jackson"

    report = validate_presentation_contract(nodes=result.nodes, edges=result.edges, lanes=result.lanes, canonical_events=events)
    assert report.ok


def test_same_day_event_order_is_preserved_in_timeline_nodes():
    events = [
        _event("event_second", "waiver", "2024-02-01", 2, "Second same-day event"),
        _event("event_first", "signing", "2024-02-01", 1, "First same-day event"),
    ]
    result = _build(events=events)

    event_nodes = [node for node in result.nodes if node.event_id]
    assert [(node.event_id, node.event_order) for node in event_nodes] == [
        ("event_first", 1),
        ("event_second", 2),
    ]

    report = validate_presentation_contract(nodes=result.nodes, edges=result.edges, lanes=result.lanes, canonical_events=events)
    assert report.ok


def test_json_contract_shape_has_nodes_edges_lanes_and_meta():
    events = [_event("event_sign", "signing", "2024-01-01", 1, "Memphis signs John Doe")]
    result = _build(
        events=events,
        player_identities=[_identity("player_john", "John Doe")],
        player_tenures=[_tenure("tenure_john_1", "player_john", "2024-01-01", None, "event_sign", None)],
        assets=[_asset("asset_john_1", "player_tenure", "John Doe Memphis tenure 1", tenure_id="tenure_john_1")],
    )

    payload = json.loads(presentation_contract_to_json(result))

    assert set(payload) == {"nodes", "edges", "lanes", "meta"}
    assert "editorial" not in payload
    assert payload["meta"]["node_count"] == len(payload["nodes"])
    assert payload["meta"]["edge_count"] == len(payload["edges"])
    assert payload["meta"]["lane_count"] == len(payload["lanes"])
    assert {"node_id", "event_date", "event_order", "node_type", "label", "payload"} <= set(payload["nodes"][0])
    assert {"edge_id", "asset_id", "source_node_id", "target_node_id", "lane_group", "lane_index", "payload"} <= set(payload["edges"][0])


def test_two_way_lane_uses_explicit_asset_state_payload():
    events = [_event("event_sign", "signing", "2024-01-01", 1, "Memphis signs Two Way Player")]
    state = AssetState(
        asset_state_id="state_two_way",
        asset_id="asset_two_way",
        state_type="player_contract_interval",
        effective_start_date=date.fromisoformat("2024-01-01"),
        effective_end_date=None,
        state_payload={"contract_type": "two-way"},
        source_event_id="event_sign",
        created_at=NOW,
        updated_at=NOW,
    )
    result = _build(
        events=events,
        player_identities=[_identity("player_two_way", "Two Way Player")],
        player_tenures=[_tenure("tenure_two_way", "player_two_way", "2024-01-01", None, "event_sign", None)],
        assets=[_asset("asset_two_way", "player_tenure", "Two Way Player Memphis tenure 1", tenure_id="tenure_two_way")],
        asset_states=[state],
    )

    assert result.edges[0].lane_group == "two_way"
    report = validate_presentation_contract(nodes=result.nodes, edges=result.edges, lanes=result.lanes, canonical_events=events)
    assert report.ok


def test_lane_group_does_not_scan_arbitrary_payload_values():
    events = [_event("event_sign", "signing", "2024-01-01", 1, "Memphis signs Player")]
    state = AssetState(
        asset_state_id="state_notes",
        asset_id="asset_player",
        state_type="player_contract_interval",
        effective_start_date=date.fromisoformat("2024-01-01"),
        effective_end_date=None,
        state_payload={"notes": "contains the words two-way but is not a lane fact"},
        source_event_id="event_sign",
        created_at=NOW,
        updated_at=NOW,
    )
    result = _build(
        events=events,
        player_identities=[_identity("player_notes", "Player Notes")],
        player_tenures=[_tenure("tenure_notes", "player_notes", "2024-01-01", None, "event_sign", None)],
        assets=[_asset("asset_player", "player_tenure", "Player Notes Memphis tenure 1", tenure_id="tenure_notes")],
        asset_states=[state],
    )

    assert result.edges[0].lane_group == "main_roster"
    report = validate_presentation_contract(nodes=result.nodes, edges=result.edges, lanes=result.lanes, canonical_events=events)
    assert report.ok


def test_two_way_drafted_player_transition_uses_explicit_pick_resolution_payload():
    events = [
        _event("event_trade_pick", "trade", "2024-01-10", 1, "Memphis acquires Utah second"),
        _event("event_draft", "draft", "2024-06-26", 1, "Memphis drafts Two Way Prospect"),
    ]
    result = _build(
        events=events,
        assets=[_asset("asset_pick_45", "pick_continuity", "Utah 2024 round 2 pick", pick_id="pick_45")],
        player_identities=[_identity("player_two_way_pick", "Two Way Prospect")],
        pick_assets=[_pick_asset("pick_45")],
        pick_resolutions=[
            _pick_resolution("resolution_future", "pick_45", "future_pick", "2024-01-10", "event_trade_pick"),
            _pick_resolution(
                "resolution_drafted",
                "pick_45",
                "drafted_player",
                "2024-06-26",
                "event_draft",
                "player_two_way_pick",
                state_payload={"state_type": "drafted_player", "contract_type": "two_way"},
            ),
        ],
    )

    transition = next(edge for edge in result.edges if edge.edge_type == "transition_line")
    assert transition.lane_group == "two_way"
    assert transition.payload["drafted_player_id"] == "player_two_way_pick"

    report = validate_presentation_contract(nodes=result.nodes, edges=result.edges, lanes=result.lanes, canonical_events=events)
    assert report.ok


def test_validate_rejects_transition_line_in_future_picks_lane():
    events = [
        _event("event_trade_pick", "trade", "2024-01-10", 1, "Memphis acquires Utah second"),
        _event("event_draft", "draft", "2024-06-26", 1, "Memphis drafts GG Jackson"),
    ]
    result = _build(
        events=events,
        assets=[_asset("asset_pick_45", "pick_continuity", "Utah 2024 round 2 pick", pick_id="pick_45")],
        player_identities=[_identity("player_gg", "GG Jackson")],
        pick_assets=[_pick_asset("pick_45")],
        pick_resolutions=[
            _pick_resolution("resolution_future", "pick_45", "future_pick", "2024-01-10", "event_trade_pick"),
            _pick_resolution(
                "resolution_drafted",
                "pick_45",
                "drafted_player",
                "2024-06-26",
                "event_draft",
                "player_gg",
                state_payload={"state_type": "drafted_player", "lane_group": "future_picks"},
            ),
        ],
    )
    transition = next(edge for edge in result.edges if edge.edge_type == "transition_line")
    transition_lane = next(lane for lane in result.lanes if lane.asset_id == transition.asset_id and lane.effective_start_date == transition.start_date)
    invalid_edges = [
        replace(edge, lane_group="future_picks")
        if edge.edge_id == transition.edge_id
        else edge
        for edge in result.edges
    ]
    invalid_lanes = [
        replace(lane, lane_group="future_picks")
        if lane.asset_lane_id == transition_lane.asset_lane_id
        else lane
        for lane in result.lanes
    ]

    report = validate_presentation_contract(nodes=result.nodes, edges=invalid_edges, lanes=invalid_lanes, canonical_events=events)

    assert not report.ok
    assert any("transition edge must use a roster lane group" in error for error in report.errors)


def test_deterministic_rebuild_stability_for_ids_and_order():
    events = [
        _event("event_trade_pick", "trade", "2024-01-10", 1, "Memphis acquires Utah second"),
        _event("event_draft", "draft", "2024-06-26", 1, "Memphis drafts GG Jackson"),
    ]
    inputs = {
        "events": list(reversed(events)),
        "assets": [_asset("asset_pick_45", "pick_continuity", "Utah 2024 round 2 pick", pick_id="pick_45")],
        "player_identities": [_identity("player_gg", "GG Jackson")],
        "pick_assets": [_pick_asset("pick_45")],
        "pick_resolutions": [
            _pick_resolution("resolution_drafted", "pick_45", "drafted_player", "2024-06-26", "event_draft", "player_gg"),
            _pick_resolution("resolution_future", "pick_45", "future_pick", "2024-01-10", "event_trade_pick"),
        ],
    }

    first = _build(**inputs)
    second = _build(**inputs)

    assert [node.node_id for node in first.nodes] == [node.node_id for node in second.nodes]
    assert [edge.edge_id for edge in first.edges] == [edge.edge_id for edge in second.edges]
    assert [lane.asset_lane_id for lane in first.lanes] == [lane.asset_lane_id for lane in second.lanes]
    assert first.nodes == second.nodes
    assert first.edges == second.edges
    assert first.lanes == second.lanes


def test_same_day_pick_stage_segments_get_distinct_lane_ids():
    events = [_event("event_draft", "draft", "2024-06-26", 1, "Memphis drafts Same Day Player")]
    result = _build(
        events=events,
        assets=[_asset("asset_pick_45", "pick_continuity", "Memphis 2024 round 2 pick", pick_id="pick_45")],
        player_identities=[_identity("player_same_day", "Same Day Player")],
        pick_assets=[_pick_asset("pick_45")],
        pick_resolutions=[
            _pick_resolution("resolution_future", "pick_45", "future_pick", "2024-06-26", "event_draft"),
            _pick_resolution("resolution_resolved", "pick_45", "resolved_pick", "2024-06-26", "event_draft"),
            _pick_resolution("resolution_drafted", "pick_45", "drafted_player", "2024-06-26", "event_draft", "player_same_day"),
        ],
    )

    assert len(result.lanes) == len({lane.asset_lane_id for lane in result.lanes})
    assert len(result.edges) == 3
    report = validate_presentation_contract(nodes=result.nodes, edges=result.edges, lanes=result.lanes, canonical_events=events)
    assert report.ok
