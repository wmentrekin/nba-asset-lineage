from __future__ import annotations

import pytest

from .helpers import (
    as_list,
    call_with_fallbacks,
    evidence_module,
    get_callable,
    get_value,
    load_json_fixture,
)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "spotrac_transaction_raw.json",
        "spotrac_contract_raw.json",
        "nba_api_draft_raw.json",
    ],
)
def test_source_record_capture_preserves_source_metadata_and_payload_hash_is_stable(
    fixture_name,
):
    ingest = evidence_module("ingest")
    ingest_source_records = get_callable(
        ingest,
        "ingest_source_records",
        "capture_source_records",
    )

    raw_source = load_json_fixture(fixture_name)

    captured_records = as_list(
        call_with_fallbacks(
            ingest_source_records,
            (([raw_source, raw_source],), {}),
            ((raw_source,), {}),
        ),
        "source_records",
        "records",
        "items",
    )

    assert len(captured_records) == 1
    captured = captured_records[0]

    for field in (
        "source_system",
        "source_type",
        "source_locator",
        "source_url",
        "captured_at",
        "parser_version",
    ):
        assert get_value(captured, field) == raw_source[field]

    assert get_value(captured, "raw_payload") == raw_source["raw_payload"]
    assert get_value(captured, "payload_hash")
