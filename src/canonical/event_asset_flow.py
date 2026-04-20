from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from canonical.models import (
    CanonicalAsset,
    CanonicalBuild,
    CanonicalEvent,
    CanonicalEventAssetFlow,
    CanonicalEventAssetFlowBuildResult,
    EventAssetFlowProvenance,
    EventProvenance,
    CanonicalPlayerTenure,
    CanonicalPickResolution,
)
from db_config import load_database_url
from shared.ids import stable_id, stable_payload_hash


FLOW_DIRECTIONS = {"in", "out"}
FLOW_ROLES = {
    "incoming_player",
    "outgoing_player",
    "incoming_pick",
    "outgoing_pick",
    "pick_consumed",
    "player_emerges",
}

FLOW_ROLE_ORDER = {
    "outgoing_player": 0,
    "outgoing_pick": 1,
    "pick_consumed": 2,
    "incoming_player": 3,
    "incoming_pick": 4,
    "player_emerges": 5,
}

FLOW_ROLE_TO_PROVENANCE_ROLE = {
    "incoming_player": "incoming_player_support",
    "outgoing_player": "outgoing_player_support",
    "incoming_pick": "incoming_pick_support",
    "outgoing_pick": "outgoing_pick_support",
    "pick_consumed": "pick_consumed_support",
    "player_emerges": "player_emerges_support",
}


@dataclass(frozen=True)
class _FlowCandidate:
    event_id: str
    asset_id: str
    flow_direction: str
    flow_role: str
    effective_date: date
    provenance_source: str
    source_key: str


