from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from canonical.models import (
    AssetState,
    CanonicalAsset,
    CanonicalEvent,
    CanonicalEventAssetFlow,
    CanonicalPickAsset,
    CanonicalPickResolution,
    CanonicalPlayerIdentity,
    CanonicalPlayerTenure,
)
from db_config import load_database_url
from presentation.models import (
    AssetLane,
    PresentationBuild,
    PresentationContractBuildResult,
    TimelineEdge,
    TimelineNode,
)
from shared.ids import stable_id, stable_payload_hash


PICK_STAGE_ORDER = {
    "future_pick": 0,
    "resolved_pick": 1,
    "drafted_player": 2,
    "conveyed_away": 3,
}

OPEN_END_EVENT_ORDER = 999_999
BOUNDARY_EVENT_ORDER = 999_998
LANE_GROUPS = {"main_roster", "two_way", "future_picks"}
TWO_WAY_VALUES = {"two_way", "two-way", "two way"}
MAIN_ROSTER_VALUES = {"main_roster", "main-roster", "main roster", "standard", "regular_roster", "active_roster"}
EXPLICIT_LANE_KEYS = ("lane_group", "presentation_lane_group", "roster_lane_group")
EXPLICIT_STATUS_KEYS = ("contract_type", "roster_status")


def bootstrap_presentation_contract_schema(sql_path: Path | str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required to bootstrap presentation contract tables.") from exc

    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with psycopg.connect(load_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
        conn.commit()


def _connect():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for presentation contract builds.") from exc
    return psycopg.connect(load_database_url())


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _json_ready(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=_json_default))


def _event_node(event: CanonicalEvent, *, built_at: datetime) -> TimelineNode:
    return TimelineNode(
        node_id=stable_id("timeline_node", "event", event.event_id),
        event_id=event.event_id,
        event_date=event.event_date,
        event_order=event.event_order,
        node_type="event",
        label=event.event_label,
        payload={
            "event_type": event.event_type,
            "description": event.description,
            "transaction_group_key": event.transaction_group_key,
            "is_compound": event.is_compound,
            "notes": event.notes,
        },
        created_at=built_at,
    )


def _boundary_node(
    *,
    boundary_key: str,
    boundary_date: date,
    label: str,
    payload: dict[str, Any],
    built_at: datetime,
    event_order: int = BOUNDARY_EVENT_ORDER,
) -> TimelineNode:
    return TimelineNode(
        node_id=stable_id("timeline_node", "boundary", boundary_key, boundary_date.isoformat()),
        event_id=None,
        event_date=boundary_date,
        event_order=event_order,
        node_type="state_boundary",
        label=label,
        payload=payload,
        created_at=built_at,
    )


def _node_sort_key(node: TimelineNode) -> tuple[date, int, str, str]:
    return (node.event_date, node.event_order, node.event_id or "", node.node_id)


def _max_contract_date(events: list[CanonicalEvent], player_tenures: list[CanonicalPlayerTenure], pick_resolutions: list[CanonicalPickResolution], built_at: datetime) -> date:
    candidates = [built_at.date()]
    candidates.extend(event.event_date for event in events)
    candidates.extend(tenure.tenure_start_date for tenure in player_tenures)
    candidates.extend(tenure.tenure_end_date for tenure in player_tenures if tenure.tenure_end_date is not None)
    candidates.extend(row.effective_start_date for row in pick_resolutions)
    candidates.extend(row.effective_end_date for row in pick_resolutions if row.effective_end_date is not None)
    return max(candidates)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _lane_group_from_payload(payload: dict[str, Any]) -> str | None:
    for key in EXPLICIT_LANE_KEYS:
        value = _normalized_text(payload.get(key))
        if value in LANE_GROUPS:
            return value
    for key in EXPLICIT_STATUS_KEYS:
        value = _normalized_text(payload.get(key))
        if value in TWO_WAY_VALUES:
            return "two_way"
        if value in MAIN_ROSTER_VALUES:
            return "main_roster"
    return None


def _lane_group_from_asset_states(states: Iterable[AssetState]) -> str | None:
    for state in sorted(states, key=lambda row: (row.effective_start_date, row.state_type, row.asset_state_id), reverse=True):
        lane_group = _lane_group_from_payload(state.state_payload)
        if lane_group is not None:
            return lane_group
    return None


def _player_lane_group(states: Iterable[AssetState]) -> str:
    explicit_lane_group = _lane_group_from_asset_states(states)
    if explicit_lane_group in {"main_roster", "two_way"}:
        return explicit_lane_group
    return "main_roster"


def _transition_lane_group(resolution: CanonicalPickResolution, states: Iterable[AssetState]) -> str:
    explicit_lane_group = _lane_group_from_payload(resolution.state_payload)
    if explicit_lane_group in {"main_roster", "two_way"}:
        return explicit_lane_group
    explicit_asset_lane_group = _lane_group_from_asset_states(states)
    if explicit_asset_lane_group in {"main_roster", "two_way"}:
        return explicit_asset_lane_group
    return "main_roster"


def _assign_lanes(edges: list[TimelineEdge], *, built_at: datetime) -> tuple[list[TimelineEdge], list[AssetLane]]:
    grouped: dict[str, list[TimelineEdge]] = defaultdict(list)
    for edge in edges:
        grouped[edge.lane_group].append(edge)

    updated_edges: list[TimelineEdge] = []
    lanes: list[AssetLane] = []
    for lane_group in sorted(grouped):
        occupied_until_by_index: list[date] = []
        for edge in sorted(grouped[lane_group], key=lambda row: (row.start_date, row.end_date, row.payload.get("label", ""), row.asset_id, row.edge_id)):
            lane_index = 0
            while lane_index < len(occupied_until_by_index) and occupied_until_by_index[lane_index] > edge.start_date:
                lane_index += 1
            if lane_index == len(occupied_until_by_index):
                occupied_until_by_index.append(edge.end_date)
            else:
                occupied_until_by_index[lane_index] = edge.end_date

            updated = TimelineEdge(
                edge_id=edge.edge_id,
                asset_id=edge.asset_id,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                start_date=edge.start_date,
                end_date=edge.end_date,
                edge_type=edge.edge_type,
                lane_group=edge.lane_group,
                lane_index=lane_index,
                payload=edge.payload,
                created_at=edge.created_at,
            )
            updated_edges.append(updated)
            lanes.append(
                AssetLane(
                    asset_lane_id=stable_id(
                        "asset_lane",
                        edge.edge_id,
                        edge.asset_id,
                        edge.lane_group,
                        lane_index,
                        edge.start_date.isoformat(),
                        edge.end_date.isoformat(),
                    ),
                    asset_id=edge.asset_id,
                    lane_group=edge.lane_group,
                    lane_index=lane_index,
                    effective_start_date=edge.start_date,
                    effective_end_date=edge.end_date,
                    assignment_method="deterministic_first_available_interval_v1",
                    created_at=built_at,
                )
            )

    return (
        sorted(updated_edges, key=lambda row: (row.start_date, row.end_date, row.lane_group, row.lane_index, row.asset_id, row.edge_id)),
        sorted(lanes, key=lambda row: (row.lane_group, row.lane_index, row.effective_start_date, row.asset_id, row.asset_lane_id)),
    )


def build_presentation_contract(
    *,
    events: Iterable[CanonicalEvent],
    assets: Iterable[CanonicalAsset],
    player_identities: Iterable[CanonicalPlayerIdentity],
    player_tenures: Iterable[CanonicalPlayerTenure],
    pick_assets: Iterable[CanonicalPickAsset],
    pick_resolutions: Iterable[CanonicalPickResolution],
    asset_states: Iterable[AssetState],
    event_asset_flows: Iterable[CanonicalEventAssetFlow] = (),
    builder_version: str = "stage6-presentation-contract-v1",
    canonical_build_id: str | None = None,
    built_at: datetime | None = None,
) -> PresentationContractBuildResult:
    built_at_value = built_at or datetime.utcnow()
    events_list = sorted(list(events), key=lambda row: (row.event_date, row.event_order, row.event_id))
    assets_list = sorted(list(assets), key=lambda row: row.asset_id)
    player_identities_list = sorted(list(player_identities), key=lambda row: row.player_id)
    player_tenures_list = sorted(list(player_tenures), key=lambda row: (row.tenure_start_date, row.player_id, row.player_tenure_id))
    pick_assets_list = sorted(list(pick_assets), key=lambda row: row.pick_asset_id)
    pick_resolutions_list = sorted(list(pick_resolutions), key=lambda row: (row.pick_asset_id, row.effective_start_date, PICK_STAGE_ORDER.get(row.state_type, 99), row.pick_resolution_id))
    asset_states_list = sorted(list(asset_states), key=lambda row: (row.asset_id, row.effective_start_date, row.state_type, row.asset_state_id))
    event_asset_flows_list = sorted(list(event_asset_flows), key=lambda row: (row.event_id, row.flow_order, row.event_asset_flow_id))

    event_node_by_id = {event.event_id: _event_node(event, built_at=built_at_value) for event in events_list}
    nodes_by_id = {node.node_id: node for node in event_node_by_id.values()}
    asset_by_player_tenure = {asset.player_tenure_id: asset for asset in assets_list if asset.player_tenure_id}
    asset_by_pick = {asset.pick_asset_id: asset for asset in assets_list if asset.pick_asset_id}
    identity_by_id = {row.player_id: row for row in player_identities_list}
    pick_asset_by_id = {row.pick_asset_id: row for row in pick_assets_list}
    states_by_asset: dict[str, list[AssetState]] = defaultdict(list)
    for state in asset_states_list:
        states_by_asset[state.asset_id].append(state)

    max_contract_date = _max_contract_date(events_list, player_tenures_list, pick_resolutions_list, built_at_value)
    provisional_edges: list[TimelineEdge] = []

    for tenure in player_tenures_list:
        asset = asset_by_player_tenure.get(tenure.player_tenure_id)
        entry_node = event_node_by_id.get(tenure.entry_event_id)
        if asset is None or entry_node is None:
            continue
        end_date = tenure.tenure_end_date or max_contract_date
        if tenure.exit_event_id and tenure.exit_event_id in event_node_by_id:
            target_node = event_node_by_id[tenure.exit_event_id]
        else:
            target_node = _boundary_node(
                boundary_key=f"player_tenure_end:{tenure.player_tenure_id}",
                boundary_date=end_date,
                label=f"{asset.asset_label} open roster boundary",
                payload={"asset_id": asset.asset_id, "player_tenure_id": tenure.player_tenure_id, "boundary_type": "open_tenure_end"},
                built_at=built_at_value,
                event_order=OPEN_END_EVENT_ORDER,
            )
            nodes_by_id[target_node.node_id] = target_node

        identity = identity_by_id.get(tenure.player_id)
        lane_group = _player_lane_group(states_by_asset.get(asset.asset_id, []))
        provisional_edges.append(
            TimelineEdge(
                edge_id=stable_id("timeline_edge", asset.asset_id, "player_line", tenure.entry_event_id, tenure.exit_event_id or "open", tenure.tenure_start_date.isoformat(), end_date.isoformat()),
                asset_id=asset.asset_id,
                source_node_id=entry_node.node_id,
                target_node_id=target_node.node_id,
                start_date=tenure.tenure_start_date,
                end_date=end_date,
                edge_type="player_line",
                lane_group=lane_group,
                lane_index=0,
                payload={
                    "label": asset.asset_label,
                    "asset_kind": asset.asset_kind,
                    "player_tenure_id": tenure.player_tenure_id,
                    "player_id": tenure.player_id,
                    "player_name": identity.display_name if identity else None,
                    "tenure_type": tenure.tenure_type,
                    "roster_path_type": tenure.roster_path_type,
                    "entry_event_id": tenure.entry_event_id,
                    "exit_event_id": tenure.exit_event_id,
                },
                created_at=built_at_value,
            )
        )

    resolutions_by_pick: dict[str, list[CanonicalPickResolution]] = defaultdict(list)
    for resolution in pick_resolutions_list:
        resolutions_by_pick[resolution.pick_asset_id].append(resolution)

    for pick_asset_id, resolutions in sorted(resolutions_by_pick.items()):
        asset = asset_by_pick.get(pick_asset_id)
        pick_asset = pick_asset_by_id.get(pick_asset_id)
        if asset is None:
            continue
        for index, resolution in enumerate(resolutions):
            if resolution.state_type == "conveyed_away":
                continue
            next_resolution = resolutions[index + 1] if index + 1 < len(resolutions) else None
            start_date = resolution.effective_start_date
            end_date = resolution.effective_end_date or (next_resolution.effective_start_date if next_resolution else max_contract_date)
            source_node = event_node_by_id.get(resolution.source_event_id or "")
            if source_node is None:
                source_node = _boundary_node(
                    boundary_key=f"pick_stage_start:{resolution.pick_resolution_id}",
                    boundary_date=start_date,
                    label=f"{asset.asset_label} {resolution.state_type} start",
                    payload={"asset_id": asset.asset_id, "pick_asset_id": pick_asset_id, "pick_resolution_id": resolution.pick_resolution_id, "boundary_type": "pick_stage_start"},
                    built_at=built_at_value,
                )
                nodes_by_id[source_node.node_id] = source_node
            target_node = None
            if next_resolution and next_resolution.source_event_id:
                target_node = event_node_by_id.get(next_resolution.source_event_id)
            if target_node is None:
                target_node = _boundary_node(
                    boundary_key=f"pick_stage_end:{resolution.pick_resolution_id}",
                    boundary_date=end_date,
                    label=f"{asset.asset_label} {resolution.state_type} end",
                    payload={"asset_id": asset.asset_id, "pick_asset_id": pick_asset_id, "pick_resolution_id": resolution.pick_resolution_id, "boundary_type": "pick_stage_end"},
                    built_at=built_at_value,
                    event_order=OPEN_END_EVENT_ORDER if next_resolution is None else BOUNDARY_EVENT_ORDER,
                )
                nodes_by_id[target_node.node_id] = target_node

            edge_type = "transition_line" if resolution.state_type == "drafted_player" else "pick_line"
            lane_group = _transition_lane_group(resolution, states_by_asset.get(asset.asset_id, [])) if resolution.state_type == "drafted_player" else "future_picks"
            player_identity = identity_by_id.get(resolution.drafted_player_id or "")
            provisional_edges.append(
                TimelineEdge(
                    edge_id=stable_id("timeline_edge", asset.asset_id, edge_type, resolution.pick_resolution_id, start_date.isoformat(), end_date.isoformat()),
                    asset_id=asset.asset_id,
                    source_node_id=source_node.node_id,
                    target_node_id=target_node.node_id,
                    start_date=start_date,
                    end_date=end_date,
                    edge_type=edge_type,
                    lane_group=lane_group,
                    lane_index=0,
                    payload={
                        "label": asset.asset_label,
                        "asset_kind": asset.asset_kind,
                        "pick_asset_id": pick_asset_id,
                        "pick_resolution_id": resolution.pick_resolution_id,
                        "pick_stage": resolution.state_type,
                        "draft_year": pick_asset.draft_year if pick_asset else None,
                        "draft_round": pick_asset.draft_round if pick_asset else None,
                        "origin_team_code": pick_asset.origin_team_code if pick_asset else None,
                        "overall_pick_number": resolution.overall_pick_number,
                        "lottery_context": resolution.lottery_context,
                        "drafted_player_id": resolution.drafted_player_id,
                        "drafted_player_name": player_identity.display_name if player_identity else None,
                        "source_event_id": resolution.source_event_id,
                        "state_payload": resolution.state_payload,
                    },
                    created_at=built_at_value,
                )
            )

    edges, lanes = _assign_lanes(provisional_edges, built_at=built_at_value)
    nodes = sorted(nodes_by_id.values(), key=_node_sort_key)
    input_hash = stable_payload_hash(
        {
            "event_ids": [event.event_id for event in events_list],
            "asset_ids": [asset.asset_id for asset in assets_list],
            "player_tenure_ids": [row.player_tenure_id for row in player_tenures_list],
            "pick_asset_ids": [row.pick_asset_id for row in pick_assets_list],
            "pick_resolution_ids": [row.pick_resolution_id for row in pick_resolutions_list],
            "asset_state_ids": [row.asset_state_id for row in asset_states_list],
            "event_asset_flow_ids": [row.event_asset_flow_id for row in event_asset_flows_list],
        }
    )
    build = PresentationBuild(
        presentation_build_id=stable_id("presentation_build", builder_version, built_at_value.isoformat(), canonical_build_id or input_hash),
        built_at=built_at_value,
        builder_version=builder_version,
        canonical_build_id=canonical_build_id,
        notes="Stage 6 presentation contract build",
    )
    return PresentationContractBuildResult(build=build, nodes=nodes, edges=edges, lanes=lanes)


def presentation_contract_to_json(result: PresentationContractBuildResult, *, editorial_overlays: Any | None = None) -> str:
    payload = _json_ready(result.as_contract())
    if editorial_overlays is not None:
        payload["editorial"] = _json_ready(editorial_overlays.as_contract())
    return json.dumps(payload, sort_keys=True, indent=2)


def fetch_presentation_contract_build_inputs(
    conn: Any,
) -> tuple[
    list[CanonicalEvent],
    list[CanonicalAsset],
    list[CanonicalPlayerIdentity],
    list[CanonicalPlayerTenure],
    list[CanonicalPickAsset],
    list[CanonicalPickResolution],
    list[AssetState],
    list[CanonicalEventAssetFlow],
    str | None,
]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select
                event_id,
                event_type,
                event_date,
                event_order,
                event_label,
                description,
                transaction_group_key,
                is_compound,
                notes,
                created_at,
                updated_at
            from canonical.events
            order by event_date, event_order, event_id
            """
        )
        event_rows = cur.fetchall()
        cur.execute(
            """
            select
                asset_id,
                asset_kind,
                player_tenure_id,
                pick_asset_id,
                asset_label,
                created_at,
                updated_at
            from canonical.asset
            order by asset_id
            """
        )
        asset_rows = cur.fetchall()
        cur.execute(
            """
            select
                player_id,
                display_name,
                normalized_name,
                nba_person_id,
                created_at,
                updated_at
            from canonical.player_identity
            order by player_id
            """
        )
        player_identity_rows = cur.fetchall()
        cur.execute(
            """
            select
                player_tenure_id,
                player_id,
                tenure_start_date,
                tenure_end_date,
                entry_event_id,
                exit_event_id,
                tenure_type,
                roster_path_type,
                created_at,
                updated_at
            from canonical.player_tenure
            order by player_id, tenure_start_date, player_tenure_id
            """
        )
        player_tenure_rows = cur.fetchall()
        cur.execute(
            """
            select
                pick_asset_id,
                origin_team_code,
                draft_year,
                draft_round,
                protection_summary,
                protection_payload,
                drafted_player_id,
                current_pick_stage,
                created_at,
                updated_at
            from canonical.pick_asset
            order by pick_asset_id
            """
        )
        pick_asset_rows = cur.fetchall()
        cur.execute(
            """
            select
                pick_resolution_id,
                pick_asset_id,
                state_type,
                effective_start_date,
                effective_end_date,
                overall_pick_number,
                lottery_context,
                drafted_player_id,
                source_event_id,
                state_payload,
                created_at,
                updated_at
            from canonical.pick_resolution
            order by pick_asset_id, effective_start_date, pick_resolution_id
            """
        )
        pick_resolution_rows = cur.fetchall()
        cur.execute(
            """
            select
                asset_state_id,
                asset_id,
                state_type,
                effective_start_date,
                effective_end_date,
                state_payload,
                source_event_id,
                created_at,
                updated_at
            from canonical.asset_state
            order by asset_id, effective_start_date, asset_state_id
            """
        )
        asset_state_rows = cur.fetchall()
        cur.execute(
            """
            select
                event_asset_flow_id,
                event_id,
                asset_id,
                flow_direction,
                flow_role,
                flow_order,
                effective_date,
                created_at
            from canonical.event_asset_flow
            order by event_id, flow_order, event_asset_flow_id
            """
        )
        flow_rows = cur.fetchall()
        cur.execute(
            """
            select canonical_build_id
            from canonical.builds
            order by built_at desc, canonical_build_id desc
            limit 1
            """
        )
        build_row = cur.fetchone()

    events = [
        CanonicalEvent(
            event_id=row[0],
            event_type=row[1],
            event_date=row[2],
            event_order=row[3],
            event_label=row[4],
            description=row[5],
            transaction_group_key=row[6],
            is_compound=row[7],
            notes=row[8],
            created_at=row[9],
            updated_at=row[10],
        )
        for row in event_rows
    ]
    assets = [
        CanonicalAsset(
            asset_id=row[0],
            asset_kind=row[1],
            player_tenure_id=row[2],
            pick_asset_id=row[3],
            asset_label=row[4],
            created_at=row[5],
            updated_at=row[6],
        )
        for row in asset_rows
    ]
    player_identities = [
        CanonicalPlayerIdentity(
            player_id=row[0],
            display_name=row[1],
            normalized_name=row[2],
            nba_person_id=row[3],
            created_at=row[4],
            updated_at=row[5],
        )
        for row in player_identity_rows
    ]
    player_tenures = [
        CanonicalPlayerTenure(
            player_tenure_id=row[0],
            player_id=row[1],
            tenure_start_date=row[2],
            tenure_end_date=row[3],
            entry_event_id=row[4],
            exit_event_id=row[5],
            tenure_type=row[6],
            roster_path_type=row[7],
            created_at=row[8],
            updated_at=row[9],
        )
        for row in player_tenure_rows
    ]
    pick_assets = [
        CanonicalPickAsset(
            pick_asset_id=row[0],
            origin_team_code=row[1],
            draft_year=row[2],
            draft_round=row[3],
            protection_summary=row[4],
            protection_payload=row[5],
            drafted_player_id=row[6],
            current_pick_stage=row[7],
            created_at=row[8],
            updated_at=row[9],
        )
        for row in pick_asset_rows
    ]
    pick_resolutions = [
        CanonicalPickResolution(
            pick_resolution_id=row[0],
            pick_asset_id=row[1],
            state_type=row[2],
            effective_start_date=row[3],
            effective_end_date=row[4],
            overall_pick_number=row[5],
            lottery_context=row[6],
            drafted_player_id=row[7],
            source_event_id=row[8],
            state_payload=row[9],
            created_at=row[10],
            updated_at=row[11],
        )
        for row in pick_resolution_rows
    ]
    asset_states = [
        AssetState(
            asset_state_id=row[0],
            asset_id=row[1],
            state_type=row[2],
            effective_start_date=row[3],
            effective_end_date=row[4],
            state_payload=row[5],
            source_event_id=row[6],
            created_at=row[7],
            updated_at=row[8],
        )
        for row in asset_state_rows
    ]
    event_asset_flows = [
        CanonicalEventAssetFlow(
            event_asset_flow_id=row[0],
            event_id=row[1],
            asset_id=row[2],
            flow_direction=row[3],
            flow_role=row[4],
            flow_order=row[5],
            effective_date=row[6],
            created_at=row[7],
        )
        for row in flow_rows
    ]
    return (
        events,
        assets,
        player_identities,
        player_tenures,
        pick_assets,
        pick_resolutions,
        asset_states,
        event_asset_flows,
        build_row[0] if build_row else None,
    )


def persist_presentation_contract_build(conn: Any, result: PresentationContractBuildResult) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("delete from presentation.timeline_edges")
        cur.execute("delete from presentation.asset_lanes")
        cur.execute("delete from presentation.timeline_nodes")
        cur.execute(
            """
            insert into presentation.builds (
                presentation_build_id,
                built_at,
                builder_version,
                canonical_build_id,
                notes
            )
            values (%s, %s, %s, %s, %s)
            """,
            (
                result.build.presentation_build_id,
                result.build.built_at,
                result.build.builder_version,
                result.build.canonical_build_id,
                result.build.notes,
            ),
        )
        for row in result.nodes:
            cur.execute(
                """
                insert into presentation.timeline_nodes (
                    node_id,
                    event_id,
                    event_date,
                    event_order,
                    node_type,
                    label,
                    payload,
                    created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    row.node_id,
                    row.event_id,
                    row.event_date,
                    row.event_order,
                    row.node_type,
                    row.label,
                    json.dumps(_json_ready(row.payload), sort_keys=True),
                    row.created_at,
                ),
            )
        for row in result.lanes:
            cur.execute(
                """
                insert into presentation.asset_lanes (
                    asset_lane_id,
                    asset_id,
                    lane_group,
                    lane_index,
                    effective_start_date,
                    effective_end_date,
                    assignment_method,
                    created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row.asset_lane_id,
                    row.asset_id,
                    row.lane_group,
                    row.lane_index,
                    row.effective_start_date,
                    row.effective_end_date,
                    row.assignment_method,
                    row.created_at,
                ),
            )
        for row in result.edges:
            cur.execute(
                """
                insert into presentation.timeline_edges (
                    edge_id,
                    asset_id,
                    source_node_id,
                    target_node_id,
                    start_date,
                    end_date,
                    edge_type,
                    lane_group,
                    lane_index,
                    payload,
                    created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    row.edge_id,
                    row.asset_id,
                    row.source_node_id,
                    row.target_node_id,
                    row.start_date,
                    row.end_date,
                    row.edge_type,
                    row.lane_group,
                    row.lane_index,
                    json.dumps(_json_ready(row.payload), sort_keys=True),
                    row.created_at,
                ),
            )
    return result.counts()


