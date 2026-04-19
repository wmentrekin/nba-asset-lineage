from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from canonical.events import CanonicalEvent, EventProvenance
from canonical.models import (
    AssetProvenance,
    AssetState,
    AssetStateProvenance,
    CanonicalAsset,
    CanonicalBuild,
    CanonicalPlayerIdentity,
    CanonicalPlayerTenure,
    CanonicalPlayerTenureBuildResult,
    PlayerIdentityProvenance,
)
from db_config import load_database_url
from evidence.models import NormalizedClaim, OverrideRecord
from evidence.normalize import normalize_name
from shared.ids import stable_id, stable_payload_hash


def bootstrap_canonical_player_tenure_schema(sql_path: Path | str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required to bootstrap canonical player tenure tables.") from exc

    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with psycopg.connect(load_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
        conn.commit()


def _connect():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for canonical player tenure builds.") from exc
    return psycopg.connect(load_database_url())


def _player_id_from_claim(claim: NormalizedClaim) -> str:
    for key in ("player_identity", "player_id", "nba_person_id", "PERSON_ID"):
        value = str(claim.claim_payload.get(key) or "").strip()
        if value:
            return value
    if claim.claim_subject_key.startswith("player::"):
        subject_value = claim.claim_subject_key.split("player::", 1)[1].strip()
        if subject_value:
            return subject_value
    fallback_name = normalize_name(str(claim.claim_payload.get("player_name") or ""))
    return stable_id("player", fallback_name or claim.claim_subject_key)


def _player_display_name(claims: Iterable[NormalizedClaim], player_id: str) -> str:
    values = [
        str(claim.claim_payload.get("player_name") or "").strip()
        for claim in claims
        if str(claim.claim_payload.get("player_name") or "").strip()
    ]
    if values:
        counts = Counter(values)
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    if player_id.startswith("player_"):
        return player_id.removeprefix("player_").replace("_", " ").title()
    return player_id


def _nba_person_id(claims: Iterable[NormalizedClaim]) -> str | None:
    for key in ("nba_person_id", "PERSON_ID", "person_id", "player_person_id"):
        values = [
            str(claim.claim_payload.get(key) or "").strip()
            for claim in claims
            if str(claim.claim_payload.get(key) or "").strip()
        ]
        if values:
            counts = Counter(values)
            return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return None


def _group_claims_by_source_record(claims: Iterable[NormalizedClaim]) -> dict[str, list[NormalizedClaim]]:
    grouped: dict[str, list[NormalizedClaim]] = defaultdict(list)
    for claim in claims:
        grouped[claim.source_record_id].append(claim)
    for claim_rows in grouped.values():
        claim_rows.sort(key=lambda claim: (claim.source_sequence if claim.source_sequence is not None else 10**9, claim.claim_id))
    return grouped


def _event_source_record_ids(event_provenance: Iterable[EventProvenance]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in event_provenance:
        if row.source_record_id:
            grouped[row.event_id].add(row.source_record_id)
    return grouped


def _event_claims(
    event: CanonicalEvent,
    event_source_record_ids: dict[str, set[str]],
    claims_by_source_record: dict[str, list[NormalizedClaim]],
) -> list[NormalizedClaim]:
    rows: list[NormalizedClaim] = []
    for source_record_id in sorted(event_source_record_ids.get(event.event_id, set())):
        rows.extend(claims_by_source_record.get(source_record_id, []))
    return rows


def _event_description(event: CanonicalEvent, claims: Iterable[NormalizedClaim]) -> str:
    descriptions = [
        str(claim.claim_payload.get("description") or claim.claim_payload.get("event_description") or "").strip()
        for claim in claims
        if claim.claim_type == "event_description"
    ]
    descriptions = [value for value in descriptions if value]
    if descriptions:
        counts = Counter(descriptions)
        return sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))[0][0]
    return event.description or ""


def _trade_direction(description: str) -> str:
    text = description.lower()
    if any(marker in text for marker in ("to memphis", "to the grizzlies", "joins memphis", "acquired by memphis", "memphis acquires")):
        return "incoming"
    if any(marker in text for marker in ("from memphis", "sent to", "traded away", "released by memphis", "waived by memphis", "buyout")):
        return "outgoing"
    return "unknown"


def _is_entry_event(event: CanonicalEvent, description: str, tenure_open: bool) -> bool:
    if event.event_type in {"signing", "re_signing", "draft"}:
        return True
    if event.event_type == "trade":
        direction = _trade_direction(description)
        if direction == "incoming":
            return True
        if direction == "outgoing":
            return False
        return not tenure_open
    return False


def _is_exit_event(event: CanonicalEvent, description: str, tenure_open: bool) -> bool:
    if event.event_type in {"waiver", "buyout"}:
        return True
    if event.event_type == "trade":
        direction = _trade_direction(description)
        if direction == "outgoing":
            return True
        if direction == "incoming":
            return False
        return tenure_open
    return False


def _opening_tenure_type(event: CanonicalEvent, description: str) -> tuple[str, str | None]:
    if event.event_type == "draft":
        return "draft", "draft"
    if event.event_type in {"signing", "re_signing"}:
        return event.event_type, "free_agency"
    if event.event_type == "trade":
        if _trade_direction(description) == "incoming":
            return "trade_acquisition", "trade"
        return "trade", "trade"
    return event.event_type, None


def _contract_payload(claim: NormalizedClaim) -> dict[str, Any]:
    payload = dict(claim.claim_payload)
    contract_metadata = payload.get("contract_metadata")
    if isinstance(contract_metadata, dict):
        return dict(contract_metadata)
    return payload


def _contract_dates(claim: NormalizedClaim, fallback_start: date) -> tuple[date, date | None]:
    payload = _contract_payload(claim)
    start_raw = payload.get("start_date") or payload.get("effective_start_date")
    end_raw = payload.get("end_date") or payload.get("effective_end_date")
    start_date = date.fromisoformat(str(start_raw)) if start_raw else fallback_start
    end_date = date.fromisoformat(str(end_raw)) if end_raw else None
    return start_date, end_date


def _state_type(claim: NormalizedClaim) -> str:
    return "buyout_metadata_point" if claim.claim_type == "buyout_metadata" else "player_contract_interval"


def _build_player_identities(
    claims: Iterable[NormalizedClaim],
    *,
    built_at: datetime,
) -> tuple[list[CanonicalPlayerIdentity], list[PlayerIdentityProvenance]]:
    player_claims = [claim for claim in claims if claim.claim_subject_type == "player"]
    grouped: dict[str, list[NormalizedClaim]] = defaultdict(list)
    for claim in player_claims:
        grouped[_player_id_from_claim(claim)].append(claim)

    identities: list[CanonicalPlayerIdentity] = []
    provenance_rows: list[PlayerIdentityProvenance] = []
    for player_id, rows in sorted(grouped.items()):
        display_name = _player_display_name(rows, player_id)
        identities.append(
            CanonicalPlayerIdentity(
                player_id=player_id,
                display_name=display_name,
                normalized_name=normalize_name(display_name),
                nba_person_id=_nba_person_id(rows),
                created_at=built_at,
                updated_at=built_at,
            )
        )
        for claim in rows:
            provenance_rows.append(
                PlayerIdentityProvenance(
                    player_identity_provenance_id=stable_id(
                        "player_identity_prov",
                        player_id,
                        "player_identity_resolution_support",
                        claim.claim_id,
                    ),
                    player_id=player_id,
                    source_record_id=claim.source_record_id,
                    claim_id=claim.claim_id,
                    override_id=None,
                    provenance_role="player_identity_resolution_support",
                    fallback_reason=None,
                    created_at=built_at,
                )
            )
    return identities, provenance_rows


def _build_player_tenures(
    events: Iterable[CanonicalEvent],
    event_provenance: Iterable[EventProvenance],
    claims: Iterable[NormalizedClaim],
    *,
    built_at: datetime,
) -> tuple[
    list[CanonicalPlayerTenure],
    list[CanonicalAsset],
    list[AssetProvenance],
    list[AssetState],
    list[AssetStateProvenance],
]:
    events_list = sorted(list(events), key=lambda event: (event.event_date, event.event_order, event.event_id))
    claims_list = list(claims)
    event_source_record_ids = _event_source_record_ids(event_provenance)
    claims_by_source_record = _group_claims_by_source_record(claims_list)
    claims_by_player_id: dict[str, list[NormalizedClaim]] = defaultdict(list)
    for claim in claims_list:
        if claim.claim_subject_type == "player":
            claims_by_player_id[_player_id_from_claim(claim)].append(claim)

    open_tenure_by_player: dict[str, CanonicalPlayerTenure] = {}
    tenure_rows: list[CanonicalPlayerTenure] = []
    asset_rows: list[CanonicalAsset] = []
    asset_provenance_rows: list[AssetProvenance] = []
    asset_states: dict[str, AssetState] = {}
    asset_state_provenance_rows: dict[str, AssetStateProvenance] = {}

    for event in events_list:
        event_claims = _event_claims(event, event_source_record_ids, claims_by_source_record)
        player_claims = [claim for claim in event_claims if claim.claim_subject_type == "player"]
        if not player_claims:
            continue
        description = _event_description(event, event_claims)

        player_ids_in_event = sorted({_player_id_from_claim(claim) for claim in player_claims})
        for player_id in player_ids_in_event:
            player_rows = claims_by_player_id.get(player_id, [])
            support_claims = [claim for claim in player_claims if _player_id_from_claim(claim) == player_id]
            support_claim = support_claims[0] if support_claims else player_rows[0]
            tenure_open = player_id in open_tenure_by_player

            if _is_entry_event(event, description, tenure_open) and not tenure_open:
                tenure_type, roster_path_type = _opening_tenure_type(event, description)
                tenure_id = stable_id("player_tenure", player_id, event.event_date.isoformat(), event.event_id, tenure_type)
                tenure = CanonicalPlayerTenure(
                    player_tenure_id=tenure_id,
                    player_id=player_id,
                    tenure_start_date=event.event_date,
                    tenure_end_date=None,
                    entry_event_id=event.event_id,
                    exit_event_id=None,
                    tenure_type=tenure_type,
                    roster_path_type=roster_path_type,
                    created_at=built_at,
                    updated_at=built_at,
                )
                open_tenure_by_player[player_id] = tenure
                tenure_rows.append(tenure)
                display_name = _player_display_name(player_rows or [support_claim], player_id)
                asset_id = stable_id("asset", tenure_id, "player_tenure")
                asset_rows.append(
                    CanonicalAsset(
                        asset_id=asset_id,
                        asset_kind="player_tenure",
                        player_tenure_id=tenure_id,
                        pick_asset_id=None,
                        asset_label=f"{display_name} Memphis tenure {sum(1 for row in tenure_rows if row.player_id == player_id)}",
                        created_at=built_at,
                        updated_at=built_at,
                    )
                )
                asset_provenance_rows.extend(
                    [
                        AssetProvenance(
                            asset_provenance_id=stable_id("asset_prov", asset_id, "asset_identity_support", support_claim.claim_id),
                            asset_id=asset_id,
                            player_tenure_id=tenure_id,
                            pick_asset_id=None,
                            source_record_id=support_claim.source_record_id,
                            claim_id=support_claim.claim_id,
                            override_id=None,
                            provenance_role="asset_identity_support",
                            fallback_reason=None,
                            created_at=built_at,
                        ),
                        AssetProvenance(
                            asset_provenance_id=stable_id(
                                "asset_prov", asset_id, "player_identity_resolution_support", support_claim.claim_id
                            ),
                            asset_id=asset_id,
                            player_tenure_id=tenure_id,
                            pick_asset_id=None,
                            source_record_id=support_claim.source_record_id,
                            claim_id=support_claim.claim_id,
                            override_id=None,
                            provenance_role="player_identity_resolution_support",
                            fallback_reason=None,
                            created_at=built_at,
                        ),
                    ]
                )
            elif _is_exit_event(event, description, tenure_open) and tenure_open:
                tenure = open_tenure_by_player[player_id]
                updated_tenure = CanonicalPlayerTenure(
                    player_tenure_id=tenure.player_tenure_id,
                    player_id=tenure.player_id,
                    tenure_start_date=tenure.tenure_start_date,
                    tenure_end_date=event.event_date,
                    entry_event_id=tenure.entry_event_id,
                    exit_event_id=event.event_id,
                    tenure_type=tenure.tenure_type,
                    roster_path_type=tenure.roster_path_type,
                    created_at=tenure.created_at,
                    updated_at=built_at,
                )
                tenure_rows[tenure_rows.index(tenure)] = updated_tenure
                open_tenure_by_player.pop(player_id, None)

    state_claims = [claim for claim in claims_list if claim.claim_subject_type == "player" and claim.claim_type in {"contract_metadata", "buyout_metadata"}]
    source_record_to_event_id: dict[str, str] = {}
    for event in events_list:
        for source_record_id in event_source_record_ids.get(event.event_id, set()):
            source_record_to_event_id[source_record_id] = event.event_id

    for claim in state_claims:
        player_id = _player_id_from_claim(claim)
        player_tenures = [
            tenure
            for tenure in tenure_rows
            if tenure.player_id == player_id
        ]
        if not player_tenures:
            continue
        start_date, end_date = _contract_dates(claim, claim.claim_date or player_tenures[0].tenure_start_date)
        state_date = claim.claim_date or start_date
        tenure_candidates = [
            tenure
            for tenure in player_tenures
            if tenure.tenure_start_date <= state_date
            and (tenure.tenure_end_date is None or tenure.tenure_end_date >= state_date)
        ]
        if not tenure_candidates:
            continue
        tenure = sorted(tenure_candidates, key=lambda row: (row.tenure_start_date, row.player_tenure_id))[-1]
        asset_id = stable_id("asset", tenure.player_tenure_id, "player_tenure")
        state_type = _state_type(claim)
        state_payload = _contract_payload(claim)
        asset_state = AssetState(
            asset_state_id=stable_id(
                "asset_state",
                asset_id,
                state_type,
                start_date.isoformat(),
                end_date.isoformat() if end_date else None,
                state_payload,
            ),
            asset_id=asset_id,
            state_type=state_type,
            effective_start_date=start_date,
            effective_end_date=end_date,
            state_payload=state_payload,
            source_event_id=source_record_to_event_id.get(claim.source_record_id),
            created_at=built_at,
            updated_at=built_at,
        )
        asset_states[asset_state.asset_state_id] = asset_state
        roles = ["asset_state_support"]
        if state_type == "buyout_metadata_point":
            roles.append("buyout_metadata_support")
        for role in roles:
            provenance = AssetStateProvenance(
                asset_state_provenance_id=stable_id("asset_state_prov", asset_state.asset_state_id, role, claim.claim_id),
                asset_state_id=asset_state.asset_state_id,
                source_record_id=claim.source_record_id,
                claim_id=claim.claim_id,
                override_id=None,
                provenance_role=role,
                fallback_reason=None,
                created_at=built_at,
            )
            asset_state_provenance_rows[provenance.asset_state_provenance_id] = provenance

    tenure_rows = sorted(tenure_rows, key=lambda row: (row.player_id, row.tenure_start_date, row.entry_event_id, row.player_tenure_id))
    asset_rows = sorted(asset_rows, key=lambda row: (row.player_tenure_id or "", row.asset_id))
    asset_provenance_rows = sorted(asset_provenance_rows, key=lambda row: (row.asset_id, row.provenance_role, row.claim_id or ""))
    asset_states = sorted(asset_states.values(), key=lambda row: (row.asset_id, row.effective_start_date, row.state_type, row.asset_state_id))
    asset_state_provenance_rows = sorted(
        asset_state_provenance_rows.values(),
        key=lambda row: (row.asset_state_id, row.provenance_role, row.claim_id or ""),
    )
    return tenure_rows, asset_rows, asset_provenance_rows, asset_states, asset_state_provenance_rows


def build_player_tenures(
    events: Iterable[CanonicalEvent],
    event_provenance: Iterable[EventProvenance],
    claims: Iterable[NormalizedClaim],
    overrides: Iterable[OverrideRecord],
    *,
    builder_version: str = "stage3-player-tenure-v1",
    built_at: datetime | None = None,
) -> CanonicalPlayerTenureBuildResult:
    built_at_value = built_at or datetime.utcnow()
    events_list = list(events)
    event_provenance_list = list(event_provenance)
    claims_list = list(claims)
    overrides_list = list(overrides)

    player_identities, player_identity_provenance_rows = _build_player_identities(claims_list, built_at=built_at_value)
    player_tenures, assets, asset_provenance_rows, asset_states, asset_state_provenance_rows = _build_player_tenures(
        events_list,
        event_provenance_list,
        claims_list,
        built_at=built_at_value,
    )

    evidence_build_hash = stable_payload_hash(
        {
            "event_ids": sorted({event.event_id for event in events_list}),
            "claim_ids": sorted({claim.claim_id for claim in claims_list}),
            "source_record_ids": sorted({claim.source_record_id for claim in claims_list if claim.source_record_id}),
        }
    )
    override_snapshot_hash = stable_payload_hash(
        {
            "override_ids": [override.override_id for override in overrides_list if override.is_active],
            "override_payloads": {override.override_id: override.payload for override in overrides_list if override.is_active},
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
        notes="Stage 3 player tenure build",
    )
    return CanonicalPlayerTenureBuildResult(
        build=build,
        player_identities=player_identities,
        player_identity_provenance_rows=player_identity_provenance_rows,
        player_tenures=player_tenures,
        assets=assets,
        asset_provenance_rows=asset_provenance_rows,
        asset_states=asset_states,
        asset_state_provenance_rows=asset_state_provenance_rows,
    )


def fetch_player_tenure_build_inputs(
    conn: Any,
) -> tuple[list[CanonicalEvent], list[EventProvenance], list[NormalizedClaim], list[OverrideRecord]]:
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


def persist_canonical_player_tenure_build(conn: Any, result: CanonicalPlayerTenureBuildResult) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("delete from canonical.asset_state_provenance")
        cur.execute("delete from canonical.asset_state")
        cur.execute("delete from canonical.asset_provenance")
        cur.execute("delete from canonical.asset")
        cur.execute("delete from canonical.player_tenure")
        cur.execute("delete from canonical.player_identity_provenance")
        cur.execute("delete from canonical.player_identity")
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
        for row in result.player_identities:
            cur.execute(
                """
                insert into canonical.player_identity (
                    player_id,
                    display_name,
                    normalized_name,
                    nba_person_id,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, %s, %s)
                """,
                (
                    row.player_id,
                    row.display_name,
                    row.normalized_name,
                    row.nba_person_id,
                    row.created_at,
                    row.updated_at,
                ),
            )
        for row in result.player_identity_provenance_rows:
            cur.execute(
                """
                insert into canonical.player_identity_provenance (
                    player_identity_provenance_id,
                    player_id,
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
                    row.player_identity_provenance_id,
                    row.player_id,
                    row.source_record_id,
                    row.claim_id,
                    row.override_id,
                    row.provenance_role,
                    row.fallback_reason,
                    row.created_at,
                ),
            )
        for row in result.player_tenures:
            cur.execute(
                """
                insert into canonical.player_tenure (
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
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row.player_tenure_id,
                    row.player_id,
                    row.tenure_start_date,
                    row.tenure_end_date,
                    row.entry_event_id,
                    row.exit_event_id,
                    row.tenure_type,
                    row.roster_path_type,
                    row.created_at,
                    row.updated_at,
                ),
            )
        for row in result.assets:
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
        for row in result.asset_provenance_rows:
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
        for row in result.asset_states:
            cur.execute(
                """
                insert into canonical.asset_state (
                    asset_state_id,
                    asset_id,
                    state_type,
                    effective_start_date,
                    effective_end_date,
                    state_payload,
                    source_event_id,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                (
                    row.asset_state_id,
                    row.asset_id,
                    row.state_type,
                    row.effective_start_date,
                    row.effective_end_date,
                    json.dumps(row.state_payload, sort_keys=True, default=str),
                    row.source_event_id,
                    row.created_at,
                    row.updated_at,
                ),
            )
        for row in result.asset_state_provenance_rows:
            cur.execute(
                """
                insert into canonical.asset_state_provenance (
                    asset_state_provenance_id,
                    asset_state_id,
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
                    row.asset_state_provenance_id,
                    row.asset_state_id,
                    row.source_record_id,
                    row.claim_id,
                    row.override_id,
                    row.provenance_role,
                    row.fallback_reason,
                    row.created_at,
                ),
            )
    return result.counts()


def build_and_persist_canonical_player_tenures(*, builder_version: str = "stage3-player-tenure-v1") -> dict[str, int]:
    with _connect() as conn:
        events, event_provenance, claims, overrides = fetch_player_tenure_build_inputs(conn)
        result = build_player_tenures(
            events,
            event_provenance,
            claims,
            overrides,
            builder_version=builder_version,
        )
        counts = persist_canonical_player_tenure_build(conn, result)
        conn.commit()
    return counts
