from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

from canonical.models import CanonicalAsset, CanonicalEvent, CanonicalEventAssetFlow, EventAssetFlowProvenance


FLOW_DIRECTIONS = {"in", "out"}
FLOW_ROLES = {
    "incoming_player",
    "outgoing_player",
    "incoming_pick",
    "outgoing_pick",
    "pick_consumed",
    "player_emerges",
}

PLAYER_FLOW_ROLES = {"incoming_player", "outgoing_player"}
PICK_FLOW_ROLES = {"incoming_pick", "outgoing_pick", "pick_consumed", "player_emerges"}


@dataclass(frozen=True)
class CanonicalEventAssetFlowValidationReport:
    event_count: int
    asset_count: int
    flow_count: int
    provenance_count: int
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _trade_direction(description: str | None) -> str:
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


def validate_canonical_event_asset_flows(
    *,
    events: Iterable[CanonicalEvent],
    assets: Iterable[CanonicalAsset],
    flows: Iterable[CanonicalEventAssetFlow],
    provenance_rows: Iterable[EventAssetFlowProvenance],
) -> CanonicalEventAssetFlowValidationReport:
    events_list = list(events)
    assets_list = list(assets)
    flows_list = list(flows)
    provenance_list = list(provenance_rows)

    errors: list[str] = []
    warnings: list[str] = []

    event_ids = [event.event_id for event in events_list]
    duplicate_event_ids = [event_id for event_id, count in Counter(event_ids).items() if count > 1]
    if duplicate_event_ids:
        errors.append(f"duplicate event_ids: {', '.join(sorted(duplicate_event_ids))}")

    asset_ids = [asset.asset_id for asset in assets_list]
    asset_id_set = set(asset_ids)
    duplicate_asset_ids = [asset_id for asset_id, count in Counter(asset_ids).items() if count > 1]
    if duplicate_asset_ids:
        errors.append(f"duplicate asset_ids: {', '.join(sorted(duplicate_asset_ids))}")

    event_by_id = {event.event_id: event for event in events_list}
    asset_by_id = {asset.asset_id: asset for asset in assets_list}

    duplicate_flow_ids = [flow_id for flow_id, count in Counter(flow.event_asset_flow_id for flow in flows_list).items() if count > 1]
    if duplicate_flow_ids:
        errors.append(f"duplicate event_asset_flow_ids: {', '.join(sorted(duplicate_flow_ids))}")

    flows_by_event: dict[str, list[CanonicalEventAssetFlow]] = defaultdict(list)
    flows_by_asset_event: dict[tuple[str, str], list[CanonicalEventAssetFlow]] = defaultdict(list)
    for row in flows_list:
        flows_by_event[row.event_id].append(row)
        flows_by_asset_event[(row.event_id, row.asset_id)].append(row)
        if row.event_id not in event_by_id:
            errors.append(f"flow references unknown event_id: {row.event_id}")
        if row.asset_id not in asset_id_set:
            errors.append(f"flow references unknown asset_id: {row.asset_id}")
        if row.flow_direction not in FLOW_DIRECTIONS:
            errors.append(f"invalid flow_direction for {row.event_asset_flow_id}: {row.flow_direction}")
        if row.flow_role not in FLOW_ROLES:
            errors.append(f"invalid flow_role for {row.event_asset_flow_id}: {row.flow_role}")
        if row.flow_order <= 0:
            errors.append(f"non-positive flow_order for {row.event_asset_flow_id}")

        asset = asset_by_id.get(row.asset_id)
        if asset is not None:
            if row.flow_role in PLAYER_FLOW_ROLES and asset.asset_kind != "player_tenure":
                errors.append(f"player flow role requires player_tenure asset for {row.event_asset_flow_id}")
            if row.flow_role in PICK_FLOW_ROLES and asset.asset_kind != "pick_continuity":
                errors.append(f"pick flow role requires pick_continuity asset for {row.event_asset_flow_id}")

    for event_id, event_flows in flows_by_event.items():
        orders = [row.flow_order for row in event_flows]
        if len(orders) != len(set(orders)):
            errors.append(f"duplicate same-event flow_order on {event_id}")
        expected = list(range(1, len(orders) + 1))
        if sorted(orders) != expected:
            errors.append(f"non-dense same-event flow_order on {event_id}")

    provenance_by_flow: dict[str, list[EventAssetFlowProvenance]] = defaultdict(list)
    for row in provenance_list:
        provenance_by_flow[row.event_asset_flow_id].append(row)
        if row.event_asset_flow_id not in {flow.event_asset_flow_id for flow in flows_list}:
            errors.append(f"flow provenance references unknown event_asset_flow_id: {row.event_asset_flow_id}")
        expected_role = next((flow.flow_role for flow in flows_list if flow.event_asset_flow_id == row.event_asset_flow_id), None)
        if expected_role is not None and row.provenance_role != f"{expected_role}_support":
            errors.append(f"unexpected flow provenance role for {row.event_asset_flow_id}: {row.provenance_role}")

    for row in flows_list:
        if not provenance_by_flow.get(row.event_asset_flow_id):
            errors.append(f"missing provenance for {row.event_asset_flow_id}")

    draft_events = [event for event in events_list if event.event_type == "draft"]
    for event in draft_events:
        event_flows = flows_by_event.get(event.event_id, [])
        if not event_flows:
            continue
        pick_flow_count = sum(
            1
            for row in event_flows
            if asset_by_id.get(row.asset_id) is not None
            and asset_by_id[row.asset_id].asset_kind == "pick_continuity"
        )
        if pick_flow_count == 0:
            continue
        pick_assets_with_both_roles = set()
        for asset_id, asset_flows in (
            (asset_id, rows)
            for (event_id, asset_id), rows in flows_by_asset_event.items()
            if event_id == event.event_id
        ):
            directions = {row.flow_direction for row in asset_flows}
            roles = {row.flow_role for row in asset_flows}
            asset = asset_by_id.get(asset_id)
            if directions == {"in", "out"}:
                if asset is None or asset.asset_kind != "pick_continuity":
                    errors.append(f"only pick continuity assets may flow both ways in one draft event: {asset_id}")
                if roles != {"pick_consumed", "player_emerges"}:
                    errors.append(f"draft event dual-direction flow must use pick_consumed/player_emerges for {asset_id}")
                pick_assets_with_both_roles.add(asset_id)
            elif len(directions) > 1:
                errors.append(f"unexpected multi-direction flow for {asset_id} in draft event {event.event_id}")
        if not pick_assets_with_both_roles:
            errors.append(f"draft event missing pick_consumed/player_emerges pair: {event.event_id}")

    for event in events_list:
        if event.event_type != "trade":
            continue
        if _trade_direction(event.description) == "unknown":
            continue
        if not flows_by_event.get(event.event_id):
            warnings.append(f"trade event with Memphis activity has no modeled asset flow rows: {event.event_id}")

    for event in events_list:
        if event.event_type == "draft":
            continue
        for asset_id, asset_flows in (
            (asset_id, rows)
            for (event_id, asset_id), rows in flows_by_asset_event.items()
            if event_id == event.event_id
        ):
            directions = {row.flow_direction for row in asset_flows}
            if len(directions) > 1:
                errors.append(f"asset appears to both enter and exit in one event without draft support: {event.event_id}/{asset_id}")

    return CanonicalEventAssetFlowValidationReport(
        event_count=len(events_list),
        asset_count=len(assets_list),
        flow_count=len(flows_list),
        provenance_count=len(provenance_list),
        errors=errors,
        warnings=warnings,
    )


validate_canonical_event_asset_flow_rows = validate_canonical_event_asset_flows