def build_and_persist_presentation_contract(*, builder_version: str = "stage6-presentation-contract-v1") -> dict[str, int]:
    with _connect() as conn:
        (
            events,
            assets,
            player_identities,
            player_tenures,
            pick_assets,
            pick_resolutions,
            asset_states,
            event_asset_flows,
            canonical_build_id,
        ) = fetch_presentation_contract_build_inputs(conn)
        result = build_presentation_contract(
            events=events,
            assets=assets,
            player_identities=player_identities,
            player_tenures=player_tenures,
            pick_assets=pick_assets,
            pick_resolutions=pick_resolutions,
            asset_states=asset_states,
            event_asset_flows=event_asset_flows,
            builder_version=builder_version,
            canonical_build_id=canonical_build_id,
        )
        counts = persist_presentation_contract_build(conn, result)
        conn.commit()
    return counts


def fetch_presentation_contract(conn: Any) -> PresentationContractBuildResult:
    with conn.cursor() as cur:
        cur.execute(
            """
            select
                presentation_build_id,
                built_at,
                builder_version,
                canonical_build_id,
                notes
            from presentation.builds
            order by built_at desc, presentation_build_id desc
            limit 1
            """
        )
        build_row = cur.fetchone()
        if build_row is None:
            raise RuntimeError("no presentation build found")
        cur.execute(
            """
            select
                node_id,
                event_id,
                event_date,
                event_order,
                node_type,
                label,
                payload,
                created_at
            from presentation.timeline_nodes
            order by event_date, event_order, coalesce(event_id, ''), node_id
            """
        )
        node_rows = cur.fetchall()
        cur.execute(
            """
            select
                edge_id,
                asset_id,
                source_node_id,
                target_node_id,
                start_date,
                end_date,
                edge_type,
                lane_group,
                lane_index,
                payload,
                created_at
            from presentation.timeline_edges
            order by start_date, end_date, lane_group, lane_index, asset_id, edge_id
            """
        )
        edge_rows = cur.fetchall()
        cur.execute(
            """
            select
                asset_lane_id,
                asset_id,
                lane_group,
                lane_index,
                effective_start_date,
                effective_end_date,
                assignment_method,
                created_at
            from presentation.asset_lanes
            order by lane_group, lane_index, effective_start_date, asset_id, asset_lane_id
            """
        )
        lane_rows = cur.fetchall()

    build = PresentationBuild(
        presentation_build_id=build_row[0],
        built_at=build_row[1],
        builder_version=build_row[2],
        canonical_build_id=build_row[3],
        notes=build_row[4],
    )
    nodes = [
        TimelineNode(
            node_id=row[0],
            event_id=row[1],
            event_date=row[2],
            event_order=row[3],
            node_type=row[4],
            label=row[5],
            payload=row[6],
            created_at=row[7],
        )
        for row in node_rows
    ]
    edges = [
        TimelineEdge(
            edge_id=row[0],
            asset_id=row[1],
            source_node_id=row[2],
            target_node_id=row[3],
            start_date=row[4],
            end_date=row[5],
            edge_type=row[6],
            lane_group=row[7],
            lane_index=row[8],
            payload=row[9],
            created_at=row[10],
        )
        for row in edge_rows
    ]
    lanes = [
        AssetLane(
            asset_lane_id=row[0],
            asset_id=row[1],
            lane_group=row[2],
            lane_index=row[3],
            effective_start_date=row[4],
            effective_end_date=row[5],
            assignment_method=row[6],
            created_at=row[7],
        )
        for row in lane_rows
    ]
    return PresentationContractBuildResult(build=build, nodes=nodes, edges=edges, lanes=lanes)


def export_presentation_contract_json(
    output_path: Path | str | None = None,
    *,
    include_editorial: bool = False,
) -> str:
    with _connect() as conn:
        result = fetch_presentation_contract(conn)
        editorial_result = None
        if include_editorial:
            from editorial.contract import fetch_editorial_overlays

            editorial_result = fetch_editorial_overlays(conn)
    payload = presentation_contract_to_json(result, editorial_overlays=editorial_result)
    if output_path is not None:
        Path(output_path).write_text(payload + "\n", encoding="utf-8")
    return payload
