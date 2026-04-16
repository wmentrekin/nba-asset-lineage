from __future__ import annotations

from datetime import datetime

from canonical.events import build_canonical_events
from evidence.models import NormalizedClaim, OverrideRecord
from evidence.ingest import capture_source_records
from evidence.normalize import normalize_source_record
from evidence.overrides import load_overrides

from tests.evidence.helpers import load_json_fixture


def _claims_from_fixtures():
    raw_records = [
        load_json_fixture("spotrac_transaction_raw.json"),
        load_json_fixture("spotrac_transaction_raw.json"),
        load_json_fixture("nba_api_draft_raw.json"),
    ]
    source_records = capture_source_records(raw_records)
    claims = []
    for record in source_records:
        claims.extend(normalize_source_record(record, normalizer_version="test-normalizer-v1"))
    return claims


def test_build_canonical_events_clusters_and_orders_by_date():
    claims = _claims_from_fixtures()
    overrides = load_overrides("tests/evidence/fixtures/event_order_override.json")
    result = build_canonical_events(
        claims,
        overrides,
        builder_version="test-builder-v1",
        built_at=datetime(2026, 4, 16, 12, 0, 0),
    )

    assert len(result.events) == 2

    draft_event = next(event for event in result.events if event.event_type == "draft")
    signing_event = next(event for event in result.events if event.event_type == "signing")

    assert draft_event.event_date.isoformat() == "2023-06-22"
    assert draft_event.event_order == 1
    assert signing_event.event_date.isoformat() == "2024-02-08"
    assert signing_event.event_order == 1
    assert signing_event.transaction_group_key == "spotrac-tx-2024-02-08-07"


def test_build_canonical_events_writes_order_and_support_provenance():
    claims = _claims_from_fixtures()
    overrides = load_overrides("tests/evidence/fixtures/event_order_override.json")
    result = build_canonical_events(
        claims,
        overrides,
        builder_version="test-builder-v1",
        built_at=datetime(2026, 4, 16, 12, 0, 0),
    )

    provenance_roles = {row.provenance_role for row in result.provenance_rows}
    assert "event_date_support" in provenance_roles
    assert "event_type_support" in provenance_roles
    assert "event_description_support" in provenance_roles
    assert "event_order_override" in provenance_roles


def test_build_canonical_events_uses_source_order_fallback_without_override():
    claims = _claims_from_fixtures()
    result = build_canonical_events(
        claims,
        [],
        builder_version="test-builder-v1",
        built_at=datetime(2026, 4, 16, 12, 0, 0),
    )

    provenance_roles = {row.provenance_role for row in result.provenance_rows}
    assert "event_order_source_fallback" in provenance_roles


def test_build_canonical_events_uses_deterministic_fallback_without_source_sequence():
    built_at = datetime(2026, 4, 16, 12, 0, 0)
    claims = [
        NormalizedClaim(
            claim_id="claim_a_date",
            source_record_id="source_a",
            claim_type="event_date",
            claim_subject_type="event",
            claim_subject_key="event_a",
            claim_group_hint="cluster_b",
            claim_date=datetime(2024, 2, 8).date(),
            source_sequence=None,
            claim_payload={"event_date": "2024-02-08"},
            confidence_flag="high",
            normalizer_version="test-normalizer-v1",
            created_at=built_at,
        ),
        NormalizedClaim(
            claim_id="claim_a_type",
            source_record_id="source_a",
            claim_type="event_type",
            claim_subject_type="event",
            claim_subject_key="event_a",
            claim_group_hint="cluster_b",
            claim_date=datetime(2024, 2, 8).date(),
            source_sequence=None,
            claim_payload={"event_type": "waiver"},
            confidence_flag="high",
            normalizer_version="test-normalizer-v1",
            created_at=built_at,
        ),
        NormalizedClaim(
            claim_id="claim_b_date",
            source_record_id="source_b",
            claim_type="event_date",
            claim_subject_type="event",
            claim_subject_key="event_b",
            claim_group_hint="cluster_a",
            claim_date=datetime(2024, 2, 8).date(),
            source_sequence=None,
            claim_payload={"event_date": "2024-02-08"},
            confidence_flag="high",
            normalizer_version="test-normalizer-v1",
            created_at=built_at,
        ),
        NormalizedClaim(
            claim_id="claim_b_type",
            source_record_id="source_b",
            claim_type="event_type",
            claim_subject_type="event",
            claim_subject_key="event_b",
            claim_group_hint="cluster_a",
            claim_date=datetime(2024, 2, 8).date(),
            source_sequence=None,
            claim_payload={"event_type": "signing"},
            confidence_flag="high",
            normalizer_version="test-normalizer-v1",
            created_at=built_at,
        ),
    ]

    result = build_canonical_events(claims, [], builder_version="test-builder-v1", built_at=built_at)

    assert [event.transaction_group_key for event in result.events] == ["cluster_a", "cluster_b"]
    provenance_roles = {row.provenance_role for row in result.provenance_rows}
    assert "event_order_deterministic_fallback" in provenance_roles


