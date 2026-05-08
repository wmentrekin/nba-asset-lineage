from __future__ import annotations

from foundation.models import BaseGraphExport


def build_empty_base_export() -> BaseGraphExport:
    return BaseGraphExport(
        franchise="memphis-grizzlies",
        span_start="2016-07-01",
        span_end="2026-06-30",
    )
