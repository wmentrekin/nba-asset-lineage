from __future__ import annotations

from datetime import date, datetime

from canonical.models import (
    AssetProvenance,
    AssetState,
    AssetStateProvenance,
    CanonicalAsset,
    CanonicalPlayerIdentity,
    CanonicalPlayerTenure,
    PlayerIdentityProvenance,
)
from canonical.validate_player_tenure import validate_canonical_player_tenures


def _player(player_id: str) -> CanonicalPlayerIdentity:
    now = datetime(2026, 4, 16, 12, 0, 0)
    return CanonicalPlayerIdentity(
        player_id=player_id,
        display_name="John Doe",
        normalized_name="john doe",
        nba_person_id=None,
        created_at=now,
        updated_at=now,
    )


def _tenure(player_id: str, tenure_id: str, start: str, end: str | None) -> CanonicalPlayerTenure:
    now = datetime(2026, 4, 16, 12, 0, 0)
    return CanonicalPlayerTenure(
        player_tenure_id=tenure_id,
        player_id=player_id,
        tenure_start_date=date.fromisoformat(start),
        tenure_end_date=date.fromisoformat(end) if end else None,
        entry_event_id=f"entry_{tenure_id}",
        exit_event_id=f"exit_{tenure_id}" if end else None,
        tenure_type="signing",
        roster_path_type="free_agency",
        created_at=now,
        updated_at=now,
    )


def _asset(asset_id: str, tenure_id: str) -> CanonicalAsset:
    now = datetime(2026, 4, 16, 12, 0, 0)
    return CanonicalAsset(
        asset_id=asset_id,
        asset_kind="player_tenure",
        player_tenure_id=tenure_id,
        pick_asset_id=None,
        asset_label="John Doe Memphis tenure 1",
        created_at=now,
        updated_at=now,
    )


def _asset_provs(asset_id: str, tenure_id: str) -> list[AssetProvenance]:
    now = datetime(2026, 4, 16, 12, 0, 0)
    return [
        AssetProvenance(
            asset_provenance_id=f"prov_{asset_id}_identity",
            asset_id=asset_id,
            player_tenure_id=tenure_id,
            pick_asset_id=None,
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="asset_identity_support",
            fallback_reason=None,
            created_at=now,
        ),
        AssetProvenance(
            asset_provenance_id=f"prov_{asset_id}_player",
            asset_id=asset_id,
            player_tenure_id=tenure_id,
            pick_asset_id=None,
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="player_identity_resolution_support",
            fallback_reason=None,
            created_at=now,
        ),
    ]


