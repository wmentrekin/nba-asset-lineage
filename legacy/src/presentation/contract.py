from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import yaml

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
from editorial.models import EditorialOverlayBuildResult
from presentation.models import (
    AssetLane,
    ChapterLayoutRow,
    EventLayoutRow,
    IdentityMarker,
    LabelLayoutRow,
    LaneLayoutRow,
    LayoutBuild,
    LayoutContractBuildResult,
    LayoutMeta,
    MinimapSegment,
    PresentationBuild,
    PresentationContractBuildResult,
    TimelineEdge,
    TimelineNode,
    TransitionAnchor,
    TransitionLink,
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
DEFAULT_LAYOUT_WINDOW_DAYS = 180
DEFAULT_LAYOUT_MIN_ZOOM_DAYS = 30
DEFAULT_LAYOUT_DAY_WIDTH = 6.0
HEADSHOT_MANIFEST_PATH = Path("configs/data/stage8_headshot_manifest.yaml")
FRONTEND_PUBLIC_ROOT = Path("frontend/public")


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


def _segment_duration_days(start_date: date, end_date: date) -> int:
    return max(1, (end_date - start_date).days + 1)


def _segment_label(edge: TimelineEdge) -> str:
    return str(
        edge.payload.get("player_name")
        or edge.payload.get("drafted_player_name")
        or edge.payload.get("label")
        or edge.asset_id
    )


def _load_headshot_manifest(manifest_path: Path | str) -> dict[str, str]:
    path = Path(manifest_path)
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("headshots"), dict):
        payload = payload["headshots"]
    if not isinstance(payload, dict):
        raise ValueError(f"headshot manifest must be a mapping: {path}")
    manifest: dict[str, str] = {}
    for asset_id, image_path in payload.items():
        asset_key = str(asset_id).strip()
        image_value = str(image_path or "").strip()
        if asset_key and image_value:
            manifest[asset_key] = image_value
    return manifest


def _resolved_identity_marker(
    *,
    asset_id: str,
    label_text: str,
    manifest: dict[str, str],
    frontend_public_root: Path,
) -> IdentityMarker:
    image_path = manifest.get(asset_id)
    if image_path and not (frontend_public_root / image_path).exists():
        image_path = None
    return IdentityMarker(
        label_text=label_text,
        image_path=image_path,
        marker_variant="headshot_text" if image_path else "text_only",
    )


def _minimap_label(start_date: date, end_date: date) -> str:
    if start_date.year == end_date.year and start_date.month == end_date.month:
        return start_date.strftime("%b %Y")
    return f"{start_date.strftime('%b %Y')} - {end_date.strftime('%b %Y')}"


