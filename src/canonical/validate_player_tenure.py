from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from canonical.models import (
    AssetProvenance,
    AssetState,
    AssetStateProvenance,
    CanonicalAsset,
    CanonicalPlayerIdentity,
    CanonicalPlayerTenure,
    PlayerIdentityProvenance,
)


@dataclass(frozen=True)
class CanonicalPlayerTenureValidationReport:
    player_identity_count: int
    player_identity_provenance_count: int
    player_tenure_count: int
    asset_count: int
    asset_provenance_count: int
    asset_state_count: int
    asset_state_provenance_count: int
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_canonical_player_tenures(
    *,
    player_identities: Iterable[CanonicalPlayerIdentity],
    player_identity_provenance_rows: Iterable[PlayerIdentityProvenance],
    player_tenures: Iterable[CanonicalPlayerTenure],
    assets: Iterable[CanonicalAsset],
    asset_provenance_rows: Iterable[AssetProvenance],
    asset_states: Iterable[AssetState],
    asset_state_provenance_rows: Iterable[AssetStateProvenance],
) -> CanonicalPlayerTenureValidationReport:
    player_identities_list = list(player_identities)
    player_identity_provenance_list = list(player_identity_provenance_rows)
    tenures_list = list(player_tenures)
    assets_list = list(assets)
    asset_provenance_list = list(asset_provenance_rows)
    asset_states_list = list(asset_states)
    asset_state_provenance_list = list(asset_state_provenance_rows)

    errors: list[str] = []
    warnings: list[str] = []

    player_ids = [row.player_id for row in player_identities_list]
    player_id_set = set(player_ids)
    duplicate_player_ids = [player_id for player_id, count in Counter(player_ids).items() if count > 1]
    if duplicate_player_ids:
        errors.append(f"duplicate player_ids: {', '.join(sorted(duplicate_player_ids))}")

    for row in player_identities_list:
        if not row.display_name:
            errors.append(f"missing display_name for {row.player_id}")
        if not row.normalized_name:
            errors.append(f"missing normalized_name for {row.player_id}")

    provenance_by_player: dict[str, list[PlayerIdentityProvenance]] = defaultdict(list)
    for row in player_identity_provenance_list:
        provenance_by_player[row.player_id].append(row)
        if row.player_id not in player_id_set:
            errors.append(f"player identity provenance references unknown player_id: {row.player_id}")
        if row.provenance_role != "player_identity_resolution_support":
            errors.append(f"unexpected player identity provenance role for {row.player_id}: {row.provenance_role}")

    for row in player_identities_list:
        if not provenance_by_player.get(row.player_id):
            errors.append(f"missing player identity provenance for {row.player_id}")

    tenures_by_player: dict[str, list[CanonicalPlayerTenure]] = defaultdict(list)
    tenure_ids = [row.player_tenure_id for row in tenures_list]
    duplicate_tenure_ids = [tenure_id for tenure_id, count in Counter(tenure_ids).items() if count > 1]
    if duplicate_tenure_ids:
        errors.append(f"duplicate player_tenure_ids: {', '.join(sorted(duplicate_tenure_ids))}")

    for row in tenures_list:
        tenures_by_player[row.player_id].append(row)
        if row.tenure_end_date is not None and row.tenure_end_date < row.tenure_start_date:
            errors.append(f"tenure ends before it starts for {row.player_tenure_id}")
        if not row.entry_event_id:
            errors.append(f"missing entry_event_id for {row.player_tenure_id}")

    for player_id, tenures in tenures_by_player.items():
        ordered = sorted(tenures, key=lambda row: (row.tenure_start_date, row.tenure_end_date or row.tenure_start_date, row.player_tenure_id))
        for left, right in zip(ordered, ordered[1:]):
            left_end = left.tenure_end_date or date.max
            if left_end > right.tenure_start_date:
                errors.append(f"overlapping tenures for {player_id}: {left.player_tenure_id} and {right.player_tenure_id}")

    asset_ids = [row.asset_id for row in assets_list]
    asset_id_set = set(asset_ids)
    duplicate_asset_ids = [asset_id for asset_id, count in Counter(asset_ids).items() if count > 1]
    if duplicate_asset_ids:
        errors.append(f"duplicate asset_ids: {', '.join(sorted(duplicate_asset_ids))}")

    assets_by_tenure: dict[str, list[CanonicalAsset]] = defaultdict(list)
    assets_by_id: dict[str, CanonicalAsset] = {}
    for row in assets_list:
        assets_by_tenure[row.player_tenure_id or ""].append(row)
        assets_by_id[row.asset_id] = row
        if row.asset_kind != "player_tenure":
            errors.append(f"unexpected asset_kind for {row.asset_id}: {row.asset_kind}")
        if not row.player_tenure_id:
            errors.append(f"missing player_tenure_id for {row.asset_id}")
        if row.pick_asset_id is not None:
            errors.append(f"player tenure asset should not have pick_asset_id: {row.asset_id}")

    for row in tenures_list:
        if len(assets_by_tenure.get(row.player_tenure_id, [])) != 1:
            errors.append(f"expected exactly one asset for tenure {row.player_tenure_id}")

    provenance_by_asset: dict[str, list[AssetProvenance]] = defaultdict(list)
    for row in asset_provenance_list:
        provenance_by_asset[row.asset_id].append(row)
        if row.asset_id not in asset_id_set:
            errors.append(f"asset provenance references unknown asset_id: {row.asset_id}")
        asset = assets_by_id.get(row.asset_id)
        if asset is not None and asset.player_tenure_id != row.player_tenure_id:
            errors.append(f"asset provenance tenure mismatch for {row.asset_id}")

    for row in assets_list:
        roles = {item.provenance_role for item in provenance_by_asset.get(row.asset_id, [])}
        if "asset_identity_support" not in roles:
            errors.append(f"missing asset_identity_support provenance for {row.asset_id}")
        if row.player_tenure_id and "player_identity_resolution_support" not in roles:
            errors.append(f"missing player_identity_resolution_support provenance for {row.asset_id}")

    state_ids = [row.asset_state_id for row in asset_states_list]
    state_id_set = set(state_ids)
    duplicate_state_ids = [state_id for state_id, count in Counter(state_ids).items() if count > 1]
    if duplicate_state_ids:
        errors.append(f"duplicate asset_state_ids: {', '.join(sorted(duplicate_state_ids))}")

    for row in asset_states_list:
        if row.effective_end_date is not None and row.effective_end_date < row.effective_start_date:
            errors.append(f"asset state ends before it starts for {row.asset_state_id}")
        if row.asset_id not in asset_id_set:
            errors.append(f"asset state references unknown asset_id: {row.asset_id}")
        if not row.state_type:
            errors.append(f"missing state_type for {row.asset_state_id}")

    provenance_by_state: dict[str, list[AssetStateProvenance]] = defaultdict(list)
    for row in asset_state_provenance_list:
        provenance_by_state[row.asset_state_id].append(row)
        if row.asset_state_id not in state_id_set:
            errors.append(f"asset state provenance references unknown asset_state_id: {row.asset_state_id}")

    for row in asset_states_list:
        roles = {item.provenance_role for item in provenance_by_state.get(row.asset_state_id, [])}
        if "asset_state_support" not in roles:
            errors.append(f"missing asset_state_support provenance for {row.asset_state_id}")

    return CanonicalPlayerTenureValidationReport(
        player_identity_count=len(player_identities_list),
        player_identity_provenance_count=len(player_identity_provenance_list),
        player_tenure_count=len(tenures_list),
        asset_count=len(assets_list),
        asset_provenance_count=len(asset_provenance_list),
        asset_state_count=len(asset_states_list),
        asset_state_provenance_count=len(asset_state_provenance_list),
        errors=errors,
        warnings=warnings,
    )


validate_canonical_player_tenure_rows = validate_canonical_player_tenures
validate_player_tenures = validate_canonical_player_tenures
