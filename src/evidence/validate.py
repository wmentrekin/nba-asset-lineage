from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from typing import Iterable

from evidence.models import NormalizedClaim, OverrideRecord, SourceRecord


@dataclass(frozen=True)
class ValidationReport:
    source_record_count: int
    normalized_claim_count: int
    override_count: int
    duplicate_source_records_skipped: int
    claim_count_by_type: dict[str, int]
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_stage1_rows(
    *,
    source_records: Iterable[SourceRecord],
    normalized_claims: Iterable[NormalizedClaim],
    overrides: Iterable[OverrideRecord],
) -> ValidationReport:
    source_records_list = list(source_records)
    normalized_claims_list = list(normalized_claims)
    overrides_list = list(overrides)
    errors: list[str] = []
    warnings: list[str] = []

    source_record_id_counts = Counter(record.source_record_id for record in source_records_list)
    source_record_ids = set(source_record_id_counts)

    for record in source_records_list:
        if not record.payload_hash:
            errors.append(f"source_record missing payload_hash: {record.source_record_id}")
        if not record.source_locator:
            errors.append(f"source_record missing source_locator: {record.source_record_id}")
        if not record.parser_version:
            errors.append(f"source_record missing parser_version: {record.source_record_id}")

    for claim in normalized_claims_list:
        if claim.source_record_id not in source_record_ids:
            errors.append(f"claim references unknown source_record_id: {claim.claim_id}")
        if not claim.claim_group_hint:
            warnings.append(f"claim missing claim_group_hint: {claim.claim_id}")
        if claim.source_sequence is None:
            warnings.append(f"claim missing source_sequence: {claim.claim_id}")
        if not claim.normalizer_version:
            errors.append(f"claim missing normalizer_version: {claim.claim_id}")

    for override in overrides_list:
        if not override.reason:
            errors.append(f"override missing reason: {override.override_id}")
        if not override.target_key:
            errors.append(f"override missing target_key: {override.override_id}")

    duplicate_source_records_skipped = 0
    for record in source_records_list:
        duplicate_count = getattr(record, "duplicate_count", 1) or 1
        if duplicate_count > 1:
            duplicate_source_records_skipped += duplicate_count - 1
    if duplicate_source_records_skipped == 0:
        duplicate_source_records_skipped = sum(count - 1 for count in source_record_id_counts.values() if count > 1)
    claim_count_by_type = dict(Counter(claim.claim_type for claim in normalized_claims_list))

    return ValidationReport(
        source_record_count=len(source_record_ids),
        normalized_claim_count=len(normalized_claims_list),
        override_count=len(overrides_list),
        duplicate_source_records_skipped=duplicate_source_records_skipped,
        claim_count_by_type=claim_count_by_type,
        errors=errors,
        warnings=warnings,
    )


validate_evidence = validate_stage1_rows
build_validation_report = validate_stage1_rows
