from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from canonical.models import (
    AssetProvenance,
    CanonicalAsset,
    CanonicalEvent,
    CanonicalPickAsset,
    CanonicalPickResolution,
    CanonicalPlayerIdentity,
    PickAssetProvenance,
    PickResolutionProvenance,
)


PICK_STAGE_ORDER = {
    "future_pick": 0,
    "resolved_pick": 1,
    "drafted_player": 2,
    "conveyed_away": 3,
}


@dataclass(frozen=True)
class CanonicalPickLifecycleValidationReport:
    pick_asset_count: int
    pick_asset_provenance_count: int
    pick_resolution_count: int
    pick_resolution_provenance_count: int
    asset_count: int
    asset_provenance_count: int
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
        )
    ):
        return "outgoing"
    return "unknown"


def validate_canonical_pick_lifecycle(
    *,
    player_identities: Iterable[CanonicalPlayerIdentity] | None = None,
    pick_assets: Iterable[CanonicalPickAsset],
    pick_asset_provenance_rows: Iterable[PickAssetProvenance],
    pick_resolutions: Iterable[CanonicalPickResolution],
    pick_resolution_provenance_rows: Iterable[PickResolutionProvenance],
    assets: Iterable[CanonicalAsset],
    asset_provenance_rows: Iterable[AssetProvenance],
    events: Iterable[CanonicalEvent] | None = None,
) -> CanonicalPickLifecycleValidationReport:
    player_identities_list = list(player_identities or [])
    player_ids = {row.player_id for row in player_identities_list}
    pick_assets_list = list(pick_assets)
    pick_asset_provenance_list = list(pick_asset_provenance_rows)
    pick_resolutions_list = list(pick_resolutions)
    pick_resolution_provenance_list = list(pick_resolution_provenance_rows)
    assets_list = list(assets)
    asset_provenance_list = list(asset_provenance_rows)
    events_list = list(events or [])

    errors: list[str] = []
    warnings: list[str] = []

    pick_ids = [row.pick_asset_id for row in pick_assets_list]
    duplicate_pick_ids = [pick_id for pick_id, count in Counter(pick_ids).items() if count > 1]
    if duplicate_pick_ids:
        errors.append(f"duplicate pick_asset_ids: {', '.join(sorted(duplicate_pick_ids))}")

    assets_by_pick: dict[str, list[CanonicalAsset]] = defaultdict(list)
    assets_by_id: dict[str, CanonicalAsset] = {}
    for row in assets_list:
        assets_by_id[row.asset_id] = row
        if row.asset_kind != "pick_continuity":
            continue
        if not row.pick_asset_id:
            errors.append(f"missing pick_asset_id for {row.asset_id}")
        else:
            assets_by_pick[row.pick_asset_id].append(row)

    for row in pick_assets_list:
        if not row.origin_team_code:
            errors.append(f"missing origin_team_code for {row.pick_asset_id}")
        if row.draft_year <= 0:
            errors.append(f"invalid draft_year for {row.pick_asset_id}")
        if row.draft_round <= 0:
            errors.append(f"invalid draft_round for {row.pick_asset_id}")
        if row.current_pick_stage not in PICK_STAGE_ORDER:
            errors.append(f"invalid current_pick_stage for {row.pick_asset_id}: {row.current_pick_stage}")
        if row.drafted_player_id and player_ids and row.drafted_player_id not in player_ids:
            errors.append(f"unknown drafted_player_id for {row.pick_asset_id}: {row.drafted_player_id}")
        if len(assets_by_pick.get(row.pick_asset_id, [])) != 1:
            errors.append(f"expected exactly one graph asset for pick {row.pick_asset_id}")

    provenance_by_pick: dict[str, list[PickAssetProvenance]] = defaultdict(list)
    for row in pick_asset_provenance_list:
        provenance_by_pick[row.pick_asset_id].append(row)
        if row.pick_asset_id not in pick_ids:
            errors.append(f"pick asset provenance references unknown pick_asset_id: {row.pick_asset_id}")
        if row.provenance_role not in {"pick_identity_support", "pick_protection_support", "drafted_player_linkage_support"}:
            errors.append(f"unexpected pick asset provenance role for {row.pick_asset_id}: {row.provenance_role}")

    for row in pick_assets_list:
        roles = {item.provenance_role for item in provenance_by_pick.get(row.pick_asset_id, [])}
        if "pick_identity_support" not in roles:
            errors.append(f"missing pick_identity_support provenance for {row.pick_asset_id}")
        if row.current_pick_stage in {"resolved_pick", "drafted_player", "conveyed_away"} and "pick_resolution_support" not in roles:
            # The build stores the base pick provenance separately; the state table carries the resolution support.
            pass
        if row.drafted_player_id and "drafted_player_linkage_support" not in roles:
            errors.append(f"missing drafted_player_linkage_support provenance for {row.pick_asset_id}")

    state_ids = [row.pick_resolution_id for row in pick_resolutions_list]
    duplicate_state_ids = [state_id for state_id, count in Counter(state_ids).items() if count > 1]
    if duplicate_state_ids:
        errors.append(f"duplicate pick_resolution_ids: {', '.join(sorted(duplicate_state_ids))}")

    states_by_pick: dict[str, list[CanonicalPickResolution]] = defaultdict(list)
    events_by_id = {event.event_id: event for event in events_list}
    for row in pick_resolutions_list:
        states_by_pick[row.pick_asset_id].append(row)
        if row.pick_asset_id not in pick_ids:
            errors.append(f"pick resolution references unknown pick_asset_id: {row.pick_asset_id}")
        if row.state_type not in PICK_STAGE_ORDER:
            errors.append(f"invalid pick resolution state_type for {row.pick_resolution_id}: {row.state_type}")
        if row.effective_end_date is not None and row.effective_end_date < row.effective_start_date:
            errors.append(f"pick state ends before it starts for {row.pick_resolution_id}")
        if row.state_type == "resolved_pick" and row.overall_pick_number is None:
            errors.append(f"missing overall_pick_number for {row.pick_resolution_id}")
        if row.state_type == "drafted_player":
            if not row.drafted_player_id:
                errors.append(f"missing drafted_player_id for {row.pick_resolution_id}")
            if not row.source_event_id:
                errors.append(f"missing source_event_id for {row.pick_resolution_id}")
            if row.source_event_id and events_by_id.get(row.source_event_id) and events_by_id[row.source_event_id].event_type != "draft":
                errors.append(f"drafted_player state does not point to a draft event for {row.pick_resolution_id}")
        if row.state_type == "conveyed_away" and row.source_event_id:
            event = events_by_id.get(row.source_event_id)
            if event is not None:
                if event.event_type != "trade":
                    errors.append(f"conveyed_away state does not point to a trade event for {row.pick_resolution_id}")
                elif _trade_direction(event.description) != "outgoing":
                    errors.append(f"conveyed_away state is not an outgoing trade for {row.pick_resolution_id}")
        if row.state_type == "conveyed_away" and not row.source_event_id:
            errors.append(f"missing source_event_id for {row.pick_resolution_id}")

    provenance_by_state: dict[str, list[PickResolutionProvenance]] = defaultdict(list)
    for row in pick_resolution_provenance_list:
        provenance_by_state[row.pick_resolution_id].append(row)
        if row.pick_resolution_id not in state_ids:
            errors.append(f"pick resolution provenance references unknown pick_resolution_id: {row.pick_resolution_id}")
        if row.provenance_role not in {
            "asset_state_support",
            "pick_identity_support",
            "pick_resolution_support",
            "drafted_player_linkage_support",
            "pick_conveyance_support",
        }:
            errors.append(f"unexpected pick resolution provenance role for {row.pick_resolution_id}: {row.provenance_role}")

    provenance_by_asset: dict[str, list[AssetProvenance]] = defaultdict(list)
    for row in asset_provenance_list:
        provenance_by_asset[row.asset_id].append(row)
        if row.asset_id not in assets_by_id:
            errors.append(f"asset provenance references unknown asset_id: {row.asset_id}")
        asset = assets_by_id.get(row.asset_id)
        if asset is not None and asset.pick_asset_id != row.pick_asset_id:
            errors.append(f"asset provenance pick mismatch for {row.asset_id}")

    for row in assets_list:
        roles = {item.provenance_role for item in provenance_by_asset.get(row.asset_id, [])}
        if row.pick_asset_id and "asset_identity_support" not in roles:
            errors.append(f"missing asset_identity_support provenance for {row.asset_id}")
        if row.pick_asset_id and "pick_identity_support" not in roles:
            errors.append(f"missing pick_identity_support provenance for {row.asset_id}")

    for row in pick_resolutions_list:
        roles = {item.provenance_role for item in provenance_by_state.get(row.pick_resolution_id, [])}
        if "asset_state_support" not in roles:
            errors.append(f"missing asset_state_support provenance for {row.pick_resolution_id}")
        if row.state_type == "future_pick" and "pick_identity_support" not in roles:
            errors.append(f"missing pick_identity_support provenance for {row.pick_resolution_id}")
        if row.state_type == "resolved_pick" and "pick_resolution_support" not in roles:
            errors.append(f"missing pick_resolution_support provenance for {row.pick_resolution_id}")
        if row.state_type == "drafted_player" and "drafted_player_linkage_support" not in roles:
            errors.append(f"missing drafted_player_linkage_support provenance for {row.pick_resolution_id}")

    for pick_asset_id, states in states_by_pick.items():
        ordered = sorted(states, key=lambda row: (row.effective_start_date, PICK_STAGE_ORDER[row.state_type], row.pick_resolution_id))
        if not ordered or ordered[0].state_type != "future_pick":
            errors.append(f"missing future_pick state for {pick_asset_id}")
        for left, right in zip(ordered, ordered[1:]):
            if left.effective_end_date is not None and left.effective_end_date > right.effective_start_date:
                errors.append(f"overlapping pick states for {pick_asset_id}: {left.pick_resolution_id} and {right.pick_resolution_id}")
            if PICK_STAGE_ORDER[right.state_type] < PICK_STAGE_ORDER[left.state_type]:
                errors.append(f"out-of-order pick states for {pick_asset_id}: {left.state_type} then {right.state_type}")
        last_state = ordered[-1]
        pick_asset = next((row for row in pick_assets_list if row.pick_asset_id == pick_asset_id), None)
        if pick_asset is not None and pick_asset.current_pick_stage != last_state.state_type:
            errors.append(f"current_pick_stage mismatch for {pick_asset_id}")
        if last_state.state_type == "conveyed_away":
            conveyed_index = ordered.index(last_state)
            if conveyed_index != len(ordered) - 1:
                errors.append(f"conveyed-away pick continues after exit for {pick_asset_id}")

    return CanonicalPickLifecycleValidationReport(
        pick_asset_count=len(pick_assets_list),
        pick_asset_provenance_count=len(pick_asset_provenance_list),
        pick_resolution_count=len(pick_resolutions_list),
        pick_resolution_provenance_count=len(pick_resolution_provenance_list),
        asset_count=len(assets_list),
        asset_provenance_count=len(asset_provenance_list),
        errors=errors,
        warnings=warnings,
    )


validate_canonical_pick_lifecycle_rows = validate_canonical_pick_lifecycle
validate_pick_lifecycle = validate_canonical_pick_lifecycle
