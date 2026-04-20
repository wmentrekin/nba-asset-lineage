from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from canonical.models import (
    AssetProvenance,
    CanonicalAsset,
    CanonicalBuild,
    CanonicalEvent,
    CanonicalPickAsset,
    CanonicalPickLifecycleBuildResult,
    CanonicalPickResolution,
    EventProvenance,
    PickAssetProvenance,
    PickResolutionProvenance,
)
from db_config import load_database_url
from evidence.models import NormalizedClaim, OverrideRecord
from shared.ids import stable_id, stable_payload_hash


PICK_RELEVANT_CLAIM_TYPES = {
    "pick_identity",
    "pick_origin_team",
    "pick_draft_year",
    "pick_round",
    "pick_protection_metadata",
    "pick_resolution_metadata",
}

PICK_STAGE_ORDER = {
    "future_pick": 0,
    "resolved_pick": 1,
    "drafted_player": 2,
    "conveyed_away": 3,
}


@dataclass(frozen=True)
class _PickStageCandidate:
    state_type: str
    effective_start_date: date
    effective_end_date: date | None
    overall_pick_number: int | None
    lottery_context: str | None
    drafted_player_id: str | None
    source_event_id: str | None
    support_claims: list[NormalizedClaim]
    support_override: OverrideRecord | None
    state_payload: dict[str, Any]
    fallback_reason: str | None


def bootstrap_canonical_pick_lifecycle_schema(sql_path: Path | str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required to bootstrap canonical pick lifecycle tables.") from exc

    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with psycopg.connect(load_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
        conn.commit()


def _connect():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for canonical pick lifecycle builds.") from exc
    return psycopg.connect(load_database_url())


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _most_common(values: Iterable[Any]) -> Any | None:
    normalized = [value for value in values if value not in {None, ""}]
    if not normalized:
        return None
    counts = Counter(normalized)
    return sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))[0][0]


