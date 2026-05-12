from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from canonical.models import CanonicalBuild, CanonicalEvent, CanonicalEventBuildResult, EventProvenance
from db_config import load_database_url
from evidence.models import NormalizedClaim, OverrideRecord
from shared.ids import stable_id, stable_payload_hash


EVENT_RELEVANT_CLAIM_TYPES = {
    "event_date",
    "event_type",
    "event_description",
    "transaction_counterparty",
    "event_order_hint",
}


@dataclass
class EventCluster:
    cluster_key: str
    claims: list[NormalizedClaim]
    overrides: list[OverrideRecord]


def bootstrap_canonical_events_schema(sql_path: Path | str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required to bootstrap canonical event tables.") from exc

    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with psycopg.connect(load_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
        conn.commit()


def _is_active(override: OverrideRecord) -> bool:
    return bool(override.is_active)


def _event_date_from_claims(claims: list[NormalizedClaim]) -> date:
    dates = [claim.claim_date for claim in claims if claim.claim_type == "event_date" and claim.claim_date]
    if not dates:
        raise ValueError("Canonical event build requires at least one event_date claim per cluster.")
    counts = Counter(dates)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _event_type_from_claims(claims: list[NormalizedClaim]) -> str:
    values = [
        str(claim.claim_payload.get("event_type") or "").strip()
        for claim in claims
        if claim.claim_type == "event_type"
    ]
    counts = Counter(value for value in values if value)
    if not counts:
        return "unknown"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _description_from_claims(claims: list[NormalizedClaim]) -> str | None:
    descriptions = [
        str(
            claim.claim_payload.get("description")
            or claim.claim_payload.get("event_description")
            or ""
        ).strip()
        for claim in claims
        if claim.claim_type == "event_description"
    ]
    descriptions = [description for description in descriptions if description]
    if not descriptions:
        return None
    counts = Counter(descriptions)
    return sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))[0][0]


def _cluster_key_for_claim(claim: NormalizedClaim) -> str:
    if claim.claim_group_hint:
        return claim.claim_group_hint
    return f"{claim.claim_date or 'undated'}::{claim.claim_subject_type}::{claim.claim_subject_key}"


def _build_clusters(
    claims: Iterable[NormalizedClaim],
    overrides: Iterable[OverrideRecord],
) -> list[EventCluster]:
    relevant_claims = [claim for claim in claims if claim.claim_type in EVENT_RELEVANT_CLAIM_TYPES]
    active_overrides = [override for override in overrides if _is_active(override)]

    excluded_claim_ids = {
        override.target_key
        for override in active_overrides
        if override.override_type in {"source_exclusion", "exclude_source_claim"} and override.target_type == "claim"
    }
    excluded_source_record_ids = {
        override.target_key
        for override in active_overrides
        if override.override_type in {"source_exclusion", "exclude_source_claim"} and override.target_type == "source_record"
    }

    cluster_rewrites: dict[str, str] = {}
    for override in active_overrides:
        if override.override_type not in {"merge_event_cluster", "event_merge_hint"}:
            continue
        target_key = str(override.payload.get("target_cluster_key") or override.target_key).strip()
        if not target_key:
            continue
        source_keys = override.payload.get("source_cluster_keys") or [override.target_key]
        if not isinstance(source_keys, list):
            source_keys = [override.target_key]
        for source_key in source_keys:
            cluster_rewrites[str(source_key)] = target_key

    claims_by_cluster: dict[str, list[NormalizedClaim]] = defaultdict(list)
    for claim in relevant_claims:
        if claim.claim_id in excluded_claim_ids or claim.source_record_id in excluded_source_record_ids:
            continue
        original_key = _cluster_key_for_claim(claim)
        cluster_key = cluster_rewrites.get(original_key, original_key)
        claims_by_cluster[cluster_key].append(claim)

    overrides_by_cluster: dict[str, list[OverrideRecord]] = defaultdict(list)
    for override in active_overrides:
        if override.target_type != "event_cluster":
            continue
        target_key = str(override.payload.get("target_cluster_key") or override.target_key)
        cluster_key = cluster_rewrites.get(target_key, target_key)
        overrides_by_cluster[cluster_key].append(override)

    return [
        EventCluster(cluster_key=cluster_key, claims=cluster_claims, overrides=overrides_by_cluster.get(cluster_key, []))
        for cluster_key, cluster_claims in sorted(claims_by_cluster.items())
        if cluster_claims
    ]