def _build_minimap_segments(*, start_date: date, end_date: date, window_end: date) -> list[MinimapSegment]:
    width_days = max(1, (window_end - start_date).days)
    step_days = max(1, width_days // 2)
    segments: list[MinimapSegment] = []
    cursor = start_date
    while True:
        segment_end = min(cursor + timedelta(days=width_days), end_date)
        anchor_date = min(cursor + timedelta(days=max(0, width_days // 2)), segment_end)
        segments.append(
            MinimapSegment(
                segment_id=stable_id("layout_minimap_segment", cursor.isoformat(), segment_end.isoformat()),
                start_date=cursor,
                end_date=segment_end,
                anchor_date=anchor_date,
                label=_minimap_label(cursor, segment_end),
            )
        )
        if segment_end >= end_date:
            break
        next_cursor = min(cursor + timedelta(days=step_days), end_date)
        if next_cursor <= cursor:
            break
        cursor = next_cursor
    return segments


def _cluster_events(nodes: list[TimelineNode]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    grouped: dict[tuple[str, ...], list[TimelineNode]] = defaultdict(list)
    for node in nodes:
        if node.event_id is None:
            continue
        event_type = str(node.payload.get("event_type") or "")
        transaction_group_key = str(node.payload.get("transaction_group_key") or "").strip()
        if event_type == "trade" and transaction_group_key:
            key = ("trade", node.event_date.isoformat(), transaction_group_key)
        else:
            key = ("event", node.event_id)
        grouped[key].append(node)

    clusters: list[dict[str, Any]] = []
    cluster_by_event_id: dict[str, dict[str, Any]] = {}
    for key, group in grouped.items():
        ordered = sorted(group, key=lambda row: (row.event_date, row.event_order, row.event_id or "", row.node_id))
        cluster_date = ordered[0].event_date
        cluster_order = min(row.event_order for row in ordered)
        if key[0] == "trade":
            cluster_id = stable_id("layout_event_cluster", cluster_date.isoformat(), key[2])
        else:
            cluster_id = stable_id("layout_event_cluster", ordered[0].event_id)
        cluster = {
            "cluster_id": cluster_id,
            "cluster_date": cluster_date,
            "cluster_order": cluster_order,
            "event_id": ordered[0].event_id,
            "member_event_ids": [row.event_id for row in ordered if row.event_id is not None],
            "event_types": [str(row.payload.get("event_type") or "") for row in ordered],
        }
        clusters.append(cluster)
        for row in ordered:
            if row.event_id is not None:
                cluster_by_event_id[row.event_id] = cluster

    clusters.sort(key=lambda row: (row["cluster_date"], row["cluster_order"], row["event_id"]))
    return clusters, cluster_by_event_id


def _build_transition_links(
    *,
    cluster: dict[str, Any],
    incoming_rows: list[LaneLayoutRow],
    outgoing_rows: list[LaneLayoutRow],
    incoming_edges: dict[str, TimelineEdge],
    outgoing_edges: dict[str, TimelineEdge],
) -> list[TransitionLink]:
    return [
        TransitionLink(
            transition_link_id=stable_id(
                "layout_transition_link",
                cluster["cluster_id"],
                source_segment_id,
                target_segment_id,
                link_type,
            ),
            source_segment_id=source_segment_id,
            target_segment_id=target_segment_id,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            link_type=link_type,
        )
        for source_segment_id, target_segment_id, source_asset_id, target_asset_id, link_type in _expected_transition_link_specs(
            cluster=cluster,
            incoming_rows=incoming_rows,
            outgoing_rows=outgoing_rows,
            incoming_edges=incoming_edges,
            outgoing_edges=outgoing_edges,
        )
    ]


def _expected_transition_link_specs(
    *,
    cluster: dict[str, Any],
    incoming_rows: list[LaneLayoutRow],
    outgoing_rows: list[LaneLayoutRow],
    incoming_edges: dict[str, TimelineEdge],
    outgoing_edges: dict[str, TimelineEdge],
) -> list[tuple[str, str, str, str, str]]:
    specs: list[tuple[str, str, str, str, str]] = []
    used_incoming: set[str] = set()
    used_outgoing: set[str] = set()
    edge_by_segment_id = {**incoming_edges, **outgoing_edges}

    if cluster["junction_type"] == "draft_transition":
        stage_order = {"future_pick": 0, "resolved_pick": 1, "drafted_player": 2}
        rows_by_asset: dict[str, dict[str, LaneLayoutRow]] = defaultdict(dict)
        for row in incoming_rows + outgoing_rows:
            rows_by_asset[row.asset_id][row.segment_id] = row
        for asset_id, rows_by_segment_id in sorted(rows_by_asset.items()):
            ordered_rows = sorted(
                rows_by_segment_id.values(),
                key=lambda row: (
                    stage_order.get(str(edge_by_segment_id[row.segment_id].payload.get("pick_stage") or ""), 99),
                    0 if edge_by_segment_id[row.segment_id].edge_type == "pick_line" else 1,
                    row.band_slot,
                    row.segment_id,
                ),
            )
            for source_row, target_row in zip(ordered_rows, ordered_rows[1:]):
                if source_row.segment_id == target_row.segment_id:
                    continue
                target_edge = edge_by_segment_id[target_row.segment_id]
                link_type = "pick_to_player" if target_edge.edge_type == "transition_line" else "same_asset"
                specs.append(
                    (
                        source_row.segment_id,
                        target_row.segment_id,
                        source_row.asset_id,
                        target_row.asset_id,
                        link_type,
                    )
                )
                used_incoming.add(source_row.segment_id)
                used_outgoing.add(target_row.segment_id)

    incoming_by_asset: dict[str, list[LaneLayoutRow]] = defaultdict(list)
    outgoing_by_asset: dict[str, list[LaneLayoutRow]] = defaultdict(list)
    for row in incoming_rows:
        if row.segment_id not in used_incoming:
            incoming_by_asset[row.asset_id].append(row)
    for row in outgoing_rows:
        if row.segment_id not in used_outgoing:
            outgoing_by_asset[row.asset_id].append(row)

    for asset_id in sorted(set(incoming_by_asset) & set(outgoing_by_asset)):
        source_rows = sorted(incoming_by_asset[asset_id], key=lambda row: (row.band_slot, row.segment_id))
        target_rows = sorted(outgoing_by_asset[asset_id], key=lambda row: (row.band_slot, row.segment_id))
        for source_row, target_row in zip(source_rows, target_rows):
            if source_row.segment_id == target_row.segment_id:
                continue
            specs.append(
                (
                    source_row.segment_id,
                    target_row.segment_id,
                    source_row.asset_id,
                    target_row.asset_id,
                    "same_asset",
                )
            )
            used_incoming.add(source_row.segment_id)
            used_outgoing.add(target_row.segment_id)

    return specs


def _chapter_window(value: Any, *, fallback_start: date, fallback_end: date) -> tuple[date, date]:
    if isinstance(value, dict):
        start_text = str(value.get("start_date") or "").strip()
        end_text = str(value.get("end_date") or "").strip()
        if start_text and end_text:
            return date.fromisoformat(start_text), date.fromisoformat(end_text)
    return fallback_start, fallback_end


def _chapter_focus_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]


def _chapter_default_zoom(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        zoom = value
    elif isinstance(value, float) and value.is_integer():
        zoom = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        zoom = int(value.strip())
    else:
        return None
    if zoom < DEFAULT_LAYOUT_MIN_ZOOM_DAYS:
        return None
    return min(zoom, DEFAULT_LAYOUT_WINDOW_DAYS)


def build_layout_contract(
    *,
    presentation_result: PresentationContractBuildResult,
    editorial_overlays: EditorialOverlayBuildResult | None = None,
    builder_version: str = "stage8-layout-contract-v1",
    built_at: datetime | None = None,
    headshot_manifest_path: Path | str = HEADSHOT_MANIFEST_PATH,
    frontend_public_root: Path | str = FRONTEND_PUBLIC_ROOT,
) -> LayoutContractBuildResult:
    if not presentation_result.nodes and not presentation_result.edges:
        raise ValueError("layout contract build requires presentation nodes or edges")

    built_at_value = built_at or datetime.utcnow()
    frontend_public_root_path = Path(frontend_public_root)
    headshot_manifest = _load_headshot_manifest(headshot_manifest_path)

    edges = list(presentation_result.edges)
    nodes = list(presentation_result.nodes)
    event_nodes = [row for row in nodes if row.event_id is not None]
    if not event_nodes:
        raise ValueError("layout contract build requires presentation event nodes")

    chronology_candidates = [row.event_date for row in event_nodes]
    chronology_candidates.extend(row.start_date for row in edges)
    chronology_candidates.extend(row.end_date for row in edges)
    start_date = min(chronology_candidates)
    end_date = max(chronology_candidates)
    default_window_start = start_date
    default_window_end = min(start_date + timedelta(days=DEFAULT_LAYOUT_WINDOW_DAYS), end_date)

    minimap_segments = _build_minimap_segments(
        start_date=start_date,
        end_date=end_date,
        window_end=default_window_end,
    )
    layout_meta = LayoutMeta(
        start_date=start_date,
        end_date=end_date,
        default_window_start=default_window_start,
        default_window_end=default_window_end,
        default_day_width=DEFAULT_LAYOUT_DAY_WIDTH,
        axis_strategy={
            "minor_tick_unit": "month",
            "major_tick_unit": "season_boundary",
            "season_boundary_rule": "july_1",
        },
        minimap_segments=minimap_segments,
    )

    label_by_asset: dict[str, str] = {}
    visible_days_by_asset: dict[str, int] = defaultdict(int)
    for edge in edges:
        label_by_asset.setdefault(edge.asset_id, _segment_label(edge))
        visible_days_by_asset[edge.asset_id] += _segment_duration_days(edge.start_date, edge.end_date)
    display_rank_by_asset = {
        asset_id: index
        for index, asset_id in enumerate(
            sorted(
                visible_days_by_asset,
                key=lambda key: (-visible_days_by_asset[key], label_by_asset.get(key, ""), key),
            )
        )
    }

    provisional_lane_rows = [
        LaneLayoutRow(
            segment_id=edge.edge_id,
            asset_id=edge.asset_id,
            lane_group=edge.lane_group,
            date_start=edge.start_date,
            date_end=edge.end_date,
            display_rank=display_rank_by_asset[edge.asset_id],
            band_slot=edge.lane_index,
            compaction_group=None,
            continuity_anchor=edge.asset_id,
            entry_slot=edge.lane_index,
            exit_slot=edge.lane_index,
            identity_marker=_resolved_identity_marker(
                asset_id=edge.asset_id,
                label_text=_segment_label(edge),
                manifest=headshot_manifest,
                frontend_public_root=frontend_public_root_path,
            ),
        )
        for edge in edges
    ]
    lane_by_segment_id = {row.segment_id: row for row in provisional_lane_rows}
    edge_by_segment_id = {edge.edge_id: edge for edge in edges}

    clusters, cluster_by_event_id = _cluster_events(event_nodes)
    compaction_group_by_segment: dict[str, str] = {}
    continuity_links_by_segment: dict[str, set[str]] = defaultdict(set)
    event_layout: list[EventLayoutRow] = []
    for cluster in clusters:
        member_event_ids = list(cluster["member_event_ids"])
        incoming_rows = sorted(
            [
                row
                for row in provisional_lane_rows
                if edge_by_segment_id[row.segment_id].target_node_id in {
                    node.node_id for node in event_nodes if node.event_id in member_event_ids
                }
            ],
            key=lambda row: (row.band_slot, row.segment_id),
        )
        outgoing_rows = sorted(
            [
                row
                for row in provisional_lane_rows
                if edge_by_segment_id[row.segment_id].source_node_id in {
                    node.node_id for node in event_nodes if node.event_id in member_event_ids
                }
            ],
            key=lambda row: (row.band_slot, row.segment_id),
        )
        incoming_edges = {row.segment_id: edge_by_segment_id[row.segment_id] for row in incoming_rows}
        outgoing_edges = {row.segment_id: edge_by_segment_id[row.segment_id] for row in outgoing_rows}

        cluster["junction_type"] = (
            "draft_transition"
            if "draft" in cluster["event_types"] and any(edge.edge_type == "transition_line" for edge in outgoing_edges.values())
            else "transaction"
        )
        transition_links = _build_transition_links(
            cluster=cluster,
            incoming_rows=incoming_rows,
            outgoing_rows=outgoing_rows,
            incoming_edges=incoming_edges,
            outgoing_edges=outgoing_edges,
        )
        transition_anchor_map: dict[tuple[str, str, int, int], TransitionAnchor] = {}
        for link in transition_links:
            source_row = lane_by_segment_id[link.source_segment_id]
            target_row = lane_by_segment_id[link.target_segment_id]
            for row, from_slot, to_slot in (
                (source_row, source_row.exit_slot, target_row.entry_slot),
                (target_row, source_row.exit_slot, target_row.entry_slot),
            ):
                transition_anchor_map[(row.segment_id, row.asset_id, from_slot, to_slot)] = TransitionAnchor(
                    segment_id=row.segment_id,
                    asset_id=row.asset_id,
                    anchor_date=cluster["cluster_date"],
                    from_slot=from_slot,
                    to_slot=to_slot,
                )
            continuity_links_by_segment[source_row.segment_id].add(target_row.segment_id)
            continuity_links_by_segment[target_row.segment_id].add(source_row.segment_id)
            compaction_group_by_segment.setdefault(source_row.segment_id, cluster["cluster_id"])
            compaction_group_by_segment.setdefault(target_row.segment_id, cluster["cluster_id"])

        event_layout.append(
            EventLayoutRow(
                event_id=cluster["event_id"],
                cluster_id=cluster["cluster_id"],
                cluster_date=cluster["cluster_date"],
                cluster_order=cluster["cluster_order"],
                junction_type=cluster["junction_type"],
                member_event_ids=member_event_ids,
                connected_asset_ids=sorted({row.asset_id for row in incoming_rows + outgoing_rows}),
                incoming_slots={row.segment_id: row.exit_slot for row in incoming_rows},
                outgoing_slots={row.segment_id: row.entry_slot for row in outgoing_rows},
                transition_anchors=sorted(
                    transition_anchor_map.values(),
                    key=lambda row: (row.from_slot, row.to_slot, row.segment_id),
                ),
                transition_links=sorted(
                    transition_links,
                    key=lambda row: (row.link_type, row.source_segment_id, row.target_segment_id),
                ),
            )
        )

    parent = {row.segment_id: row.segment_id for row in provisional_lane_rows}

    def find(segment_id: str) -> str:
        root = parent[segment_id]
        while root != parent[root]:
            root = parent[root]
        while segment_id != root:
            next_segment = parent[segment_id]
            parent[segment_id] = root
            segment_id = next_segment
        return root

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    for linked_segments in continuity_links_by_segment.values():
        ordered = sorted(linked_segments)
        for left, right in zip(ordered, ordered[1:]):
            union(left, right)
    for segment_id, linked_segments in continuity_links_by_segment.items():
        for linked_segment_id in linked_segments:
            union(segment_id, linked_segment_id)

    component_members: dict[str, list[str]] = defaultdict(list)
    for row in provisional_lane_rows:
        component_members[find(row.segment_id)].append(row.segment_id)
    continuity_anchor_by_segment = {
        segment_id: stable_id("layout_continuity_anchor", *sorted(component))
        for component in component_members.values()
        for segment_id in component
    }

    lane_layout = sorted(
        [
            LaneLayoutRow(
                segment_id=row.segment_id,
                asset_id=row.asset_id,
                lane_group=row.lane_group,
                date_start=row.date_start,
                date_end=row.date_end,
                display_rank=row.display_rank,
                band_slot=row.band_slot,
                compaction_group=compaction_group_by_segment.get(row.segment_id),
                continuity_anchor=continuity_anchor_by_segment.get(
                    row.segment_id,
                    stable_id("layout_continuity_anchor", row.segment_id),
                ),
                entry_slot=row.entry_slot,
                exit_slot=row.exit_slot,
                identity_marker=row.identity_marker,
            )
            for row in provisional_lane_rows
        ],
        key=lambda row: (row.lane_group, row.band_slot, row.date_start, row.asset_id, row.segment_id),
    )

    label_layout = sorted(
        [
            LabelLayoutRow(
                segment_id=row.segment_id,
                asset_id=row.asset_id,
                date_start=row.date_start,
                date_end=row.date_end,
                inline_label_allowed=_segment_duration_days(row.date_start, row.date_end) > 1
                and edge_by_segment_id[row.segment_id].edge_type != "transition_line",
                label_priority=row.display_rank,
                fallback_marker_required=not (
                    _segment_duration_days(row.date_start, row.date_end) > 1
                    and edge_by_segment_id[row.segment_id].edge_type != "transition_line"
                ),
                marker_side="left",
            )
            for row in lane_layout
        ],
        key=lambda row: (row.label_priority, row.date_start, row.segment_id),
    )

    presentation_event_ids = {row.event_id for row in event_nodes if row.event_id is not None}
    presentation_asset_ids = {row.asset_id for row in lane_layout}
    chapter_layout: list[ChapterLayoutRow] = []
    if editorial_overlays is not None:
        for chapter in sorted(editorial_overlays.story_chapters, key=lambda row: (row.chapter_order, row.start_date, row.story_chapter_id)):
            focus_payload = chapter.focus_payload or {}
            window_start, window_end = _chapter_window(
                focus_payload.get("date_range"),
                fallback_start=chapter.start_date,
                fallback_end=chapter.end_date,
            )
            window_start = max(layout_meta.start_date, window_start)
            window_end = min(layout_meta.end_date, window_end)
            if window_end < window_start:
                window_end = window_start
            anchor_segment = next(
                (
                    segment
                    for segment in minimap_segments
                    if segment.start_date <= window_start <= segment.end_date
                ),
                minimap_segments[-1],
            )
            chapter_layout.append(
                ChapterLayoutRow(
                    story_chapter_id=chapter.story_chapter_id,
                    window_start=window_start,
                    window_end=window_end,
                    highlight_asset_ids=[
                        asset_id
                        for asset_id in _chapter_focus_ids(focus_payload.get("asset_ids"))
                        if asset_id in presentation_asset_ids
                    ],
                    highlight_event_ids=[
                        event_id
                        for event_id in _chapter_focus_ids(focus_payload.get("event_ids"))
                        if event_id in presentation_event_ids
                    ],
                    minimap_anchor_id=anchor_segment.segment_id,
                    default_zoom=_chapter_default_zoom(focus_payload.get("default_zoom")),
                )
            )

    build = LayoutBuild(
        layout_build_id=stable_id(
            "layout_build",
            builder_version,
            built_at_value.isoformat(),
            presentation_result.build.presentation_build_id,
            editorial_overlays.build.editorial_build_id if editorial_overlays is not None else "no_editorial",
        ),
        built_at=built_at_value,
        builder_version=builder_version,
        presentation_build_id=presentation_result.build.presentation_build_id,
        editorial_build_id=editorial_overlays.build.editorial_build_id if editorial_overlays is not None else None,
        notes="Stage 8 layout contract build",
    )
    return LayoutContractBuildResult(
        build=build,
        layout_meta=layout_meta,
        lane_layout=lane_layout,
        event_layout=event_layout,
        label_layout=label_layout,
        chapter_layout=chapter_layout,
    )


def layout_contract_to_json(result: LayoutContractBuildResult) -> str:
    return json.dumps(_json_ready(result.as_contract()), sort_keys=True, indent=2)


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


def build_layout_contract_from_db(
    *,
    builder_version: str = "stage8-layout-contract-v1",
    headshot_manifest_path: Path | str = HEADSHOT_MANIFEST_PATH,
    frontend_public_root: Path | str = FRONTEND_PUBLIC_ROOT,
) -> LayoutContractBuildResult:
    with _connect() as conn:
        presentation_result = fetch_presentation_contract(conn)
        try:
            from editorial.contract import fetch_editorial_overlays

            editorial_result = fetch_editorial_overlays(conn)
        except RuntimeError:
            editorial_result = None
    return build_layout_contract(
        presentation_result=presentation_result,
        editorial_overlays=editorial_result,
        builder_version=builder_version,
        headshot_manifest_path=headshot_manifest_path,
        frontend_public_root=frontend_public_root,
    )


def export_layout_contract_json(
    output_path: Path | str | None = None,
    *,
    builder_version: str = "stage8-layout-contract-v1",
    headshot_manifest_path: Path | str = HEADSHOT_MANIFEST_PATH,
    frontend_public_root: Path | str = FRONTEND_PUBLIC_ROOT,
) -> str:
    result = build_layout_contract_from_db(
        builder_version=builder_version,
        headshot_manifest_path=headshot_manifest_path,
        frontend_public_root=frontend_public_root,
    )
    payload = layout_contract_to_json(result)
    if output_path is not None:
        Path(output_path).write_text(payload + "\n", encoding="utf-8")
    return payload
