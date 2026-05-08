from __future__ import annotations

from datetime import date, datetime

from canonical.models import (
    CanonicalAsset,
    CanonicalEvent,
    CanonicalEventAssetFlow,
    CanonicalPickResolution,
    CanonicalPlayerTenure,
    EventAssetFlowProvenance,
    EventProvenance,
)
from canonical.event_asset_flow import build_event_asset_flows
from canonical.validate_event_asset_flow import validate_canonical_event_asset_flows


NOW = datetime(2026, 4, 16, 12, 0, 0)


def _event(event_id: str, event_type: str, event_date: str, order: int, description: str) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        event_date=date.fromisoformat(event_date),
        event_order=order,
        event_label=description,
        description=description,
        transaction_group_key=event_id,
        is_compound=False,
        notes=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _event_prov(event_id: str, claim_id: str, role: str = "event_date_support") -> EventProvenance:
    return EventProvenance(
        event_provenance_id=f"prov_{event_id}_{claim_id}",
        event_id=event_id,
        source_record_id=f"source_{event_id}",
        claim_id=claim_id,
        override_id=None,
        provenance_role=role,
        fallback_reason=None,
        created_at=NOW,
    )


def _player_tenure(
    tenure_id: str,
    player_id: str,
    entry_event_id: str,
    exit_event_id: str | None,
    tenure_type: str,
) -> CanonicalPlayerTenure:
    return CanonicalPlayerTenure(
        player_tenure_id=tenure_id,
        player_id=player_id,
        tenure_start_date=date.fromisoformat("2024-01-01"),
        tenure_end_date=date.fromisoformat("2024-03-01") if exit_event_id else None,
        entry_event_id=entry_event_id,
        exit_event_id=exit_event_id,
        tenure_type=tenure_type,
        roster_path_type="free_agency" if tenure_type != "draft" else "draft",
        created_at=NOW,
        updated_at=NOW,
    )


def _asset(asset_id: str, asset_kind: str, player_tenure_id: str | None, pick_asset_id: str | None, label: str) -> CanonicalAsset:
    return CanonicalAsset(
        asset_id=asset_id,
        asset_kind=asset_kind,
        player_tenure_id=player_tenure_id,
        pick_asset_id=pick_asset_id,
        asset_label=label,
        created_at=NOW,
        updated_at=NOW,
    )


def _pick_resolution(
    resolution_id: str,
    pick_asset_id: str,
    state_type: str,
    source_event_id: str,
    drafted_player_id: str | None = None,
) -> CanonicalPickResolution:
    return CanonicalPickResolution(
        pick_resolution_id=resolution_id,
        pick_asset_id=pick_asset_id,
        state_type=state_type,
        effective_start_date=date.fromisoformat("2024-01-10" if state_type == "future_pick" else "2024-06-26"),
        effective_end_date=None,
        overall_pick_number=45 if state_type == "resolved_pick" else None,
        lottery_context=None,
        drafted_player_id=drafted_player_id,
        source_event_id=source_event_id,
        state_payload={"state_type": state_type},
        created_at=NOW,
        updated_at=NOW,
    )


