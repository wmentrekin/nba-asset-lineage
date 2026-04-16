from __future__ import annotations

from datetime import date, datetime
from typing import Any

from evidence.models import NormalizedClaim, SourceRecord
from shared.ids import stable_id


def normalize_name(value: str) -> str:
    cleaned = " ".join(value.strip().lower().split())
    return "".join(character for character in cleaned if character.isalnum() or character == " ")


def _parse_iso_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _player_subject_key(payload: dict[str, Any]) -> str:
    player_id = str(payload.get("player_id") or payload.get("PERSON_ID") or "").strip()
    if player_id:
        return f"player::{player_id}"
    player_name = str(payload.get("player_name") or payload.get("PLAYER_NAME") or "").strip()
    return f"player_name::{normalize_name(player_name)}"


def _spotrac_transaction_event_key(payload: dict[str, Any]) -> str:
    return (
        f"spotrac_tx::{payload.get('player_id', 'unknown')}::"
        f"{payload.get('event_date', 'unknown')}::{payload.get('description_hash', 'unknown')}"
    )


def _spotrac_contract_subject_key(payload: dict[str, Any]) -> str:
    return (
        f"spotrac_contract::{payload.get('player_id', 'unknown')}::"
        f"{payload.get('start_year', 'unknown')}::{payload.get('end_year', 'unknown')}"
    )


def _nba_draft_event_key(payload: dict[str, Any]) -> str:
    return (
        f"nba_api_draft::{payload.get('SEASON', 'unknown')}::{payload.get('ROUND_NUMBER', 'unknown')}::"
        f"{payload.get('OVERALL_PICK', 'unknown')}::{payload.get('TEAM_ABBREVIATION', 'unknown')}"
    )


def _pick_subject_key(payload: dict[str, Any]) -> str:
    draft_year = payload.get("draft_year") or payload.get("SEASON") or "unknown"
    origin_team = payload.get("origin_team") or payload.get("TEAM_ABBREVIATION") or "unknown"
    round_number = payload.get("round_number") or payload.get("ROUND_NUMBER") or "unknown"
    return f"pick::{draft_year}::{origin_team}::{round_number}"


def _build_claim(
    *,
    source_record: SourceRecord,
    claim_type: str,
    subject_type: str,
    subject_key: str,
    claim_group_hint: str | None,
    claim_date: date | None,
    source_sequence: int | None,
    claim_payload: dict[str, Any],
    confidence_flag: str,
    normalizer_version: str,
    created_at: datetime,
) -> NormalizedClaim:
    claim_id = stable_id(
        "claim",
        source_record.source_record_id,
        claim_type,
        subject_type,
        subject_key,
        source_sequence,
        claim_payload,
    )
    return NormalizedClaim(
        claim_id=claim_id,
        source_record_id=source_record.source_record_id,
        claim_type=claim_type,
        claim_subject_type=subject_type,
        claim_subject_key=subject_key,
        claim_group_hint=claim_group_hint,
        claim_date=claim_date,
        source_sequence=source_sequence,
        claim_payload=claim_payload,
        confidence_flag=confidence_flag,
        normalizer_version=normalizer_version,
        created_at=created_at,
    )