def test_validate_canonical_player_tenures_accepts_non_overlapping_tenures():
    player = _player("player_john_doe")
    tenures = [_tenure("player_john_doe", "tenure_1", "2024-02-08", "2024-02-20"), _tenure("player_john_doe", "tenure_2", "2024-03-01", None)]
    assets = [_asset("asset_1", "tenure_1"), _asset("asset_2", "tenure_2")]
    player_provenance = [
        PlayerIdentityProvenance(
            player_identity_provenance_id="pip_1",
            player_id=player.player_id,
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="player_identity_resolution_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]
    asset_provenance = _asset_provs("asset_1", "tenure_1") + _asset_provs("asset_2", "tenure_2")
    states = [
        AssetState(
            asset_state_id="state_1",
            asset_id="asset_1",
            state_type="player_contract_interval",
            effective_start_date=date.fromisoformat("2024-02-08"),
            effective_end_date=date.fromisoformat("2024-02-18"),
            state_payload={"contract_type": "10-day"},
            source_event_id="entry_tenure_1",
            created_at=datetime(2026, 4, 16, 12, 0, 0),
            updated_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]
    state_provenance = [
        AssetStateProvenance(
            asset_state_provenance_id="asp_1",
            asset_state_id="state_1",
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="asset_state_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]

    report = validate_canonical_player_tenures(
        player_identities=[player],
        player_identity_provenance_rows=player_provenance,
        player_tenures=tenures,
        assets=assets,
        asset_provenance_rows=asset_provenance,
        asset_states=states,
        asset_state_provenance_rows=state_provenance,
    )
    assert report.ok
    assert report.errors == []


def test_validate_canonical_player_tenures_accepts_same_day_exit_and_reentry():
    player = _player("player_john_doe")
    tenures = [_tenure("player_john_doe", "tenure_1", "2024-02-08", "2024-03-01"), _tenure("player_john_doe", "tenure_2", "2024-03-01", None)]
    assets = [_asset("asset_1", "tenure_1"), _asset("asset_2", "tenure_2")]
    player_provenance = [
        PlayerIdentityProvenance(
            player_identity_provenance_id="pip_1",
            player_id=player.player_id,
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="player_identity_resolution_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]
    asset_provenance = _asset_provs("asset_1", "tenure_1") + _asset_provs("asset_2", "tenure_2")

    report = validate_canonical_player_tenures(
        player_identities=[player],
        player_identity_provenance_rows=player_provenance,
        player_tenures=tenures,
        assets=assets,
        asset_provenance_rows=asset_provenance,
        asset_states=[],
        asset_state_provenance_rows=[],
    )
    assert report.ok
    assert report.errors == []


def test_validate_canonical_player_tenures_flags_closed_tenure_without_exit_event():
    player = _player("player_john_doe")
    tenures = [_tenure("player_john_doe", "tenure_1", "2024-02-08", "2024-02-20")]
    tenures[0] = CanonicalPlayerTenure(
        player_tenure_id="tenure_1",
        player_id="player_john_doe",
        tenure_start_date=date.fromisoformat("2024-02-08"),
        tenure_end_date=date.fromisoformat("2024-02-20"),
        entry_event_id="entry_tenure_1",
        exit_event_id=None,
        tenure_type="signing",
        roster_path_type="free_agency",
        created_at=datetime(2026, 4, 16, 12, 0, 0),
        updated_at=datetime(2026, 4, 16, 12, 0, 0),
    )
    assets = [_asset("asset_1", "tenure_1")]
    player_provenance = [
        PlayerIdentityProvenance(
            player_identity_provenance_id="pip_1",
            player_id=player.player_id,
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="player_identity_resolution_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]
    asset_provenance = _asset_provs("asset_1", "tenure_1")

    report = validate_canonical_player_tenures(
        player_identities=[player],
        player_identity_provenance_rows=player_provenance,
        player_tenures=tenures,
        assets=assets,
        asset_provenance_rows=asset_provenance,
        asset_states=[],
        asset_state_provenance_rows=[],
    )
    assert not report.ok
    assert any("missing exit_event_id" in error for error in report.errors)


def test_validate_canonical_player_tenures_flags_player_tenure_asset_subtype_mismatch():
    player = _player("player_john_doe")
    tenures = [_tenure("player_john_doe", "tenure_1", "2024-02-08", None)]
    assets = [
        CanonicalAsset(
            asset_id="asset_1",
            asset_kind="pick_continuity",
            player_tenure_id="tenure_1",
            pick_asset_id="pick_1",
            asset_label="John Doe Memphis tenure 1",
            created_at=datetime(2026, 4, 16, 12, 0, 0),
            updated_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]
    player_provenance = [
        PlayerIdentityProvenance(
            player_identity_provenance_id="pip_1",
            player_id=player.player_id,
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="player_identity_resolution_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]
    asset_provenance = [
        AssetProvenance(
            asset_provenance_id="prov_asset_1_identity",
            asset_id="asset_1",
            player_tenure_id="tenure_1",
            pick_asset_id="pick_1",
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="asset_identity_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        ),
        AssetProvenance(
            asset_provenance_id="prov_asset_1_player",
            asset_id="asset_1",
            player_tenure_id="tenure_1",
            pick_asset_id="pick_1",
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="player_identity_resolution_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        ),
    ]

    report = validate_canonical_player_tenures(
        player_identities=[player],
        player_identity_provenance_rows=player_provenance,
        player_tenures=tenures,
        assets=assets,
        asset_provenance_rows=asset_provenance,
        asset_states=[],
        asset_state_provenance_rows=[],
    )
    assert not report.ok
    assert any("unexpected asset_kind" in error for error in report.errors)
    assert any("pick_asset_id" in error for error in report.errors)


def test_validate_canonical_player_tenures_flags_asset_for_unknown_tenure():
    player = _player("player_john_doe")
    tenures = [_tenure("player_john_doe", "tenure_1", "2024-02-08", None)]
    assets = [_asset("asset_1", "tenure_1"), _asset("asset_2", "tenure_2")]
    player_provenance = [
        PlayerIdentityProvenance(
            player_identity_provenance_id="pip_1",
            player_id=player.player_id,
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="player_identity_resolution_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]
    asset_provenance = _asset_provs("asset_1", "tenure_1") + _asset_provs("asset_2", "tenure_2")

    report = validate_canonical_player_tenures(
        player_identities=[player],
        player_identity_provenance_rows=player_provenance,
        player_tenures=tenures,
        assets=assets,
        asset_provenance_rows=asset_provenance,
        asset_states=[],
        asset_state_provenance_rows=[],
    )
    assert not report.ok
    assert any("unknown player_tenure_id" in error for error in report.errors)


def test_validate_canonical_player_tenures_flags_player_tenure_id_conflation():
    player = _player("player_john_doe")
    tenures = [_tenure("player_john_doe", "player_john_doe", "2024-02-08", None)]
    assets = [_asset("asset_1", "player_john_doe")]
    player_provenance = [
        PlayerIdentityProvenance(
            player_identity_provenance_id="pip_1",
            player_id=player.player_id,
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="player_identity_resolution_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]
    asset_provenance = _asset_provs("asset_1", "player_john_doe")

    report = validate_canonical_player_tenures(
        player_identities=[player],
        player_identity_provenance_rows=player_provenance,
        player_tenures=tenures,
        assets=assets,
        asset_provenance_rows=asset_provenance,
        asset_states=[],
        asset_state_provenance_rows=[],
    )
    assert not report.ok
    assert any("conflates with player_id" in error for error in report.errors)


def test_validate_canonical_player_tenures_flags_overlapping_tenures():
    player = _player("player_john_doe")
    tenures = [_tenure("player_john_doe", "tenure_1", "2024-02-08", "2024-02-20"), _tenure("player_john_doe", "tenure_2", "2024-02-18", None)]
    assets = [_asset("asset_1", "tenure_1"), _asset("asset_2", "tenure_2")]
    player_provenance = [
        PlayerIdentityProvenance(
            player_identity_provenance_id="pip_1",
            player_id=player.player_id,
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="player_identity_resolution_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]
    asset_provenance = _asset_provs("asset_1", "tenure_1") + _asset_provs("asset_2", "tenure_2")

    report = validate_canonical_player_tenures(
        player_identities=[player],
        player_identity_provenance_rows=player_provenance,
        player_tenures=tenures,
        assets=assets,
        asset_provenance_rows=asset_provenance,
        asset_states=[],
        asset_state_provenance_rows=[],
    )
    assert not report.ok
    assert any("overlapping tenures" in error for error in report.errors)


def test_validate_canonical_player_tenures_flags_open_tenure_before_later_tenure():
    player = _player("player_john_doe")
    tenures = [_tenure("player_john_doe", "tenure_1", "2024-02-08", None), _tenure("player_john_doe", "tenure_2", "2024-03-01", None)]
    assets = [_asset("asset_1", "tenure_1"), _asset("asset_2", "tenure_2")]
    player_provenance = [
        PlayerIdentityProvenance(
            player_identity_provenance_id="pip_1",
            player_id=player.player_id,
            source_record_id="source_1",
            claim_id="claim_1",
            override_id=None,
            provenance_role="player_identity_resolution_support",
            fallback_reason=None,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
        )
    ]
    asset_provenance = _asset_provs("asset_1", "tenure_1") + _asset_provs("asset_2", "tenure_2")

    report = validate_canonical_player_tenures(
        player_identities=[player],
        player_identity_provenance_rows=player_provenance,
        player_tenures=tenures,
        assets=assets,
        asset_provenance_rows=asset_provenance,
        asset_states=[],
        asset_state_provenance_rows=[],
    )
    assert not report.ok
    assert any("overlapping tenures" in error for error in report.errors)