def test_build_event_asset_flows_is_deterministic_and_captures_common_semantics():
    events = [
        _event("event_trade_pick", "trade", "2024-01-10", 1, "Memphis acquires future pick from Utah"),
        _event("event_sign", "signing", "2024-02-01", 1, "Memphis signs John Doe"),
        _event("event_waive", "waiver", "2024-03-01", 1, "Memphis waives John Doe"),
        _event("event_draft", "draft", "2024-06-26", 1, "Memphis drafts GG Jackson"),
    ]
    event_provenance = [
        _event_prov("event_trade_pick", "claim_trade_pick"),
        _event_prov("event_sign", "claim_sign"),
        _event_prov("event_waive", "claim_waive"),
        _event_prov("event_draft", "claim_draft"),
    ]
    assets = [
        _asset("asset_player_john", "player_tenure", "tenure_john", None, "John Doe Memphis tenure"),
        _asset("asset_pick_45", "pick_continuity", None, "pick_45", "Utah 2024 round 1 pick"),
    ]
    player_tenures = [
        _player_tenure("tenure_john", "player_john", "event_sign", "event_waive", "signing"),
    ]
    pick_resolutions = [
        _pick_resolution("pick_future", "pick_45", "future_pick", "event_trade_pick"),
        _pick_resolution("pick_drafted", "pick_45", "drafted_player", "event_draft", drafted_player_id="player_gg_jackson"),
    ]

    first = build_event_asset_flows(events, event_provenance, assets, player_tenures, pick_resolutions, built_at=NOW)
    second = build_event_asset_flows(events, event_provenance, assets, player_tenures, pick_resolutions, built_at=NOW)

    assert [flow.event_asset_flow_id for flow in first.flows] == [flow.event_asset_flow_id for flow in second.flows]
    assert first.flows == second.flows

    flow_by_role = {flow.flow_role: flow for flow in first.flows}
    assert flow_by_role["incoming_player"].flow_direction == "out"
    assert flow_by_role["outgoing_player"].flow_direction == "in"
    assert flow_by_role["incoming_pick"].flow_direction == "out"
    assert flow_by_role["pick_consumed"].flow_direction == "in"
    assert flow_by_role["player_emerges"].flow_direction == "out"

    provenance_roles = {row.provenance_role for row in first.provenance_rows}
    assert "incoming_player_support" in provenance_roles
    assert "outgoing_player_support" in provenance_roles
    assert "incoming_pick_support" in provenance_roles
    assert "pick_consumed_support" in provenance_roles
    assert "player_emerges_support" in provenance_roles

    report = validate_canonical_event_asset_flows(
        events=events,
        assets=assets,
        flows=first.flows,
        provenance_rows=first.provenance_rows,
    )
    assert report.ok


def test_build_event_asset_flows_does_not_emit_incoming_pick_for_draft_future_state():
    events = [_event("event_draft", "draft", "2024-06-26", 1, "Draft")]
    event_provenance = [_event_prov("event_draft", "claim_draft")]
    assets = [_asset("asset_pick_45", "pick_continuity", None, "pick_45", "Memphis 2024 round 2 pick")]
    pick_resolutions = [
        _pick_resolution("pick_future", "pick_45", "future_pick", "event_draft"),
        _pick_resolution("pick_drafted", "pick_45", "drafted_player", "event_draft", drafted_player_id="player_gg_jackson"),
    ]

    result = build_event_asset_flows(events, event_provenance, assets, [], pick_resolutions, built_at=NOW)

    assert sorted(flow.flow_role for flow in result.flows) == ["pick_consumed", "player_emerges"]
    report = validate_canonical_event_asset_flows(
        events=events,
        assets=assets,
        flows=result.flows,
        provenance_rows=result.provenance_rows,
    )
    assert report.ok


def test_build_event_asset_flows_supports_multi_asset_trade():
    events = [
        _event("event_sign_a", "signing", "2024-01-01", 1, "Memphis signs outgoing player A"),
        _event("event_sign_b", "signing", "2024-01-02", 1, "Memphis signs outgoing player B"),
        _event("event_trade", "trade", "2024-02-15", 1, "Memphis trades two players for one player"),
    ]
    event_provenance = [_event_prov(event.event_id, f"claim_{event.event_id}") for event in events]
    assets = [
        _asset("asset_out_a", "player_tenure", "tenure_out_a", None, "Outgoing Player A"),
        _asset("asset_out_b", "player_tenure", "tenure_out_b", None, "Outgoing Player B"),
        _asset("asset_in_c", "player_tenure", "tenure_in_c", None, "Incoming Player C"),
    ]
    player_tenures = [
        _player_tenure("tenure_out_a", "player_out_a", "event_sign_a", "event_trade", "signing"),
        _player_tenure("tenure_out_b", "player_out_b", "event_sign_b", "event_trade", "signing"),
        _player_tenure("tenure_in_c", "player_in_c", "event_trade", None, "trade_acquisition"),
    ]

    result = build_event_asset_flows(events, event_provenance, assets, player_tenures, [], built_at=NOW)

    trade_flows = [row for row in result.flows if row.event_id == "event_trade"]
    assert len(trade_flows) == 3
    assert sorted(row.flow_direction for row in trade_flows) == ["in", "in", "out"]
    assert sorted(row.flow_role for row in trade_flows) == ["incoming_player", "outgoing_player", "outgoing_player"]

    report = validate_canonical_event_asset_flows(
        events=events,
        assets=assets,
        flows=result.flows,
        provenance_rows=result.provenance_rows,
    )
    assert report.ok


