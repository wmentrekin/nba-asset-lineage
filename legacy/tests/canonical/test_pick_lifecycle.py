from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from canonical.models import CanonicalEvent, CanonicalPickResolution, CanonicalPlayerIdentity, EventProvenance
from canonical.pick_lifecycle import build_pick_lifecycle
from canonical.validate_pick_lifecycle import validate_canonical_pick_lifecycle
from evidence.models import NormalizedClaim


def _event(event_id: str, event_type: str, event_date: str, order: int, description: str, source_record_id: str) -> CanonicalEvent:
    now = datetime(2026, 4, 16, 12, 0, 0)
    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        event_date=datetime.fromisoformat(f"{event_date}T00:00:00").date(),
        event_order=order,
        event_label=description,
        description=description,
        transaction_group_key=source_record_id,
        is_compound=False,
        notes=None,
        created_at=now,
        updated_at=now,
    )


def _event_provenance(event_id: str, source_record_id: str, claim_id: str, role: str = "event_date_support") -> EventProvenance:
    return EventProvenance(
        event_provenance_id=f"prov_{event_id}_{claim_id}",
        event_id=event_id,
        source_record_id=source_record_id,
        claim_id=claim_id,
        override_id=None,
        provenance_role=role,
        fallback_reason=None,
        created_at=datetime(2026, 4, 16, 12, 0, 0),
    )


def _claim(
    claim_id: str,
    source_record_id: str,
    claim_type: str,
    subject_type: str,
    subject_key: str,
    payload: dict[str, object],
    *,
    claim_group_hint: str,
    claim_date: str,
    source_sequence: int,
) -> NormalizedClaim:
    return NormalizedClaim(
        claim_id=claim_id,
        source_record_id=source_record_id,
        claim_type=claim_type,
        claim_subject_type=subject_type,
        claim_subject_key=subject_key,
        claim_group_hint=claim_group_hint,
        claim_date=datetime.fromisoformat(f"{claim_date}T00:00:00").date(),
        source_sequence=source_sequence,
        claim_payload=payload,
        confidence_flag="high",
        normalizer_version="test-normalizer-v1",
        created_at=datetime(2026, 4, 16, 12, 0, 0),
    )


def _player_identity(player_id: str) -> CanonicalPlayerIdentity:
    now = datetime(2026, 4, 16, 12, 0, 0)
    return CanonicalPlayerIdentity(
        player_id=player_id,
        display_name="GG Jackson",
        normalized_name="gg jackson",
        nba_person_id=None,
        created_at=now,
        updated_at=now,
    )


def _draft_claims(source_record_id: str, group_hint: str) -> list[NormalizedClaim]:
    return [
        _claim(
            "pick_1_identity",
            source_record_id,
            "pick_identity",
            "pick",
            "pick_2023_mem_2_45",
            {"pick_identity": "pick_2023_mem_2_45"},
            claim_group_hint=group_hint,
            claim_date="2023-06-22",
            source_sequence=1,
        ),
        _claim(
            "pick_1_origin",
            source_record_id,
            "pick_origin_team",
            "pick",
            "pick_2023_mem_2_45",
            {"origin_team": "mem"},
            claim_group_hint=group_hint,
            claim_date="2023-06-22",
            source_sequence=1,
        ),
        _claim(
            "pick_1_year",
            source_record_id,
            "pick_draft_year",
            "pick",
            "pick_2023_mem_2_45",
            {"draft_year": 2023},
            claim_group_hint=group_hint,
            claim_date="2023-06-22",
            source_sequence=1,
        ),
        _claim(
            "pick_1_round",
            source_record_id,
            "pick_round",
            "pick",
            "pick_2023_mem_2_45",
            {"round_number": 2},
            claim_group_hint=group_hint,
            claim_date="2023-06-22",
            source_sequence=1,
        ),
        _claim(
            "pick_1_resolution",
            source_record_id,
            "pick_resolution_metadata",
            "pick",
            "pick_2023_mem_2_45",
            {"overall_pick": 45, "draft_type": "draft", "organization": "nba_api"},
            claim_group_hint=group_hint,
            claim_date="2023-06-22",
            source_sequence=1,
        ),
        _claim(
            "pick_1_player",
            source_record_id,
            "player_identity",
            "player",
            "player::player_gg_jackson",
            {"player_identity": "player_gg_jackson"},
            claim_group_hint=group_hint,
            claim_date="2023-06-22",
            source_sequence=1,
        ),
        _claim(
            "pick_1_player_name",
            source_record_id,
            "player_name",
            "player",
            "player::player_gg_jackson",
            {"player_name": "GG Jackson"},
            claim_group_hint=group_hint,
            claim_date="2023-06-22",
            source_sequence=1,
        ),
    ]


def _future_pick_claims(source_record_id: str, group_hint: str) -> list[NormalizedClaim]:
    return [
        _claim(
            "pick_2_identity",
            source_record_id,
            "pick_identity",
            "pick",
            "pick::2024::mem::1",
            {"pick_identity": "pick::2024::mem::1"},
            claim_group_hint=group_hint,
            claim_date="2024-02-08",
            source_sequence=1,
        ),
        _claim(
            "pick_2_origin",
            source_record_id,
            "pick_origin_team",
            "pick",
            "pick::2024::mem::1",
            {"origin_team": "mem"},
            claim_group_hint=group_hint,
            claim_date="2024-02-08",
            source_sequence=1,
        ),
        _claim(
            "pick_2_year",
            source_record_id,
            "pick_draft_year",
            "pick",
            "pick::2024::mem::1",
            {"draft_year": 2024},
            claim_group_hint=group_hint,
            claim_date="2024-02-08",
            source_sequence=1,
        ),
        _claim(
            "pick_2_round",
            source_record_id,
            "pick_round",
            "pick",
            "pick::2024::mem::1",
            {"round_number": 1},
            claim_group_hint=group_hint,
            claim_date="2024-02-08",
            source_sequence=1,
        ),
        _claim(
            "pick_2_protection",
            source_record_id,
            "pick_protection_metadata",
            "pick",
            "pick::2024::mem::1",
            {"protection_summary": "top-4 protected", "protection_payload": {"top_protected": 4}},
            claim_group_hint=group_hint,
            claim_date="2024-02-08",
            source_sequence=1,
        ),
    ]