def _normalize_team_code(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _pick_origin_from_key(pick_key: str) -> str | None:
    if pick_key.startswith("pick::"):
        parts = pick_key.split("::")
        if len(parts) >= 4:
            return _normalize_team_code(parts[2])
    parts = pick_key.split("_")
    if len(parts) >= 5 and parts[0] == "pick":
        return _normalize_team_code(parts[2])
    return None


def _pick_draft_year_from_key(pick_key: str) -> int | None:
    if pick_key.startswith("pick::"):
        parts = pick_key.split("::")
        if len(parts) >= 4:
            return _as_int(parts[1])
    parts = pick_key.split("_")
    if len(parts) >= 5 and parts[0] == "pick":
        return _as_int(parts[1])
    return None


def _pick_round_from_key(pick_key: str) -> int | None:
    if pick_key.startswith("pick::"):
        parts = pick_key.split("::")
        if len(parts) >= 4:
            return _as_int(parts[3])
    parts = pick_key.split("_")
    if len(parts) >= 5 and parts[0] == "pick":
        return _as_int(parts[3])
    return None


def _pick_trade_direction(description: str | None) -> str:
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


def _group_claims_by_source_record(claims: Iterable[NormalizedClaim]) -> dict[str, list[NormalizedClaim]]:
    grouped: dict[str, list[NormalizedClaim]] = defaultdict(list)
    for claim in claims:
        grouped[claim.source_record_id].append(claim)
    for rows in grouped.values():
        rows.sort(key=lambda claim: (claim.source_sequence if claim.source_sequence is not None else 10**9, claim.claim_id))
    return grouped


def _event_source_record_ids(event_provenance: Iterable[EventProvenance]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in event_provenance:
        if row.source_record_id:
            grouped[row.event_id].add(row.source_record_id)
    return grouped


def _events_by_source_record(events: Iterable[CanonicalEvent], event_provenance: Iterable[EventProvenance]) -> dict[str, list[CanonicalEvent]]:
    event_by_id = {event.event_id: event for event in events}
    grouped: dict[str, list[CanonicalEvent]] = defaultdict(list)
    for event_id, source_record_ids in _event_source_record_ids(event_provenance).items():
        event = event_by_id.get(event_id)
        if event is None:
            continue
        for source_record_id in source_record_ids:
            grouped[source_record_id].append(event)
    for rows in grouped.values():
        rows.sort(key=lambda event: (event.event_date, event.event_order, event.event_id))
    return grouped


def _claim_payload(claim: NormalizedClaim) -> dict[str, Any]:
    payload = claim.claim_payload
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _claim_text(claim: NormalizedClaim, *keys: str) -> str | None:
    payload = _claim_payload(claim)
    for key in keys:
        value = payload.get(key)
        if value not in {None, ""}:
            return str(value).strip() or None
    return None


def _pick_identity_claim(pick_claims: list[NormalizedClaim]) -> NormalizedClaim | None:
    for claim in pick_claims:
        if claim.claim_type == "pick_identity":
            return claim
    return pick_claims[0] if pick_claims else None


def _claim_date(claims: Iterable[NormalizedClaim]) -> date | None:
    dates = [claim.claim_date for claim in claims if claim.claim_date is not None]
    return _most_common(dates)


def _related_claims_for_pick(
    pick_claims: list[NormalizedClaim],
    claims_by_group_hint: dict[str, list[NormalizedClaim]],
) -> list[NormalizedClaim]:
    related: dict[str, NormalizedClaim] = {claim.claim_id: claim for claim in pick_claims}
    for hint in sorted({claim.claim_group_hint for claim in pick_claims if claim.claim_group_hint}):
        for claim in claims_by_group_hint.get(hint, []):
            related[claim.claim_id] = claim
    return sorted(related.values(), key=lambda claim: (claim.claim_date or date.min, claim.source_sequence if claim.source_sequence is not None else 10**9, claim.claim_id))


def _most_common_pick_identity(pick_claims: list[NormalizedClaim]) -> str:
    identity_claims = [_claim_text(claim, "pick_identity") for claim in pick_claims if claim.claim_type == "pick_identity"]
    identity = _most_common(identity_claims)
    if identity:
        return str(identity)
    claim = _pick_identity_claim(pick_claims)
    if claim is None:
        raise ValueError("canonical pick build requires at least one pick claim.")
    draft_year = _as_int(_claim_text(claim, "draft_year", "pick_draft_year"))
    origin_team = _normalize_team_code(_claim_text(claim, "origin_team", "pick_origin_team"))
    draft_round = _as_int(_claim_text(claim, "round_number", "pick_round"))
    return stable_id("pick_asset", origin_team or "unknown", draft_year or "unknown", draft_round or "unknown", claim.claim_subject_key)


def _resolution_context(claim: NormalizedClaim | None) -> str | None:
    if claim is None:
        return None
    payload = _claim_payload(claim)
    values = [str(payload.get(key)).strip() for key in ("draft_type", "organization", "lottery_context") if str(payload.get(key) or "").strip()]
    return " | ".join(values) if values else None


def _build_pick_stage_candidates(
    pick_key: str,
    pick_claims: list[NormalizedClaim],
    related_claims: list[NormalizedClaim],
    related_events: list[CanonicalEvent],
    overrides: list[OverrideRecord],
) -> list[_PickStageCandidate]:
    identity_claim = _pick_identity_claim(pick_claims)
    pick_start_claim = min(
        [claim for claim in pick_claims if claim.claim_date is not None],
        key=lambda claim: (claim.claim_date, claim.source_sequence if claim.source_sequence is not None else 10**9, claim.claim_id),
        default=identity_claim,
    )
    if pick_start_claim is None:
        raise ValueError(f"canonical pick build requires claim_date support for {pick_key}.")

    future_start_date = pick_start_claim.claim_date or (related_events[0].event_date if related_events else date.min)
    future_support_claims = [claim for claim in pick_claims if claim.claim_type in {"pick_identity", "pick_origin_team", "pick_draft_year", "pick_round", "pick_protection_metadata"}]
    if not future_support_claims:
        future_support_claims = list(pick_claims)

    stage_candidates: list[_PickStageCandidate] = []
    protection_claims = [claim for claim in pick_claims if claim.claim_type == "pick_protection_metadata"]
    protection_payload = {}
    protection_summary = None
    if protection_claims:
        protection_payload = _claim_payload(protection_claims[0])
        protection_summary = (
            _claim_text(protection_claims[0], "protection_summary", "summary", "language")
            or protection_payload.get("protection_summary")
            or protection_payload.get("summary")
            or protection_payload.get("language")
        )

    future_override = next((override for override in overrides if override.is_active and override.target_key == pick_key and override.target_type in {"pick_asset", "pick_stage"}), None)
    if future_override is not None:
        override_payload = dict(future_override.payload)
        protection_summary = str(override_payload.get("protection_summary") or protection_summary or "").strip() or None
        if isinstance(override_payload.get("protection_payload"), dict):
            protection_payload = dict(override_payload["protection_payload"])

    stage_candidates.append(
        _PickStageCandidate(
            state_type="future_pick",
            effective_start_date=future_start_date,
            effective_end_date=None,
            overall_pick_number=None,
            lottery_context=None,
            drafted_player_id=None,
            source_event_id=related_events[0].event_id if related_events else None,
            support_claims=future_support_claims,
            support_override=future_override,
            state_payload={
                "pick_key": pick_key,
                "current_pick_stage": "future_pick",
                "origin_team_code": _normalize_team_code(_claim_text(identity_claim, "origin_team", "pick_origin_team")) if identity_claim else None,
                "draft_year": _as_int(_claim_text(identity_claim, "draft_year", "pick_draft_year")) if identity_claim else None,
                "draft_round": _as_int(_claim_text(identity_claim, "round_number", "pick_round")) if identity_claim else None,
                "protection_summary": protection_summary,
                "protection_payload": protection_payload,
            },
            fallback_reason="claim_date_support" if pick_start_claim.claim_date is not None else "event_date_support",
        )
    )

    resolution_claims = [claim for claim in pick_claims if claim.claim_type == "pick_resolution_metadata"]
    resolution_claim = resolution_claims[0] if resolution_claims else None
    resolution_event = next((event for event in related_events if event.event_type == "draft"), None)
    if resolution_claim or resolution_event is not None:
        resolution_date = _claim_date(resolution_claims) or (resolution_event.event_date if resolution_event else future_start_date)
        resolution_payload = _claim_payload(resolution_claim) if resolution_claim else {}
        stage_candidates.append(
            _PickStageCandidate(
                state_type="resolved_pick",
                effective_start_date=resolution_date,
                effective_end_date=None,
                overall_pick_number=_as_int(resolution_payload.get("overall_pick")),
                lottery_context=_resolution_context(resolution_claim),
                drafted_player_id=None,
                source_event_id=resolution_event.event_id if resolution_event else (related_events[0].event_id if related_events else None),
                support_claims=resolution_claims or future_support_claims,
                support_override=next((override for override in overrides if override.is_active and override.target_key == pick_key and override.target_type == "pick_resolution"), None),
                state_payload={
                    "pick_key": pick_key,
                    "current_pick_stage": "resolved_pick",
                    "overall_pick_number": _as_int(resolution_payload.get("overall_pick")),
                    "lottery_context": _resolution_context(resolution_claim),
                    "draft_type": resolution_payload.get("draft_type"),
                    "organization": resolution_payload.get("organization"),
                },
                fallback_reason=None if resolution_claim is not None else "draft_event_support",
            )
        )

    player_claims = [claim for claim in related_claims if claim.claim_subject_type == "player"]
    player_identity_claims = [claim for claim in player_claims if claim.claim_type == "player_identity"]
    draft_event = next((event for event in related_events if event.event_type == "draft"), None)
    drafted_player_id = None
    if player_identity_claims:
        drafted_player_id = _most_common(_claim_text(claim, "player_identity", "player_id") for claim in player_identity_claims)
        if drafted_player_id is None:
            drafted_player_id = _most_common((claim.claim_subject_key for claim in player_identity_claims),)
    if draft_event and drafted_player_id:
        draft_player_override = next((override for override in overrides if override.is_active and override.target_key == pick_key and override.target_type in {"pick_asset", "pick_resolution", "drafted_player_link"}), None)
        stage_candidates.append(
            _PickStageCandidate(
                state_type="drafted_player",
                effective_start_date=draft_event.event_date,
                effective_end_date=None,
                overall_pick_number=_as_int(_claim_text(resolution_claim, "overall_pick")) if resolution_claim else None,
                lottery_context=_resolution_context(resolution_claim),
                drafted_player_id=drafted_player_id,
                source_event_id=draft_event.event_id,
                support_claims=player_identity_claims,
                support_override=draft_player_override,
                state_payload={
                    "pick_key": pick_key,
                    "current_pick_stage": "drafted_player",
                    "drafted_player_id": drafted_player_id,
                    "draft_event_id": draft_event.event_id,
                    "draft_event_label": draft_event.event_label,
                },
                fallback_reason=None,
            )
        )

    conveyed_event = next((event for event in related_events if event.event_type == "trade" and _pick_trade_direction(event.description) == "outgoing"), None)
    if conveyed_event is not None:
        convey_override = next((override for override in overrides if override.is_active and override.target_key == pick_key and override.target_type in {"pick_asset", "pick_stage"}), None)
        stage_candidates.append(
            _PickStageCandidate(
                state_type="conveyed_away",
                effective_start_date=conveyed_event.event_date,
                effective_end_date=None,
                overall_pick_number=_as_int(_claim_text(resolution_claim, "overall_pick")) if resolution_claim else None,
                lottery_context=_resolution_context(resolution_claim),
                drafted_player_id=drafted_player_id,
                source_event_id=conveyed_event.event_id,
                support_claims=future_support_claims,
                support_override=convey_override,
                state_payload={
                    "pick_key": pick_key,
                    "current_pick_stage": "conveyed_away",
                    "trade_event_id": conveyed_event.event_id,
                    "trade_event_label": conveyed_event.event_label,
                },
                fallback_reason=None,
            )
        )

    stage_candidates.sort(
        key=lambda candidate: (
            candidate.effective_start_date,
            PICK_STAGE_ORDER[candidate.state_type],
            candidate.source_event_id or "",
        )
    )
    return [
        replace(
            candidate,
            effective_end_date=stage_candidates[index + 1].effective_start_date if index + 1 < len(stage_candidates) else None,
        )
        for index, candidate in enumerate(stage_candidates)
    ]


def build_pick_lifecycle(
    events: Iterable[CanonicalEvent],
    event_provenance: Iterable[EventProvenance],
    claims: Iterable[NormalizedClaim],
    overrides: Iterable[OverrideRecord],
    *,
    builder_version: str = "stage4-pick-lifecycle-v1",
    built_at: datetime | None = None,
) -> CanonicalPickLifecycleBuildResult:
    built_at_value = built_at or datetime.utcnow()
    events_list = sorted(list(events), key=lambda event: (event.event_date, event.event_order, event.event_id))
    event_provenance_list = list(event_provenance)
    claims_list = list(claims)
    overrides_list = list(overrides)
    active_overrides = [override for override in overrides_list if override.is_active]

    claims_by_group_hint: dict[str, list[NormalizedClaim]] = defaultdict(list)
    for claim in claims_list:
        if claim.claim_group_hint:
            claims_by_group_hint[claim.claim_group_hint].append(claim)
    related_events_by_source_record = _events_by_source_record(events_list, event_provenance_list)

    pick_claims_by_key: dict[str, list[NormalizedClaim]] = defaultdict(list)
    for claim in claims_list:
        if claim.claim_subject_type == "pick" and claim.claim_type in PICK_RELEVANT_CLAIM_TYPES:
            pick_claims_by_key[claim.claim_subject_key].append(claim)
    if not pick_claims_by_key:
        raise ValueError("canonical pick build requires at least one pick claim.")

    pick_assets: list[CanonicalPickAsset] = []
    pick_asset_provenance_rows: list[PickAssetProvenance] = []
    pick_resolutions: list[CanonicalPickResolution] = []
    pick_resolution_provenance_rows: list[PickResolutionProvenance] = []
    assets: list[CanonicalAsset] = []
    asset_provenance_rows: list[AssetProvenance] = []

    for pick_key, pick_claims in sorted(pick_claims_by_key.items()):
        related_claims = _related_claims_for_pick(pick_claims, claims_by_group_hint)
        related_source_record_ids = {claim.source_record_id for claim in related_claims}
        related_events: list[CanonicalEvent] = []
        for source_record_id in sorted(related_source_record_ids):
            related_events.extend(related_events_by_source_record.get(source_record_id, []))
        related_events = sorted({event.event_id: event for event in related_events}.values(), key=lambda event: (event.event_date, event.event_order, event.event_id))

        identity_claim = _pick_identity_claim(pick_claims)
        if identity_claim is None:
            continue

        pick_asset_id = _most_common_pick_identity(pick_claims)
        origin_team_code = _normalize_team_code(
            _most_common(
                [
                    _claim_text(claim, "origin_team", "pick_origin_team")
                    for claim in pick_claims
                    if claim.claim_type in {"pick_identity", "pick_origin_team"}
                ]
            )
        )
        if origin_team_code is None:
            origin_team_code = _pick_origin_from_key(pick_key) or "UNK"
        draft_year = _as_int(
            _most_common([_claim_text(claim, "draft_year", "pick_draft_year") for claim in pick_claims if claim.claim_type in {"pick_identity", "pick_draft_year"}])
        ) or _pick_draft_year_from_key(pick_key)
        draft_round = _as_int(
            _most_common([_claim_text(claim, "round_number", "pick_round") for claim in pick_claims if claim.claim_type in {"pick_identity", "pick_round"}])
        ) or _pick_round_from_key(pick_key)
        if draft_year is None or draft_round is None:
            raise ValueError(f"canonical pick build requires draft year and round support for {pick_key}.")

        player_identity_claims = [claim for claim in related_claims if claim.claim_subject_type == "player" and claim.claim_type == "player_identity"]
        drafted_player_id = _most_common(
            [
                _claim_text(claim, "player_identity", "player_id") or claim.claim_subject_key
                for claim in player_identity_claims
            ]
        )

        protection_claims = [claim for claim in pick_claims if claim.claim_type == "pick_protection_metadata"]
        protection_payload = _claim_payload(protection_claims[0]) if protection_claims else {}
        protection_summary = None
        if protection_claims:
            protection_summary = (
                _claim_text(protection_claims[0], "protection_summary", "summary", "language")
                or protection_payload.get("protection_summary")
                or protection_payload.get("summary")
                or protection_payload.get("language")
            )

        stage_candidates = _build_pick_stage_candidates(
            pick_key,
            pick_claims,
            related_claims,
            related_events,
            overrides_list,
        )
        current_stage = stage_candidates[-1].state_type if stage_candidates else "future_pick"
        if stage_candidates and stage_candidates[-1].state_type == "drafted_player":
            drafted_player_id = drafted_player_id or stage_candidates[-1].drafted_player_id

        if stage_candidates and stage_candidates[-1].state_type == "conveyed_away" and stage_candidates[-1].drafted_player_id:
            drafted_player_id = stage_candidates[-1].drafted_player_id

        asset_id = stable_id("asset", pick_asset_id, "pick_continuity")
        pick_assets.append(
            CanonicalPickAsset(
                pick_asset_id=pick_asset_id,
                origin_team_code=origin_team_code,
                draft_year=draft_year,
                draft_round=draft_round,
                protection_summary=protection_summary,
                protection_payload=protection_payload,
                drafted_player_id=drafted_player_id,
                current_pick_stage=current_stage,
                created_at=built_at_value,
                updated_at=built_at_value,
            )
        )
        assets.append(
            CanonicalAsset(
                asset_id=asset_id,
                asset_kind="pick_continuity",
                player_tenure_id=None,
                pick_asset_id=pick_asset_id,
                asset_label=f"{origin_team_code} {draft_year} round {draft_round} pick",
                created_at=built_at_value,
                updated_at=built_at_value,
            )
        )

        identity_support_claim = identity_claim
        pick_asset_provenance_rows.append(
            PickAssetProvenance(
                pick_asset_provenance_id=stable_id(
                    "pick_asset_prov",
                    pick_asset_id,
                    "pick_identity_support",
                    identity_support_claim.claim_id if identity_support_claim else pick_key,
                ),
                pick_asset_id=pick_asset_id,
                source_record_id=identity_support_claim.source_record_id if identity_support_claim else None,
                claim_id=identity_support_claim.claim_id if identity_support_claim else None,
                override_id=None,
                provenance_role="pick_identity_support",
                fallback_reason=None if identity_support_claim else "subject_key_derivation",
                created_at=built_at_value,
            )
        )
        if protection_claims:
            protection_claim = protection_claims[0]
            pick_asset_provenance_rows.append(
                PickAssetProvenance(
                    pick_asset_provenance_id=stable_id("pick_asset_prov", pick_asset_id, "pick_protection_support", protection_claim.claim_id),
                    pick_asset_id=pick_asset_id,
                    source_record_id=protection_claim.source_record_id,
                    claim_id=protection_claim.claim_id,
                    override_id=None,
                    provenance_role="pick_protection_support",
                    fallback_reason=None,
                    created_at=built_at_value,
                )
            )
        if protection_summary is not None or protection_payload:
            pass
        if drafted_player_id is not None:
            drafted_claim = player_identity_claims[0] if player_identity_claims else None
            if drafted_claim is not None:
                pick_asset_provenance_rows.append(
                    PickAssetProvenance(
                        pick_asset_provenance_id=stable_id("pick_asset_prov", pick_asset_id, "drafted_player_linkage_support", drafted_claim.claim_id),
                        pick_asset_id=pick_asset_id,
                        source_record_id=drafted_claim.source_record_id,
                        claim_id=drafted_claim.claim_id,
                        override_id=None,
                        provenance_role="drafted_player_linkage_support",
                        fallback_reason=None,
                        created_at=built_at_value,
                    )
                )

        asset_provenance_rows.append(
            AssetProvenance(
                asset_provenance_id=stable_id("asset_prov", asset_id, "asset_identity_support", identity_support_claim.claim_id if identity_support_claim else pick_key),
                asset_id=asset_id,
                player_tenure_id=None,
                pick_asset_id=pick_asset_id,
                source_record_id=identity_support_claim.source_record_id if identity_support_claim else None,
                claim_id=identity_support_claim.claim_id if identity_support_claim else None,
                override_id=None,
                provenance_role="asset_identity_support",
                fallback_reason=None if identity_support_claim else "subject_key_derivation",
                created_at=built_at_value,
            )
        )
        asset_provenance_rows.append(
            AssetProvenance(
                asset_provenance_id=stable_id("asset_prov", asset_id, "pick_identity_support", identity_support_claim.claim_id if identity_support_claim else pick_key),
                asset_id=asset_id,
                player_tenure_id=None,
                pick_asset_id=pick_asset_id,
                source_record_id=identity_support_claim.source_record_id if identity_support_claim else None,
                claim_id=identity_support_claim.claim_id if identity_support_claim else None,
                override_id=None,
                provenance_role="pick_identity_support",
                fallback_reason=None if identity_support_claim else "subject_key_derivation",
                created_at=built_at_value,
            )
        )

        for candidate in stage_candidates:
            current_override = candidate.support_override
            pick_resolution = CanonicalPickResolution(
                pick_resolution_id=stable_id(
                    "pick_resolution",
                    pick_asset_id,
                    candidate.state_type,
                    candidate.effective_start_date.isoformat(),
                    candidate.state_payload,
                ),
                pick_asset_id=pick_asset_id,
                state_type=candidate.state_type,
                effective_start_date=candidate.effective_start_date,
                effective_end_date=candidate.effective_end_date,
                overall_pick_number=candidate.overall_pick_number,
                lottery_context=candidate.lottery_context,
                drafted_player_id=candidate.drafted_player_id,
                source_event_id=candidate.source_event_id,
                state_payload=candidate.state_payload,
                created_at=built_at_value,
                updated_at=built_at_value,
            )
            pick_resolutions.append(pick_resolution)

            roles = ["asset_state_support"]
            if candidate.state_type == "resolved_pick":
                roles.append("pick_resolution_support")
            elif candidate.state_type == "drafted_player":
                roles.append("drafted_player_linkage_support")
            elif candidate.state_type == "future_pick":
                roles.append("pick_identity_support")
            elif candidate.state_type == "conveyed_away":
                roles.append("pick_conveyance_support")

            support_claim = candidate.support_claims[0] if candidate.support_claims else None
            if support_claim is not None:
                pick_resolution_provenance_rows.append(
                    PickResolutionProvenance(
                        pick_resolution_provenance_id=stable_id(
                            "pick_resolution_prov",
                            pick_resolution.pick_resolution_id,
                            roles[0],
                            support_claim.claim_id,
                        ),
                        pick_resolution_id=pick_resolution.pick_resolution_id,
                        source_record_id=support_claim.source_record_id,
                        claim_id=support_claim.claim_id,
                        override_id=current_override.override_id if current_override else None,
                        provenance_role=roles[0],
                        fallback_reason=candidate.fallback_reason,
                        created_at=built_at_value,
                    )
                )
            for role in roles[1:]:
                pick_resolution_provenance_rows.append(
                    PickResolutionProvenance(
                        pick_resolution_provenance_id=stable_id(
                            "pick_resolution_prov",
                            pick_resolution.pick_resolution_id,
                            role,
                            support_claim.claim_id if support_claim else candidate.state_type,
                        ),
                        pick_resolution_id=pick_resolution.pick_resolution_id,
                        source_record_id=support_claim.source_record_id if support_claim else None,
                        claim_id=support_claim.claim_id if support_claim else None,
                        override_id=current_override.override_id if current_override else None,
                        provenance_role=role,
                        fallback_reason=candidate.fallback_reason,
                        created_at=built_at_value,
                    )
                )

    resolutions_by_asset: dict[str, list[CanonicalPickResolution]] = defaultdict(list)
    for row in pick_resolutions:
        resolutions_by_asset[row.pick_asset_id].append(row)
    for rows in resolutions_by_asset.values():
        rows.sort(key=lambda row: (row.effective_start_date, PICK_STAGE_ORDER[row.state_type], row.pick_resolution_id))
        for index, row in enumerate(rows):
            next_row = rows[index + 1] if index + 1 < len(rows) else None
            if next_row is not None:
                updated = CanonicalPickResolution(
                    pick_resolution_id=row.pick_resolution_id,
                    pick_asset_id=row.pick_asset_id,
                    state_type=row.state_type,
                    effective_start_date=row.effective_start_date,
                    effective_end_date=next_row.effective_start_date,
                    overall_pick_number=row.overall_pick_number,
                    lottery_context=row.lottery_context,
                    drafted_player_id=row.drafted_player_id,
                    source_event_id=row.source_event_id,
                    state_payload=row.state_payload,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for replace_index, existing in enumerate(pick_resolutions):
                    if existing.pick_resolution_id == row.pick_resolution_id:
                        pick_resolutions[replace_index] = updated
                        break

    evidence_build_hash = stable_payload_hash(
        {
            "event_ids": sorted({event.event_id for event in events_list}),
            "claim_ids": sorted({claim.claim_id for claim in claims_list}),
            "source_record_ids": sorted({claim.source_record_id for claim in claims_list if claim.source_record_id}),
            "pick_asset_ids": sorted({row.pick_asset_id for row in pick_assets}),
        }
    )
    override_snapshot_hash = stable_payload_hash(
        {
            "override_ids": [override.override_id for override in active_overrides],
            "override_payloads": {override.override_id: override.payload for override in active_overrides},
        }
    )
    build = CanonicalBuild(
        canonical_build_id=stable_id(
            "canonical_build",
            builder_version,
            built_at_value.isoformat(),
            evidence_build_hash,
            override_snapshot_hash,
        ),
        built_at=built_at_value,
        builder_version=builder_version,
        evidence_build_id=stable_id("evidence_build", evidence_build_hash),
        override_snapshot_hash=override_snapshot_hash,
        notes="Stage 4 pick lifecycle build",
    )
    return CanonicalPickLifecycleBuildResult(
        build=build,
        pick_assets=pick_assets,
        pick_asset_provenance_rows=pick_asset_provenance_rows,
        pick_resolutions=pick_resolutions,
        pick_resolution_provenance_rows=pick_resolution_provenance_rows,
        assets=assets,
        asset_provenance_rows=asset_provenance_rows,
    )


def fetch_pick_lifecycle_build_inputs(conn: Any) -> tuple[list[CanonicalEvent], list[EventProvenance], list[NormalizedClaim], list[OverrideRecord]]:
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
                claim_id,
                source_record_id,
                claim_type,
                claim_subject_type,
                claim_subject_key,
                claim_group_hint,
                claim_date,
                source_sequence,
                claim_payload,
                confidence_flag,
                normalizer_version,
                created_at
            from evidence.normalized_claims
            order by created_at, claim_id
            """
        )
        claim_rows = cur.fetchall()
        cur.execute(
            """
            select
                override_id,
                override_type,
                target_type,
                target_key,
                payload,
                reason,
                authored_by,
                authored_at,
                is_active
            from evidence.overrides
            order by authored_at, override_id
            """
        )
        override_rows = cur.fetchall()

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
    claims = [
        NormalizedClaim(
            claim_id=row[0],
            source_record_id=row[1],
            claim_type=row[2],
            claim_subject_type=row[3],
            claim_subject_key=row[4],
            claim_group_hint=row[5],
            claim_date=row[6],
            source_sequence=row[7],
            claim_payload=row[8],
            confidence_flag=row[9],
            normalizer_version=row[10],
            created_at=row[11],
        )
        for row in claim_rows
    ]
    overrides = [
        OverrideRecord(
            override_id=row[0],
            override_type=row[1],
            target_type=row[2],
            target_key=row[3],
            payload=row[4],
            reason=row[5],
            authored_by=row[6],
            authored_at=row[7],
            is_active=row[8],
        )
        for row in override_rows
    ]
    return events, event_provenance, claims, overrides


def persist_canonical_pick_lifecycle_build(conn: Any, result: CanonicalPickLifecycleBuildResult) -> dict[str, int]:
    pick_asset_ids = {row.pick_asset_id for row in result.pick_assets}
    with conn.cursor() as cur:
        cur.execute("delete from canonical.pick_resolution_provenance")
        cur.execute("delete from canonical.pick_resolution")
        cur.execute(
            "delete from canonical.asset_provenance where asset_id in (select asset_id from canonical.asset where pick_asset_id is not null)"
        )
        cur.execute("delete from canonical.asset where pick_asset_id is not null")
        cur.execute("delete from canonical.pick_asset_provenance")
        cur.execute("delete from canonical.pick_asset")
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
        for row in result.pick_assets:
            cur.execute(
                """
                insert into canonical.pick_asset (
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
                )
                values (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                """,
                (
                    row.pick_asset_id,
                    row.origin_team_code,
                    row.draft_year,
                    row.draft_round,
                    row.protection_summary,
                    json.dumps(row.protection_payload, sort_keys=True, default=str),
                    row.drafted_player_id,
                    row.current_pick_stage,
                    row.created_at,
                    row.updated_at,
                ),
            )
        for row in result.assets:
            if row.pick_asset_id not in pick_asset_ids:
                continue
            cur.execute(
                """
                insert into canonical.asset (
                    asset_id,
                    asset_kind,
                    player_tenure_id,
                    pick_asset_id,
                    asset_label,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row.asset_id,
                    row.asset_kind,
                    row.player_tenure_id,
                    row.pick_asset_id,
                    row.asset_label,
                    row.created_at,
                    row.updated_at,
                ),
            )
        for row in result.pick_asset_provenance_rows:
            cur.execute(
                """
                insert into canonical.pick_asset_provenance (
                    pick_asset_provenance_id,
                    pick_asset_id,
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
                    row.pick_asset_provenance_id,
                    row.pick_asset_id,
                    row.source_record_id,
                    row.claim_id,
                    row.override_id,
                    row.provenance_role,
                    row.fallback_reason,
                    row.created_at,
                ),
            )
        for row in result.asset_provenance_rows:
            if row.pick_asset_id not in pick_asset_ids:
                continue
            cur.execute(
                """
                insert into canonical.asset_provenance (
                    asset_provenance_id,
                    asset_id,
                    player_tenure_id,
                    pick_asset_id,
                    source_record_id,
                    claim_id,
                    override_id,
                    provenance_role,
                    fallback_reason,
                    created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row.asset_provenance_id,
                    row.asset_id,
                    row.player_tenure_id,
                    row.pick_asset_id,
                    row.source_record_id,
                    row.claim_id,
                    row.override_id,
                    row.provenance_role,
                    row.fallback_reason,
                    row.created_at,
                ),
            )
        for row in result.pick_resolutions:
            cur.execute(
                """
                insert into canonical.pick_resolution (
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
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    row.pick_resolution_id,
                    row.pick_asset_id,
                    row.state_type,
                    row.effective_start_date,
                    row.effective_end_date,
                    row.overall_pick_number,
                    row.lottery_context,
                    row.drafted_player_id,
                    row.source_event_id,
                    json.dumps(row.state_payload, sort_keys=True, default=str),
                    row.created_at,
                    row.updated_at,
                ),
            )
        for row in result.pick_resolution_provenance_rows:
            cur.execute(
                """
                insert into canonical.pick_resolution_provenance (
                    pick_resolution_provenance_id,
                    pick_resolution_id,
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
                    row.pick_resolution_provenance_id,
                    row.pick_resolution_id,
                    row.source_record_id,
                    row.claim_id,
                    row.override_id,
                    row.provenance_role,
                    row.fallback_reason,
                    row.created_at,
                ),
            )
    return result.counts()


def build_and_persist_canonical_pick_lifecycle(*, builder_version: str = "stage4-pick-lifecycle-v1") -> dict[str, int]:
    with _connect() as conn:
        events, event_provenance, claims, overrides = fetch_pick_lifecycle_build_inputs(conn)
        result = build_pick_lifecycle(
            events,
            event_provenance,
            claims,
            overrides,
            builder_version=builder_version,
        )
        counts = persist_canonical_pick_lifecycle_build(conn, result)
        conn.commit()
    return counts
