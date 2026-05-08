from __future__ import annotations

from .helpers import (
    as_list,
    call_with_fallbacks,
    evidence_module,
    get_callable,
    get_value,
    load_json_fixture,
)


def _capture_source_record(fixture_name: str):
    ingest = evidence_module("ingest")
    ingest_source_records = get_callable(
        ingest,
        "ingest_source_records",
        "capture_source_records",
    )
    return as_list(
        call_with_fallbacks(
            ingest_source_records,
            (([load_json_fixture(fixture_name)],), {}),
            ((load_json_fixture(fixture_name),), {}),
        ),
        "source_records",
        "records",
        "items",
    )[0]


def _normalize(source_record):
    normalize = evidence_module("normalize")
    normalize_source_record = get_callable(
        normalize,
        "normalize_source_record",
        "normalize_source_records",
        "emit_normalized_claims",
    )
    return as_list(
        call_with_fallbacks(
            normalize_source_record,
            ((source_record,), {}),
            (([source_record],), {}),
        ),
        "normalized_claims",
        "claims",
        "items",
    )


def test_transaction_normalization_emits_multiple_claims_with_group_hint_and_version():
    raw_source = load_json_fixture("spotrac_transaction_raw.json")
    claims = _normalize(_capture_source_record("spotrac_transaction_raw.json"))

    claim_types = {get_value(claim, "claim_type") for claim in claims}
    assert {
        "event_date",
        "event_type",
        "event_description",
        "transaction_counterparty",
    } <= claim_types

    assert {get_value(claim, "claim_group_hint") for claim in claims} == {
        raw_source["raw_payload"]["source_event_ref"]
    }
    assert {get_value(claim, "source_sequence") for claim in claims} == {
        raw_source["raw_payload"]["source_sequence"]
    }
    assert len({get_value(claim, "normalizer_version") for claim in claims}) == 1
    assert get_value(claims[0], "normalizer_version")


def test_draft_normalization_carries_source_sequence_and_pick_claims():
    raw_source = load_json_fixture("nba_api_draft_raw.json")
    claims = _normalize(_capture_source_record("nba_api_draft_raw.json"))

    claim_types = {get_value(claim, "claim_type") for claim in claims}
    assert {"pick_identity", "pick_draft_year", "pick_round"} <= claim_types
    assert "player_name" in claim_types
    assert {get_value(claim, "claim_group_hint") for claim in claims} == {
        raw_source["raw_payload"]["source_event_ref"]
    }
    assert {get_value(claim, "source_sequence") for claim in claims} == {
        raw_source["raw_payload"]["source_sequence"]
    }
    assert len({get_value(claim, "normalizer_version") for claim in claims}) == 1