def test_build_event_asset_flows_supports_pick_conveyance():
    events = [_event("event_trade_pick", "trade", "2024-06-26", 1, "Memphis trades draft-night pick to Orlando")]
    event_provenance = [_event_prov("event_trade_pick", "claim_trade_pick")]
    assets = [_asset("asset_pick_1", "pick_continuity", None, "pick_1", "2024 round 1 pick")]
    pick_resolutions = [_pick_resolution("pick_conveyed", "pick_1", "conveyed_away", "event_trade_pick")]

    result = build_event_asset_flows(events, event_provenance, assets, [], pick_resolutions, built_at=NOW)

    assert len(result.flows) == 1
    assert result.flows[0].flow_direction == "in"
    assert result.flows[0].flow_role == "outgoing_pick"

    report = validate_canonical_event_asset_flows(
        events=events,
        assets=assets,
        flows=result.flows,
        provenance_rows=result.provenance_rows,
    )
    assert report.ok


def test_validate_event_asset_flows_flags_illegal_bidirectional_non_draft_flow():
    event = _event("event_trade", "trade", "2024-02-15", 1, "Memphis trade")
    asset = _asset("asset_player", "player_tenure", "tenure_player", None, "Player")
    flows = [
        CanonicalEventAssetFlow(
            event_asset_flow_id="flow_in",
            event_id=event.event_id,
            asset_id=asset.asset_id,
            flow_direction="in",
            flow_role="outgoing_player",
            flow_order=1,
            effective_date=event.event_date,
            created_at=NOW,
        ),
        CanonicalEventAssetFlow(
            event_asset_flow_id="flow_out",
            event_id=event.event_id,
            asset_id=asset.asset_id,
            flow_direction="out",
            flow_role="incoming_player",
            flow_order=2,
            effective_date=event.event_date,
            created_at=NOW,
        ),
    ]
    provenance = [
        EventAssetFlowProvenance(
            event_asset_flow_provenance_id="prov_in",
            event_asset_flow_id="flow_in",
            source_record_id="source_trade",
            claim_id="claim_trade",
            override_id=None,
            provenance_role="outgoing_player_support",
            fallback_reason=None,
            created_at=NOW,
        ),
        EventAssetFlowProvenance(
            event_asset_flow_provenance_id="prov_out",
            event_asset_flow_id="flow_out",
            source_record_id="source_trade",
            claim_id="claim_trade",
            override_id=None,
            provenance_role="incoming_player_support",
            fallback_reason=None,
            created_at=NOW,
        ),
    ]

    report = validate_canonical_event_asset_flows(
        events=[event],
        assets=[asset],
        flows=flows,
        provenance_rows=provenance,
    )
    assert not report.ok
    assert any("asset appears to both enter and exit" in error for error in report.errors)


def test_validate_event_asset_flows_warns_on_memphis_trade_with_no_modeled_assets():
    event = _event("event_trade", "trade", "2024-02-15", 1, "Traded to Memphis (MEM) from Charlotte (CHA) for cash")

    report = validate_canonical_event_asset_flows(
        events=[event],
        assets=[],
        flows=[],
        provenance_rows=[],
    )
    assert report.ok
    assert any("no modeled asset flow rows" in warning for warning in report.warnings)


def test_validate_event_asset_flows_allows_draft_event_with_player_tenure_only():
    event = _event("event_draft", "draft", "2024-06-26", 1, "Drafted by Memphis")
    asset = _asset("asset_player", "player_tenure", "tenure_player", None, "Drafted Player Memphis tenure")
    flow = CanonicalEventAssetFlow(
        event_asset_flow_id="flow_player",
        event_id=event.event_id,
        asset_id=asset.asset_id,
        flow_direction="out",
        flow_role="incoming_player",
        flow_order=1,
        effective_date=event.event_date,
        created_at=NOW,
    )
    provenance = [
        EventAssetFlowProvenance(
            event_asset_flow_provenance_id="prov_player",
            event_asset_flow_id=flow.event_asset_flow_id,
            source_record_id="source_draft",
            claim_id="claim_draft",
            override_id=None,
            provenance_role="incoming_player_support",
            fallback_reason=None,
            created_at=NOW,
        )
    ]

    report = validate_canonical_event_asset_flows(
        events=[event],
        assets=[asset],
        flows=[flow],
        provenance_rows=provenance,
    )
    assert report.ok