def bootstrap_canonical_event_asset_flow_schema(sql_path: Path | str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required to bootstrap canonical event asset flow tables.") from exc

    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with psycopg.connect(load_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
        conn.commit()


def _connect():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for canonical event asset flow builds.") from exc
    return psycopg.connect(load_database_url())


def _event_direction_keywords(description: str | None) -> str:
    text = (description or "").lower()
    if any(marker in text for marker in ("to memphis", "to the grizzlies", "joins memphis", "acquired by memphis", "memphis acquires")):
        return "incoming"
    if any(
        marker in text
        for marker in (
            "from memphis",
            "sent to",
            "traded away",
            "trades",
            "trading",
            "released by memphis",
            "waived by memphis",
            "buyout",
        )
    ):
        return "outgoing"
    return "unknown"


def _event_support_row(event_id: str, provenance_by_event: dict[str, list[EventProvenance]]) -> EventProvenance | None:
    rows = list(provenance_by_event.get(event_id, []))
    if not rows:
        return None

    def sort_key(row: EventProvenance) -> tuple[int, str, str, str]:
        preferred = {
            "event_date_support": 0,
            "event_type_support": 1,
            "event_description_support": 2,
            "event_cluster_support": 3,
            "event_order_override": 4,
            "event_order_source_fallback": 5,
            "event_order_deterministic_fallback": 6,
        }.get(row.provenance_role, 10)
        return (
            preferred,
            row.claim_id or "",
            row.source_record_id or "",
            row.override_id or "",
        )

    return sorted(rows, key=sort_key)[0]


def _asset_by_subtype(assets: Iterable[CanonicalAsset]) -> tuple[dict[str, CanonicalAsset], dict[str, CanonicalAsset]]:
    by_player_tenure: dict[str, CanonicalAsset] = {}
    by_pick_asset: dict[str, CanonicalAsset] = {}
    for asset in assets:
        if asset.player_tenure_id:
            by_player_tenure[asset.player_tenure_id] = asset
        if asset.pick_asset_id:
            by_pick_asset[asset.pick_asset_id] = asset
    return by_player_tenure, by_pick_asset


def _build_flow_candidates(
    events: Iterable[CanonicalEvent],
    assets: Iterable[CanonicalAsset],
    player_tenures: Iterable[CanonicalPlayerTenure],
    pick_resolutions: Iterable[CanonicalPickResolution],
) -> list[_FlowCandidate]:
    events_by_id = {event.event_id: event for event in events}
    player_asset_by_tenure, pick_asset_by_pick = _asset_by_subtype(assets)
    candidates: list[_FlowCandidate] = []

    for tenure in player_tenures:
        asset = player_asset_by_tenure.get(tenure.player_tenure_id)
        if asset is None:
            raise ValueError(f"canonical event asset flow build requires a graph asset for tenure {tenure.player_tenure_id}.")

        entry_event = events_by_id.get(tenure.entry_event_id)
        if entry_event is not None:
            candidates.append(
                _FlowCandidate(
                    event_id=entry_event.event_id,
                    asset_id=asset.asset_id,
                    flow_direction="out",
                    flow_role="incoming_player",
                    effective_date=entry_event.event_date,
                    provenance_source="player_tenure_entry",
                    source_key=tenure.player_tenure_id,
                )
            )

        if tenure.exit_event_id:
            exit_event = events_by_id.get(tenure.exit_event_id)
            if exit_event is not None:
                candidates.append(
                    _FlowCandidate(
                        event_id=exit_event.event_id,
                        asset_id=asset.asset_id,
                        flow_direction="in",
                        flow_role="outgoing_player",
                        effective_date=exit_event.event_date,
                        provenance_source="player_tenure_exit",
                        source_key=tenure.player_tenure_id,
                    )
                )

    for resolution in pick_resolutions:
        asset = pick_asset_by_pick.get(resolution.pick_asset_id)
        if asset is None:
            raise ValueError(f"canonical event asset flow build requires a graph asset for pick {resolution.pick_asset_id}.")
        event = events_by_id.get(resolution.source_event_id or "")
        if event is None:
            continue

        if resolution.state_type == "future_pick" and event.event_type != "draft":
            candidates.append(
                _FlowCandidate(
                    event_id=event.event_id,
                    asset_id=asset.asset_id,
                    flow_direction="out",
                    flow_role="incoming_pick",
                    effective_date=event.event_date,
                    provenance_source="pick_future_state",
                    source_key=resolution.pick_resolution_id,
                )
            )
        elif resolution.state_type == "conveyed_away":
            candidates.append(
                _FlowCandidate(
                    event_id=event.event_id,
                    asset_id=asset.asset_id,
                    flow_direction="in",
                    flow_role="outgoing_pick",
                    effective_date=event.event_date,
                    provenance_source="pick_conveyance_state",
                    source_key=resolution.pick_resolution_id,
                )
            )
        elif resolution.state_type == "drafted_player":
            candidates.append(
                _FlowCandidate(
                    event_id=event.event_id,
                    asset_id=asset.asset_id,
                    flow_direction="in",
                    flow_role="pick_consumed",
                    effective_date=event.event_date,
                    provenance_source="pick_draft_state",
                    source_key=resolution.pick_resolution_id,
                )
            )
            candidates.append(
                _FlowCandidate(
                    event_id=event.event_id,
                    asset_id=asset.asset_id,
                    flow_direction="out",
                    flow_role="player_emerges",
                    effective_date=event.event_date,
                    provenance_source="pick_draft_state",
                    source_key=resolution.pick_resolution_id,
                )
            )

    return candidates


def build_event_asset_flows(
    events: Iterable[CanonicalEvent],
    event_provenance: Iterable[EventProvenance],
    assets: Iterable[CanonicalAsset],
    player_tenures: Iterable[CanonicalPlayerTenure],
    pick_resolutions: Iterable[CanonicalPickResolution],
    *,
    builder_version: str = "stage5-event-asset-flow-v1",
    built_at: datetime | None = None,
) -> CanonicalEventAssetFlowBuildResult:
    built_at_value = built_at or datetime.utcnow()
    events_list = list(events)
    event_provenance_list = list(event_provenance)
    assets_list = list(assets)
    player_tenures_list = list(player_tenures)
    pick_resolutions_list = list(pick_resolutions)

    flow_candidates = _build_flow_candidates(events_list, assets_list, player_tenures_list, pick_resolutions_list)
    event_by_id = {event.event_id: event for event in events_list}
    asset_by_id = {asset.asset_id: asset for asset in assets_list}
    provenance_by_event: dict[str, list[EventProvenance]] = defaultdict(list)
    for row in event_provenance_list:
        provenance_by_event[row.event_id].append(row)

    flow_rows_by_id: dict[str, CanonicalEventAssetFlow] = {}
    provenance_rows_by_id: dict[str, EventAssetFlowProvenance] = {}

    for event_id in sorted({candidate.event_id for candidate in flow_candidates}, key=lambda value: (event_by_id[value].event_date, event_by_id[value].event_order, value)):
        event_candidates = [candidate for candidate in flow_candidates if candidate.event_id == event_id]
        event_candidates.sort(
            key=lambda candidate: (
                0 if candidate.flow_direction == "in" else 1,
                FLOW_ROLE_ORDER.get(candidate.flow_role, 99),
                asset_by_id[candidate.asset_id].asset_label,
                candidate.asset_id,
                candidate.source_key,
            )
        )
        for flow_order, candidate in enumerate(event_candidates, start=1):
            flow_id = stable_id(
                "event_asset_flow",
                candidate.event_id,
                candidate.asset_id,
                candidate.flow_direction,
                candidate.flow_role,
            )
            flow_rows_by_id[flow_id] = CanonicalEventAssetFlow(
                event_asset_flow_id=flow_id,
                event_id=candidate.event_id,
                asset_id=candidate.asset_id,
                flow_direction=candidate.flow_direction,
                flow_role=candidate.flow_role,
                flow_order=flow_order,
                effective_date=candidate.effective_date,
                created_at=built_at_value,
            )

            support_row = _event_support_row(candidate.event_id, provenance_by_event)
            provenance_role = FLOW_ROLE_TO_PROVENANCE_ROLE[candidate.flow_role]
            if support_row is None:
                provenance_rows_by_id[stable_id("event_asset_flow_prov", flow_id, provenance_role, candidate.source_key)] = EventAssetFlowProvenance(
                    event_asset_flow_provenance_id=stable_id("event_asset_flow_prov", flow_id, provenance_role, candidate.source_key),
                    event_asset_flow_id=flow_id,
                    source_record_id=None,
                    claim_id=None,
                    override_id=None,
                    provenance_role=provenance_role,
                    fallback_reason=f"derived_from_{candidate.provenance_source}",
                    created_at=built_at_value,
                )
            else:
                fallback_reason = (
                    support_row.fallback_reason
                    if support_row.source_record_id is None and support_row.claim_id is None and support_row.override_id is None
                    else None
                )
                provenance_rows_by_id[stable_id("event_asset_flow_prov", flow_id, provenance_role, support_row.claim_id or support_row.source_record_id or support_row.override_id or candidate.source_key)] = EventAssetFlowProvenance(
                    event_asset_flow_provenance_id=stable_id(
                        "event_asset_flow_prov",
                        flow_id,
                        provenance_role,
                        support_row.claim_id or support_row.source_record_id or support_row.override_id or candidate.source_key,
                    ),
                    event_asset_flow_id=flow_id,
                    source_record_id=support_row.source_record_id,
                    claim_id=support_row.claim_id,
                    override_id=support_row.override_id,
                    provenance_role=provenance_role,
                    fallback_reason=fallback_reason,
                    created_at=built_at_value,
                )

    flow_rows = sorted(flow_rows_by_id.values(), key=lambda row: (event_by_id[row.event_id].event_date, event_by_id[row.event_id].event_order, row.flow_order, row.asset_id, row.flow_role, row.event_asset_flow_id))
    provenance_rows = sorted(provenance_rows_by_id.values(), key=lambda row: (row.event_asset_flow_id, row.provenance_role, row.event_asset_flow_provenance_id))

    evidence_build_hash = stable_payload_hash(
        {
            "event_ids": [event.event_id for event in sorted(events_list, key=lambda event: (event.event_date, event.event_order, event.event_id))],
            "asset_ids": [asset.asset_id for asset in sorted(assets_list, key=lambda asset: asset.asset_id)],
            "player_tenure_ids": [tenure.player_tenure_id for tenure in sorted(player_tenures_list, key=lambda tenure: tenure.player_tenure_id)],
            "pick_resolution_ids": [resolution.pick_resolution_id for resolution in sorted(pick_resolutions_list, key=lambda resolution: resolution.pick_resolution_id)],
            "event_provenance_ids": [row.event_provenance_id for row in sorted(event_provenance_list, key=lambda row: row.event_provenance_id)],
        }
    )
    build = CanonicalBuild(
        canonical_build_id=stable_id("canonical_build", builder_version, built_at_value.isoformat(), evidence_build_hash),
        built_at=built_at_value,
        builder_version=builder_version,
        evidence_build_id=stable_id("evidence_build", evidence_build_hash),
        override_snapshot_hash=None,
        notes="Stage 5 event asset flow build",
    )
    return CanonicalEventAssetFlowBuildResult(build=build, flows=flow_rows, provenance_rows=provenance_rows)


def fetch_event_asset_flow_build_inputs(
    conn: Any,
) -> tuple[
    list[CanonicalEvent],
    list[EventProvenance],
    list[CanonicalAsset],
    list[CanonicalPlayerTenure],
    list[CanonicalPickResolution],
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
                event_provenance_id,
                event_id,
                source_record_id,
                claim_id,
                override_id,
                provenance_role,
                fallback_reason,
                created_at
            from canonical.event_provenance
            order by created_at, event_provenance_id
            """
        )
        event_provenance_rows = cur.fetchall()
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
            order by player_tenure_id
            """
        )
        tenure_rows = cur.fetchall()
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
            order by pick_resolution_id
            """
        )
        pick_resolution_rows = cur.fetchall()

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
    event_provenance = [
        EventProvenance(
            event_provenance_id=row[0],
            event_id=row[1],
            source_record_id=row[2],
            claim_id=row[3],
            override_id=row[4],
            provenance_role=row[5],
            fallback_reason=row[6],
            created_at=row[7],
        )
        for row in event_provenance_rows
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
        for row in tenure_rows
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
    return events, event_provenance, assets, player_tenures, pick_resolutions


def persist_canonical_event_asset_flow_build(conn: Any, result: CanonicalEventAssetFlowBuildResult) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("delete from canonical.event_asset_flow_provenance")
        cur.execute("delete from canonical.event_asset_flow")
        cur.execute(
            """
            insert into canonical.builds (
                canonical_build_id,
                built_at,
                builder_version,
                evidence_build_id,
                override_snapshot_hash,
                notes
            )
            values (%s, %s, %s, %s, %s, %s)
            """,
            (
                result.build.canonical_build_id,
                result.build.built_at,
                result.build.builder_version,
                result.build.evidence_build_id,
                result.build.override_snapshot_hash,
                result.build.notes,
            ),
        )
        for row in result.flows:
            cur.execute(
                """
                insert into canonical.event_asset_flow (
                    event_asset_flow_id,
                    event_id,
                    asset_id,
                    flow_direction,
                    flow_role,
                    flow_order,
                    effective_date,
                    created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row.event_asset_flow_id,
                    row.event_id,
                    row.asset_id,
                    row.flow_direction,
                    row.flow_role,
                    row.flow_order,
                    row.effective_date,
                    row.created_at,
                ),
            )
        for row in result.provenance_rows:
            cur.execute(
                """
                insert into canonical.event_asset_flow_provenance (
                    event_asset_flow_provenance_id,
                    event_asset_flow_id,
                    source_record_id,
                    claim_id,
                    override_id,
                    provenance_role,
                    fallback_reason,
                    created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row.event_asset_flow_provenance_id,
                    row.event_asset_flow_id,
                    row.source_record_id,
                    row.claim_id,
                    row.override_id,
                    row.provenance_role,
                    row.fallback_reason,
                    row.created_at,
                ),
            )
    return result.counts()


def build_and_persist_canonical_event_asset_flows(*, builder_version: str = "stage5-event-asset-flow-v1") -> dict[str, int]:
    with _connect() as conn:
        events, event_provenance, assets, player_tenures, pick_resolutions = fetch_event_asset_flow_build_inputs(conn)
        result = build_event_asset_flows(
            events,
            event_provenance,
            assets,
            player_tenures,
            pick_resolutions,
            builder_version=builder_version,
        )
        counts = persist_canonical_event_asset_flow_build(conn, result)
        conn.commit()
    return counts
