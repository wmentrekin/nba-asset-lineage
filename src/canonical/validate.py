from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

from canonical.models import CanonicalEvent, EventProvenance


@dataclass(frozen=True)
class CanonicalEventValidationReport:
    event_count: int
    provenance_count: int
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_canonical_events(
    *,
    events: Iterable[CanonicalEvent],
    provenance_rows: Iterable[EventProvenance],
) -> CanonicalEventValidationReport:
    events_list = list(events)
    provenance_list = list(provenance_rows)
    errors: list[str] = []
    warnings: list[str] = []

    event_ids = [event.event_id for event in events_list]
    duplicate_event_ids = [event_id for event_id, count in Counter(event_ids).items() if count > 1]
    if duplicate_event_ids:
        errors.append(f"duplicate event_ids: {', '.join(sorted(duplicate_event_ids))}")

    orders_by_date: dict[object, list[int]] = defaultdict(list)
    for event in events_list:
        orders_by_date[event.event_date].append(event.event_order)
        if event.event_order <= 0:
            errors.append(f"non-positive event_order for {event.event_id}")
        if not event.event_type:
            errors.append(f"missing event_type for {event.event_id}")
        if not event.event_label:
            errors.append(f"missing event_label for {event.event_id}")

    for event_date, orders in orders_by_date.items():
        if len(orders) != len(set(orders)):
            errors.append(f"duplicate same-day event_order on {event_date}")
        expected = list(range(1, len(orders) + 1))
        if sorted(orders) != expected:
            warnings.append(f"non-dense same-day ordering on {event_date}")

    event_ids_set = set(event_ids)
    provenance_by_event: dict[str, list[EventProvenance]] = defaultdict(list)
    for row in provenance_list:
        provenance_by_event[row.event_id].append(row)
        if row.event_id not in event_ids_set:
            errors.append(f"provenance references unknown event_id: {row.event_id}")

    required_roles = {"event_date_support", "event_type_support"}
    valid_order_roles = {
        "event_order_override",
        "event_order_source_fallback",
        "event_order_deterministic_fallback",
    }
    for event in events_list:
        rows = provenance_by_event.get(event.event_id, [])
        if not rows:
            errors.append(f"missing provenance for {event.event_id}")
            continue
        roles = {row.provenance_role for row in rows}
        missing_roles = sorted(required_roles - roles)
        if missing_roles:
            errors.append(f"missing required provenance roles for {event.event_id}: {', '.join(missing_roles)}")
        if not roles.intersection(valid_order_roles):
            errors.append(f"missing event order provenance for {event.event_id}")

    return CanonicalEventValidationReport(
        event_count=len(events_list),
        provenance_count=len(provenance_list),
        errors=errors,
        warnings=warnings,
    )
