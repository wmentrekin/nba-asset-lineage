from __future__ import annotations

from datetime import datetime

from canonical.models import CanonicalEvent, EventProvenance
from canonical.player_tenure import build_player_tenures
from evidence.models import NormalizedClaim


def _event(event_id: str, event_type: str, event_date: str, order: int, description: str) -> CanonicalEvent:
    now = datetime(2026, 4, 16, 12, 0, 0)
    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        event_date=datetime.fromisoformat(f"{event_date}T00:00:00").date(),
        event_order=order,
        event_label=description,
        description=description,
        transaction_group_key=event_id,
        is_compound=False,
        notes=None,
        created_at=now,
        updated_at=now,
    )


def _event_provenance(event_id: str, source_record_id: str, claim_id: str) -> EventProvenance:
    return EventProvenance(
        event_provenance_id=f"prov_{event_id}_{claim_id}",
        event_id=event_id,
        source_record_id=source_record_id,
        claim_id=claim_id,
        override_id=None,
        provenance_role="event_date_support",
        fallback_reason=None,
        created_at=datetime(2026, 4, 16, 12, 0, 0),
    )


def _claim(
    claim_id: str,
    source_record_id: str,
    claim_type: str,
    subject_key: str,
    payload: dict[str, object],
    *,
    claim_date: str | None = None,
    source_sequence: int | None = None,
) -> NormalizedClaim:
    return NormalizedClaim(
        claim_id=claim_id,
        source_record_id=source_record_id,
        claim_type=claim_type,
        claim_subject_type="player",
        claim_subject_key=subject_key,
        claim_group_hint=source_record_id,
        claim_date=datetime.fromisoformat(f"{claim_date}T00:00:00").date() if claim_date else None,
        source_sequence=source_sequence,
        claim_payload=payload,
        confidence_flag="high",
        normalizer_version="test-normalizer-v1",
        created_at=datetime(2026, 4, 16, 12, 0, 0),
    )


def test_build_player_tenures_creates_distinct_chapters_and_assets():
    events = [
        _event("event_sign_1", "signing", "2024-02-08", 1, "Memphis signs John Doe"),
        _event("event_waive", "waiver", "2024-02-20", 1, "Memphis waives John Doe"),
        _event("event_sign_2", "signing", "2024-03-01", 1, "Memphis signs John Doe again"),
    ]
    event_provenance = [
        _event_provenance("event_sign_1", "source_sign_1", "claim_sign_1"),
        _event_provenance("event_waive", "source_waive", "claim_waive_1"),
        _event_provenance("event_sign_2", "source_sign_2", "claim_sign_2"),
    ]
    claims = [
        _claim("claim_sign_1", "source_sign_1", "player_identity", "player::player_john_doe", {"player_identity": "player_john_doe"}, claim_date="2024-02-08", source_sequence=1),
        _claim("claim_sign_1_name", "source_sign_1", "player_name", "player::player_john_doe", {"player_name": "John Doe"}, claim_date="2024-02-08", source_sequence=1),
        _claim(
            "claim_sign_1_contract",
            "source_sign_1",
            "contract_metadata",
            "player::player_john_doe",
            {"start_date": "2024-02-08", "end_date": "2024-02-18", "contract_type": "10-day"},
            claim_date="2024-02-08",
            source_sequence=1,
        ),
        _claim("claim_waive_1", "source_waive", "player_identity", "player::player_john_doe", {"player_identity": "player_john_doe"}, claim_date="2024-02-20", source_sequence=2),
        _claim("claim_waive_1_name", "source_waive", "player_name", "player::player_john_doe", {"player_name": "John Doe"}, claim_date="2024-02-20", source_sequence=2),
        _claim("claim_sign_2", "source_sign_2", "player_identity", "player::player_john_doe", {"player_identity": "player_john_doe"}, claim_date="2024-03-01", source_sequence=3),
        _claim("claim_sign_2_name", "source_sign_2", "player_name", "player::player_john_doe", {"player_name": "John Doe"}, claim_date="2024-03-01", source_sequence=3),
    ]

    result_first = build_player_tenures(events, event_provenance, claims, [], built_at=datetime(2026, 4, 16, 12, 0, 0))
    result_second = build_player_tenures(events, event_provenance, claims, [], built_at=datetime(2026, 4, 16, 12, 0, 0))

    assert [tenure.player_tenure_id for tenure in result_first.player_tenures] == [
        tenure.player_tenure_id for tenure in result_second.player_tenures
    ]
    assert len(result_first.player_tenures) == 2
    assert {tenure.player_id for tenure in result_first.player_tenures} == {"player_john_doe"}
    assert all(tenure.player_tenure_id != tenure.player_id for tenure in result_first.player_tenures)

    first_tenure, second_tenure = result_first.player_tenures
    assert first_tenure.tenure_start_date.isoformat() == "2024-02-08"
    assert first_tenure.tenure_end_date.isoformat() == "2024-02-20"
    assert second_tenure.tenure_start_date.isoformat() == "2024-03-01"
    assert second_tenure.tenure_end_date is None

    assert len(result_first.assets) == 2
    assert all(asset.asset_kind == "player_tenure" for asset in result_first.assets)
    assert len(result_first.player_identities) == 1
    assert result_first.player_identities[0].player_id == "player_john_doe"
    assert any(row.provenance_role == "player_identity_resolution_support" for row in result_first.player_identity_provenance_rows)
    assert any(row.provenance_role == "asset_identity_support" for row in result_first.asset_provenance_rows)
    assert any(state.state_type == "player_contract_interval" for state in result_first.asset_states)
    assert any(row.provenance_role == "asset_state_support" for row in result_first.asset_state_provenance_rows)


def test_build_player_tenures_preserves_identity_separation_for_draft_player():
    events = [_event("event_draft", "draft", "2023-06-22", 1, "Memphis drafts GG Jackson")]
    event_provenance = [_event_provenance("event_draft", "source_draft", "claim_draft_1")]
    claims = [
        _claim("claim_draft_1", "source_draft", "player_identity", "player::player_gg_jackson", {"player_identity": "player_gg_jackson"}, claim_date="2023-06-22", source_sequence=1),
        _claim("claim_draft_1_name", "source_draft", "player_name", "player::player_gg_jackson", {"player_name": "GG Jackson"}, claim_date="2023-06-22", source_sequence=1),
    ]

    result = build_player_tenures(events, event_provenance, claims, [], built_at=datetime(2026, 4, 16, 12, 0, 0))

    assert len(result.player_tenures) == 1
    assert result.player_tenures[0].tenure_type == "draft"
    assert result.player_identities[0].player_id == "player_gg_jackson"
    assert result.assets[0].asset_id != result.player_identities[0].player_id