def normalize_source_record(
    source_record: SourceRecord,
    *,
    normalizer_version: str = "stage1-normalizer-v1",
    created_at: datetime | None = None,
) -> list[NormalizedClaim]:
    created_at_value = created_at or datetime.utcnow()
    payload = source_record.raw_payload
    claims: list[NormalizedClaim] = []
    source_sequence = payload.get("source_sequence")

    if source_record.source_type in {"spotrac_transaction", "transaction"}:
        if payload.get("source_event_ref"):
            claim_date = _parse_iso_date(payload.get("event_date"))
            event_key = str(payload["source_event_ref"])
            player_key = str(payload.get("player_identity") or _player_subject_key(payload))
            claim_group_hint = event_key
            claims.extend(
                [
                    _build_claim(
                        source_record=source_record,
                        claim_type="event_date",
                        subject_type="event",
                        subject_key=event_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"event_date": payload.get("event_date")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="event_type",
                        subject_type="event",
                        subject_key=event_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"event_type": payload.get("event_type")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="event_description",
                        subject_type="event",
                        subject_key=event_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"description": payload.get("event_description")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="player_identity",
                        subject_type="player",
                        subject_key=player_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"player_identity": payload.get("player_identity")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="player_name",
                        subject_type="player",
                        subject_key=player_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"player_name": payload.get("player_name")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="transaction_counterparty",
                        subject_type="event",
                        subject_key=event_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"transaction_counterparty": payload.get("transaction_counterparty")},
                        confidence_flag="medium",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                ]
            )
            return claims

        claim_date = _parse_iso_date(payload.get("event_date"))
        event_key = _spotrac_transaction_event_key(payload)
        player_key = _player_subject_key(payload)
        claim_group_hint = event_key
        description = str(payload.get("description") or "")
        counterparty = payload.get("counterparty_team")

        claims.extend(
            [
                _build_claim(
                    source_record=source_record,
                    claim_type="event_date",
                    subject_type="event",
                    subject_key=event_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"event_date": payload.get("event_date")},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="event_type",
                    subject_type="event",
                    subject_key=event_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"event_type": payload.get("event_type")},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="event_description",
                    subject_type="event",
                    subject_key=event_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"description": description},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="player_identity",
                    subject_type="player",
                    subject_key=player_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={
                        "player_id": payload.get("player_id"),
                        "player_href": payload.get("player_href"),
                    },
                    confidence_flag="high" if payload.get("player_id") else "medium",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="player_name",
                    subject_type="player",
                    subject_key=player_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"player_name": payload.get("player_name")},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
            ]
        )

        if counterparty:
            claims.append(
                _build_claim(
                    source_record=source_record,
                    claim_type="transaction_counterparty",
                    subject_type="event",
                    subject_key=event_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"counterparty_team": counterparty},
                    confidence_flag="medium",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                )
            )

        if payload.get("source_sequence") is not None:
            claims.append(
                _build_claim(
                    source_record=source_record,
                    claim_type="event_order_hint",
                    subject_type="event",
                    subject_key=event_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"source_sequence": source_sequence},
                    confidence_flag="medium",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                )
            )

        if payload.get("event_type") in {"signing", "re_signing", "extension"}:
            claims.append(
                _build_claim(
                    source_record=source_record,
                    claim_type="contract_metadata",
                    subject_type="event",
                    subject_key=event_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={
                        "contract_expiry_year": payload.get("contract_expiry_year"),
                        "average_annual_salary": payload.get("average_annual_salary"),
                    },
                    confidence_flag="medium",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                )
            )

        if payload.get("event_type") == "waiver":
            claims.append(
                _build_claim(
                    source_record=source_record,
                    claim_type="waiver_metadata",
                    subject_type="event",
                    subject_key=event_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"description": description},
                    confidence_flag="medium",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                )
            )
            if "buyout" in description.lower():
                claims.append(
                    _build_claim(
                        source_record=source_record,
                        claim_type="buyout_metadata",
                        subject_type="event",
                        subject_key=event_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=source_sequence,
                        claim_payload={"description": description},
                        confidence_flag="medium",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    )
                )

        return claims

    if source_record.source_type in {"spotrac_contract", "contract"}:
        if payload.get("source_event_ref"):
            player_key = str(payload.get("player_identity") or _player_subject_key(payload))
            contract_metadata = payload.get("contract_metadata") or {}
            claim_date = _parse_iso_date(contract_metadata.get("start_date"))
            claim_group_hint = str(payload["source_event_ref"])
            claims.extend(
                [
                    _build_claim(
                        source_record=source_record,
                        claim_type="player_identity",
                        subject_type="player",
                        subject_key=player_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"player_identity": payload.get("player_identity")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="player_name",
                        subject_type="player",
                        subject_key=player_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"player_name": payload.get("player_name")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="contract_metadata",
                        subject_type="player",
                        subject_key=player_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload=contract_metadata,
                        confidence_flag="medium",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                ]
            )
            return claims

        player_key = _player_subject_key(payload)
        claim_group_hint = _spotrac_contract_subject_key(payload)
        start_year = payload.get("start_year")
        claim_date = date(int(start_year), 1, 1) if start_year else None

        claims.extend(
            [
                _build_claim(
                    source_record=source_record,
                    claim_type="player_identity",
                    subject_type="player",
                    subject_key=player_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={
                        "player_id": payload.get("player_id"),
                        "player_href": payload.get("player_href"),
                    },
                    confidence_flag="high" if payload.get("player_id") else "medium",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="player_name",
                    subject_type="player",
                    subject_key=player_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"player_name": payload.get("player_name")},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="contract_metadata",
                    subject_type="player",
                    subject_key=player_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={
                        "position": payload.get("position"),
                        "contract_type": payload.get("contract_type"),
                        "start_year": payload.get("start_year"),
                        "end_year": payload.get("end_year"),
                        "years": payload.get("years"),
                        "value": payload.get("value"),
                        "aav": payload.get("aav"),
                        "gtd_at_sign": payload.get("gtd_at_sign"),
                        "practical_gtd": payload.get("practical_gtd"),
                    },
                    confidence_flag="medium",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
            ]
        )
        return claims

    if source_record.source_type in {"nba_api_draft_history", "draft_history"}:
        if payload.get("source_event_ref"):
            claim_date = _parse_iso_date(payload.get("event_date"))
            event_key = str(payload["source_event_ref"])
            pick_key = str(payload.get("pick_identity") or _pick_subject_key(payload))
            player_key = str(payload.get("player_identity") or _player_subject_key(payload))
            claim_group_hint = event_key
            claims.extend(
                [
                    _build_claim(
                        source_record=source_record,
                        claim_type="event_date",
                        subject_type="event",
                        subject_key=event_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"event_date": payload.get("event_date")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="event_type",
                        subject_type="event",
                        subject_key=event_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"event_type": "draft"},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="pick_identity",
                        subject_type="pick",
                        subject_key=pick_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"pick_identity": payload.get("pick_identity")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="pick_draft_year",
                        subject_type="pick",
                        subject_key=pick_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"pick_draft_year": payload.get("pick_draft_year")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="pick_round",
                        subject_type="pick",
                        subject_key=pick_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"pick_round": payload.get("pick_round")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="player_identity",
                        subject_type="player",
                        subject_key=player_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"player_identity": payload.get("player_identity")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                    _build_claim(
                        source_record=source_record,
                        claim_type="player_name",
                        subject_type="player",
                        subject_key=player_key,
                        claim_group_hint=claim_group_hint,
                        claim_date=claim_date,
                        source_sequence=payload.get("source_sequence"),
                        claim_payload={"player_name": payload.get("player_name")},
                        confidence_flag="high",
                        normalizer_version=normalizer_version,
                        created_at=created_at_value,
                    ),
                ]
            )
            return claims

        claim_date = _parse_iso_date(payload.get("event_date"))
        event_key = _nba_draft_event_key(payload)
        pick_key = _pick_subject_key(payload)
        player_key = _player_subject_key(payload)
        claim_group_hint = (
            f"draft::{payload.get('SEASON', 'unknown')}::{payload.get('TEAM_ABBREVIATION', 'unknown')}::"
            f"{payload.get('OVERALL_PICK', 'unknown')}"
        )

        claims.extend(
            [
                _build_claim(
                    source_record=source_record,
                    claim_type="event_date",
                    subject_type="event",
                    subject_key=event_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"event_date": payload.get("event_date")},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="event_type",
                    subject_type="event",
                    subject_key=event_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"event_type": "draft"},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="player_identity",
                    subject_type="player",
                    subject_key=player_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={
                        "player_id": payload.get("PERSON_ID"),
                        "team_abbreviation": payload.get("TEAM_ABBREVIATION"),
                    },
                    confidence_flag="high" if payload.get("PERSON_ID") else "medium",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="player_name",
                    subject_type="player",
                    subject_key=player_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"player_name": payload.get("PLAYER_NAME")},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="pick_identity",
                    subject_type="pick",
                    subject_key=pick_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={
                        "draft_year": payload.get("SEASON"),
                        "origin_team": payload.get("TEAM_ABBREVIATION"),
                        "round_number": payload.get("ROUND_NUMBER"),
                        "overall_pick": payload.get("OVERALL_PICK"),
                    },
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="pick_origin_team",
                    subject_type="pick",
                    subject_key=pick_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"origin_team": payload.get("TEAM_ABBREVIATION")},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="pick_draft_year",
                    subject_type="pick",
                    subject_key=pick_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"draft_year": payload.get("SEASON")},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="pick_round",
                    subject_type="pick",
                    subject_key=pick_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={"round_number": payload.get("ROUND_NUMBER")},
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
                _build_claim(
                    source_record=source_record,
                    claim_type="pick_resolution_metadata",
                    subject_type="pick",
                    subject_key=pick_key,
                    claim_group_hint=claim_group_hint,
                    claim_date=claim_date,
                    source_sequence=source_sequence,
                    claim_payload={
                        "overall_pick": payload.get("OVERALL_PICK"),
                        "draft_type": payload.get("DRAFT_TYPE"),
                        "organization": payload.get("ORGANIZATION"),
                    },
                    confidence_flag="high",
                    normalizer_version=normalizer_version,
                    created_at=created_at_value,
                ),
            ]
        )
        return claims

    return claims