def _label_for_event(event_type: str, description: str | None) -> str:
    if description:
        return description
    return event_type.replace("_", " ").title()


def _base_provenance_rows(
    event_id: str,
    claims: list[NormalizedClaim],
    overrides: list[OverrideRecord],
    *,
    created_at: datetime,
) -> list[EventProvenance]:
    rows: list[EventProvenance] = []
    for claim in claims:
        role: str | None = None
        if claim.claim_type == "event_date":
            role = "event_date_support"
        elif claim.claim_type == "event_type":
            role = "event_type_support"
        elif claim.claim_type == "event_description":
            role = "event_description_support"
        if role:
            rows.append(
                EventProvenance(
                    event_provenance_id=stable_id("event_prov", event_id, role, claim.claim_id),
                    event_id=event_id,
                    source_record_id=claim.source_record_id,
                    claim_id=claim.claim_id,
                    override_id=None,
                    provenance_role=role,
                    fallback_reason=None,
                    created_at=created_at,
                )
            )

    for override in overrides:
        if override.override_type in {"merge_event_cluster", "event_merge_hint"}:
            rows.append(
                EventProvenance(
                    event_provenance_id=stable_id("event_prov", event_id, "event_merge_support", override.override_id),
                    event_id=event_id,
                    source_record_id=None,
                    claim_id=None,
                    override_id=override.override_id,
                    provenance_role="event_merge_support",
                    fallback_reason=None,
                    created_at=created_at,
                )
            )
    return rows


