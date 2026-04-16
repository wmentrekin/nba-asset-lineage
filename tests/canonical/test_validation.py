from __future__ import annotations

from datetime import date, datetime

from canonical.models import CanonicalEvent, EventProvenance
from canonical.validate import validate_canonical_events


def _event(event_id: str, event_date: str, event_order: int) -> CanonicalEvent:
    now = datetime(2026, 4, 16, 12, 0, 0)
    return CanonicalEvent(
        event_id=event_id,
        event_type="signing",
        event_date=date.fromisoformat(event_date),
        event_order=event_order,
        event_label=f"Event {event_id}",
        description=None,
        transaction_group_key=event_id,
        is_compound=False,
        notes=None,
        created_at=now,
        updated_at=now,
    )


def _prov(event_id: str, role: str) -> EventProvenance:
    return EventProvenance(
        event_provenance_id=f"prov_{event_id}_{role}",
        event_id=event_id,
        source_record_id="source_record_1" if "support" in role or "fallback" in role else None,
        claim_id="claim_1" if "support" in role or "fallback" in role else None,
        override_id="override_1" if role == "event_order_override" else None,
        provenance_role=role,
        fallback_reason="source_sequence" if role == "event_order_source_fallback" else None,
        created_at=datetime(2026, 4, 16, 12, 0, 0),
    )


def test_validate_canonical_events_accepts_dense_same_day_ordering():
    events = [_event("event_1", "2024-02-08", 1), _event("event_2", "2024-02-08", 2)]
    provenance = [
        _prov("event_1", "event_date_support"),
        _prov("event_1", "event_type_support"),
        _prov("event_1", "event_order_source_fallback"),
        _prov("event_2", "event_date_support"),
        _prov("event_2", "event_type_support"),
        _prov("event_2", "event_order_deterministic_fallback"),
    ]

    report = validate_canonical_events(events=events, provenance_rows=provenance)
    assert report.ok
    assert report.errors == []


def test_validate_canonical_events_flags_duplicate_same_day_ordering():
    events = [_event("event_1", "2024-02-08", 1), _event("event_2", "2024-02-08", 1)]
    provenance = [
        _prov("event_1", "event_date_support"),
        _prov("event_1", "event_type_support"),
        _prov("event_1", "event_order_source_fallback"),
        _prov("event_2", "event_date_support"),
        _prov("event_2", "event_type_support"),
        _prov("event_2", "event_order_override"),
    ]

    report = validate_canonical_events(events=events, provenance_rows=provenance)
    assert not report.ok
    assert any("duplicate same-day event_order" in error for error in report.errors)
