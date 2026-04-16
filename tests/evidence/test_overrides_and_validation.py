from __future__ import annotations

from pathlib import Path

from .helpers import (
    as_list,
    call_validate,
    call_with_fallbacks,
    evidence_module,
    get_callable,
    get_value,
    load_json_fixture,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _capture_source_records():
    ingest = evidence_module("ingest")
    ingest_source_records = get_callable(
        ingest,
        "ingest_source_records",
        "capture_source_records",
    )
    return as_list(
        call_with_fallbacks(
            ingest_source_records,
            (
                (
                    [
                        load_json_fixture("spotrac_transaction_raw.json"),
                        load_json_fixture("spotrac_transaction_raw.json"),
                        load_json_fixture("nba_api_draft_raw.json"),
                    ],
                ),
                {},
            ),
            (
                (
                    load_json_fixture("spotrac_transaction_raw.json"),
                    load_json_fixture("spotrac_transaction_raw.json"),
                    load_json_fixture("nba_api_draft_raw.json"),
                ),
                {},
            ),
        ),
        "source_records",
        "records",
        "items",
    )


def _normalize_all(source_records):
    normalize = evidence_module("normalize")
    normalize_source_record = get_callable(
        normalize,
        "normalize_source_record",
        "normalize_source_records",
        "emit_normalized_claims",
    )
    claims = []
    for source_record in source_records:
        claims.extend(
            as_list(
                call_with_fallbacks(
                    normalize_source_record,
                    ((source_record,), {}),
                    (([source_record],), {}),
                ),
                "normalized_claims",
                "claims",
                "items",
            )
        )
    return claims


def test_override_loader_reads_structured_file_deterministically():
    overrides = evidence_module("overrides")
    load_overrides = get_callable(overrides, "load_overrides", "ingest_overrides")

    override_path = str(FIXTURES_DIR / "event_order_override.json")
    first_load = as_list(load_overrides(override_path), "overrides", "records", "items")
    second_load = as_list(load_overrides(override_path), "overrides", "records", "items")

    assert first_load == second_load
    assert len(first_load) == 1

    override = first_load[0]
    assert get_value(override, "override_id") == "override_event_order_spotrac_ttx_20240208_01"
    assert get_value(override, "override_type") == "event_ordering"
    assert get_value(override, "target_type") == "event_cluster"
    assert get_value(override, "target_key") == "spotrac-tx-2024-02-08-07"
    assert get_value(override, "payload") == {
        "event_cluster_key": "spotrac-tx-2024-02-08-07",
        "event_date": "2024-02-08",
        "event_order": 1,
    }
    assert get_value(override, "reason")
    assert get_value(override, "authored_by") == "curator"
    assert get_value(override, "is_active") is True


def test_validation_report_counts_stage1_inputs_without_canonical_assumptions():
    source_records = _capture_source_records()
    claims = _normalize_all(source_records)

    overrides_module = evidence_module("overrides")
    load_overrides = get_callable(overrides_module, "load_overrides", "ingest_overrides")
    overrides = as_list(
        load_overrides(str(FIXTURES_DIR / "event_order_override.json")),
        "overrides",
        "records",
        "items",
    )

    validate = evidence_module("validate")
    validate_evidence = get_callable(validate, "validate_evidence", "build_validation_report")
    report = call_validate(validate_evidence, source_records, claims, overrides)

    assert get_value(report, "source_record_count", "source_records_count") == 2
    assert get_value(report, "override_count", "overrides_count") == 1
    assert get_value(
        report,
        "duplicate_source_records_skipped",
        "duplicate_source_record_count",
    ) == 1

    claim_counts = get_value(report, "claim_count_by_type", "claims_by_type", "claim_counts")
    assert claim_counts["event_date"] >= 1
    assert claim_counts["pick_identity"] >= 1