def test_build_pick_lifecycle_is_deterministic_and_persists_continuity():
    events = [_event("event_draft", "draft", "2023-06-22", 1, "Memphis drafts GG Jackson", "source_draft")]
    event_provenance = [_event_provenance("event_draft", "source_draft", "claim_draft_event")]
    claims = _draft_claims("source_draft", "draft::2023-06-22::gg")
    result_first = build_pick_lifecycle(events, event_provenance, claims, [], built_at=datetime(2026, 4, 16, 12, 0, 0))
    result_second = build_pick_lifecycle(events, event_provenance, claims, [], built_at=datetime(2026, 4, 16, 12, 0, 0))

    assert result_first.build.canonical_build_id == result_second.build.canonical_build_id
    assert [row.pick_asset_id for row in result_first.pick_assets] == [row.pick_asset_id for row in result_second.pick_assets]
    assert len(result_first.pick_assets) == 1
    assert len(result_first.assets) == 1
    assert result_first.assets[0].asset_kind == "pick_continuity"
    assert result_first.assets[0].pick_asset_id == result_first.pick_assets[0].pick_asset_id
    assert result_first.pick_assets[0].current_pick_stage == "drafted_player"
    assert result_first.pick_assets[0].drafted_player_id == "player_gg_jackson"
    assert any(row.provenance_role == "pick_identity_support" for row in result_first.pick_asset_provenance_rows)
    assert any(row.provenance_role == "drafted_player_linkage_support" for row in result_first.pick_asset_provenance_rows)
    assert any(row.provenance_role == "asset_identity_support" for row in result_first.asset_provenance_rows)
    assert any(row.state_type == "resolved_pick" for row in result_first.pick_resolutions)
    assert any(row.state_type == "drafted_player" for row in result_first.pick_resolutions)

    player = _player_identity("player_gg_jackson")
    report = validate_canonical_pick_lifecycle(
        player_identities=[player],
        pick_assets=result_first.pick_assets,
        pick_asset_provenance_rows=result_first.pick_asset_provenance_rows,
        pick_resolutions=result_first.pick_resolutions,
        pick_resolution_provenance_rows=result_first.pick_resolution_provenance_rows,
        assets=result_first.assets,
        asset_provenance_rows=result_first.asset_provenance_rows,
        events=events,
    )
    assert report.ok


def test_build_pick_lifecycle_supports_future_pick_and_conveyed_away_exit():
    events = [_event("event_trade", "trade", "2024-02-08", 1, "Memphis trades future pick to Orlando", "source_trade")]
    event_provenance = [_event_provenance("event_trade", "source_trade", "claim_trade_event")]
    claims = _future_pick_claims("source_trade", "trade::2024-02-08::pick")
    result = build_pick_lifecycle(events, event_provenance, claims, [], built_at=datetime(2026, 4, 16, 12, 0, 0))

    assert len(result.pick_assets) == 1
    assert result.pick_assets[0].current_pick_stage == "conveyed_away"
    assert result.pick_assets[0].drafted_player_id is None
    assert any(row.state_type == "future_pick" for row in result.pick_resolutions)
    assert any(row.state_type == "conveyed_away" for row in result.pick_resolutions)

    report = validate_canonical_pick_lifecycle(
        pick_assets=result.pick_assets,
        pick_asset_provenance_rows=result.pick_asset_provenance_rows,
        pick_resolutions=result.pick_resolutions,
        pick_resolution_provenance_rows=result.pick_resolution_provenance_rows,
        assets=result.assets,
        asset_provenance_rows=result.asset_provenance_rows,
        events=events,
    )
    assert report.ok


def test_validate_pick_lifecycle_flags_out_of_order_state_dates():
    events = [_event("event_draft", "draft", "2023-06-22", 1, "Memphis drafts GG Jackson", "source_draft")]
    event_provenance = [_event_provenance("event_draft", "source_draft", "claim_draft_event")]
    claims = _draft_claims("source_draft", "draft::2023-06-22::gg")
    result = build_pick_lifecycle(events, event_provenance, claims, [], built_at=datetime(2026, 4, 16, 12, 0, 0))

    bad_resolutions = list(result.pick_resolutions)
    bad_resolutions[0] = replace(bad_resolutions[0], effective_end_date=datetime(2023, 1, 1).date())

    report = validate_canonical_pick_lifecycle(
        pick_assets=result.pick_assets,
        pick_asset_provenance_rows=result.pick_asset_provenance_rows,
        pick_resolutions=bad_resolutions,
        pick_resolution_provenance_rows=result.pick_resolution_provenance_rows,
        assets=result.assets,
        asset_provenance_rows=result.asset_provenance_rows,
        events=events,
    )
    assert not report.ok
    assert any("pick state ends before it starts" in error or "overlapping pick states" in error for error in report.errors)