def build_canonical_events(
    claims: Iterable[NormalizedClaim],
    overrides: Iterable[OverrideRecord],
    *,
    builder_version: str = "stage2-events-v1",
    built_at: datetime | None = None,
) -> CanonicalEventBuildResult:
    built_at_value = built_at or datetime.utcnow()
    overrides_list = list(overrides)
    clusters = _build_clusters(claims, overrides_list)

    staged_by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for cluster in clusters:
        event_date = _event_date_from_claims(cluster.claims)
        event_type = _event_type_from_claims(cluster.claims)
        description = _description_from_claims(cluster.claims)
        event_id = stable_id("event", cluster.cluster_key)
        event = CanonicalEvent(
            event_id=event_id,
            event_type=event_type,
            event_date=event_date,
            event_order=0,
            event_label=_label_for_event(event_type, description),
            description=description,
            transaction_group_key=cluster.cluster_key,
            is_compound=len({claim.source_record_id for claim in cluster.claims}) > 1,
            notes=None,
            created_at=built_at_value,
            updated_at=built_at_value,
        )
        override_orders = [
            int(override.payload["event_order"])
            for override in cluster.overrides
            if override.override_type in {"event_ordering", "set_event_order"}
            and override.payload.get("event_order") is not None
        ]
        source_sequences = [claim.source_sequence for claim in cluster.claims if claim.source_sequence is not None]
        staged_by_date[event_date].append(
            {
                "cluster": cluster,
                "event": event,
                "override_order": min(override_orders) if override_orders else None,
                "source_sequence": min(source_sequences) if source_sequences else None,
            }
        )

    final_events: list[CanonicalEvent] = []
    final_provenance: list[EventProvenance] = []

    for event_date, entries in sorted(staged_by_date.items()):
        ordered_entries = sorted(
            entries,
            key=lambda entry: (
                0 if entry["override_order"] is not None else 1,
                entry["override_order"] if entry["override_order"] is not None else 10**9,
                entry["source_sequence"] if entry["source_sequence"] is not None else 10**9,
                entry["event"].transaction_group_key or entry["event"].event_id,
            ),
        )
        for dense_order, entry in enumerate(ordered_entries, start=1):
            cluster = entry["cluster"]
            event = entry["event"]
            final_event = CanonicalEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                event_date=event.event_date,
                event_order=dense_order,
                event_label=event.event_label,
                description=event.description,
                transaction_group_key=event.transaction_group_key,
                is_compound=event.is_compound,
                notes=event.notes,
                created_at=event.created_at,
                updated_at=event.updated_at,
            )
            final_events.append(final_event)
            final_provenance.extend(
                _base_provenance_rows(final_event.event_id, cluster.claims, cluster.overrides, created_at=built_at_value)
            )

            if entry["override_order"] is not None:
                supporting_override = next(
                    override for override in cluster.overrides if override.override_type in {"event_ordering", "set_event_order"}
                )
                final_provenance.append(
                    EventProvenance(
                        event_provenance_id=stable_id(
                            "event_prov", final_event.event_id, "event_order_override", supporting_override.override_id
                        ),
                        event_id=final_event.event_id,
                        source_record_id=None,
                        claim_id=None,
                        override_id=supporting_override.override_id,
                        provenance_role="event_order_override",
                        fallback_reason=None,
                        created_at=built_at_value,
                    )
                )
            elif entry["source_sequence"] is not None:
                supporting_claim = sorted(
                    [claim for claim in cluster.claims if claim.source_sequence is not None],
                    key=lambda claim: (claim.source_sequence or 10**9, claim.claim_id),
                )[0]
                final_provenance.append(
                    EventProvenance(
                        event_provenance_id=stable_id(
                            "event_prov", final_event.event_id, "event_order_source_fallback", supporting_claim.claim_id
                        ),
                        event_id=final_event.event_id,
                        source_record_id=supporting_claim.source_record_id,
                        claim_id=supporting_claim.claim_id,
                        override_id=None,
                        provenance_role="event_order_source_fallback",
                        fallback_reason="source_sequence",
                        created_at=built_at_value,
                    )
                )
            else:
                final_provenance.append(
                    EventProvenance(
                        event_provenance_id=stable_id(
                            "event_prov", final_event.event_id, "event_order_deterministic_fallback", final_event.event_id
                        ),
                        event_id=final_event.event_id,
                        source_record_id=None,
                        claim_id=None,
                        override_id=None,
                        provenance_role="event_order_deterministic_fallback",
                        fallback_reason="stable_cluster_key_sort",
                        created_at=built_at_value,
                    )
                )

    override_snapshot_hash = stable_payload_hash(
        {
            "override_ids": [override.override_id for override in overrides_list if _is_active(override)],
            "override_payloads": {
                override.override_id: override.payload
                for override in overrides_list
                if _is_active(override)
            },
        }
    )
    build = CanonicalBuild(
        canonical_build_id=stable_id("canonical_build", builder_version, built_at_value.isoformat(), override_snapshot_hash),
        built_at=built_at_value,
        builder_version=builder_version,
        evidence_build_id=None,
        override_snapshot_hash=override_snapshot_hash,
        notes="Stage 2 canonical event build",
    )
    return CanonicalEventBuildResult(build=build, events=final_events, provenance_rows=final_provenance)


def _connect():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for canonical event builds.") from exc
    return psycopg.connect(load_database_url())


def fetch_event_build_inputs(conn: Any) -> tuple[list[NormalizedClaim], list[OverrideRecord]]:
    with conn.cursor() as cur:
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
    return claims, overrides


def persist_canonical_event_build(conn: Any, result: CanonicalEventBuildResult) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("delete from canonical.event_provenance")
        cur.execute("delete from canonical.events")
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
        for event in result.events:
            cur.execute(
                """
                insert into canonical.events (
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
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event.event_id,
                    event.event_type,
                    event.event_date,
                    event.event_order,
                    event.event_label,
                    event.description,
                    event.transaction_group_key,
                    event.is_compound,
                    event.notes,
                    event.created_at,
                    event.updated_at,
                ),
            )
        for row in result.provenance_rows:
            cur.execute(
                """
                insert into canonical.event_provenance (
                    event_provenance_id,
                    event_id,
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
                    row.event_provenance_id,
                    row.event_id,
                    row.source_record_id,
                    row.claim_id,
                    row.override_id,
                    row.provenance_role,
                    row.fallback_reason,
                    row.created_at,
                ),
            )
    return result.counts()


def build_and_persist_canonical_events(*, builder_version: str = "stage2-events-v1") -> dict[str, int]:
    with _connect() as conn:
        claims, overrides = fetch_event_build_inputs(conn)
        result = build_canonical_events(claims, overrides, builder_version=builder_version)
        counts = persist_canonical_event_build(conn, result)
        conn.commit()
    return counts