def test_build_canonical_events_merges_clusters_when_merge_override_is_active():
    built_at = datetime(2026, 4, 16, 12, 0, 0)
    claims = [
        NormalizedClaim(
            claim_id="claim_1_date",
            source_record_id="source_1",
            claim_type="event_date",
            claim_subject_type="event",
            claim_subject_key="event_1",
            claim_group_hint="cluster_left",
            claim_date=datetime(2024, 2, 8).date(),
            source_sequence=1,
            claim_payload={"event_date": "2024-02-08"},
            confidence_flag="high",
            normalizer_version="test-normalizer-v1",
            created_at=built_at,
        ),
        NormalizedClaim(
            claim_id="claim_1_type",
            source_record_id="source_1",
            claim_type="event_type",
            claim_subject_type="event",
            claim_subject_key="event_1",
            claim_group_hint="cluster_left",
            claim_date=datetime(2024, 2, 8).date(),
            source_sequence=1,
            claim_payload={"event_type": "trade"},
            confidence_flag="high",
            normalizer_version="test-normalizer-v1",
            created_at=built_at,
        ),
        NormalizedClaim(
            claim_id="claim_2_date",
            source_record_id="source_2",
            claim_type="event_date",
            claim_subject_type="event",
            claim_subject_key="event_2",
            claim_group_hint="cluster_right",
            claim_date=datetime(2024, 2, 8).date(),
            source_sequence=2,
            claim_payload={"event_date": "2024-02-08"},
            confidence_flag="high",
            normalizer_version="test-normalizer-v1",
            created_at=built_at,
        ),
        NormalizedClaim(
            claim_id="claim_2_type",
            source_record_id="source_2",
            claim_type="event_type",
            claim_subject_type="event",
            claim_subject_key="event_2",
            claim_group_hint="cluster_right",
            claim_date=datetime(2024, 2, 8).date(),
            source_sequence=2,
            claim_payload={"event_type": "trade"},
            confidence_flag="high",
            normalizer_version="test-normalizer-v1",
            created_at=built_at,
        ),
    ]
    overrides = [
        OverrideRecord(
            override_id="override_merge_clusters",
            override_type="merge_event_cluster",
            target_type="event_cluster",
            target_key="cluster_left",
            payload={
                "source_cluster_keys": ["cluster_left", "cluster_right"],
                "target_cluster_key": "merged_cluster",
            },
            reason="Both evidence rows describe the same Memphis trade package.",
            authored_by="curator",
            authored_at=built_at,
            is_active=True,
        )
    ]

    result = build_canonical_events(claims, overrides, builder_version="test-builder-v1", built_at=built_at)

    assert len(result.events) == 1
    assert result.events[0].transaction_group_key == "merged_cluster"
    assert result.events[0].is_compound is True
    provenance_roles = {row.provenance_role for row in result.provenance_rows}
    assert "event_merge_support" in provenance_roles
