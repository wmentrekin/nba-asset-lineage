from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

from foundation.refresh_artifacts import (
    FIXTURE_SLOT_NAMES,
    SOURCE_KINDS,
    RefreshArtifactError,
    RefreshReconciliation,
    RefreshRequest,
    SealedRefreshPlan,
    load_refresh_plan,
    load_refresh_request,
    load_reconciliation,
    mutation_plan_from_payload,
    mutation_plan_payload,
    validate_artifact_chain,
    write_reconciliation,
    write_refresh_plan,
    write_refresh_request,
)
from foundation.refresh_mutations import FoundationMutationPlan, UpsertRows
from foundation.refresh_safety import ApprovedRefreshPlans, ApprovedRefreshStep, create_refresh_artifact_directory
from foundation.refresh_projection import APPROVED_PROJECTION_ORDER
from foundation.source_payloads import CapturedResponse, capture_source_bundle


def _plan() -> FoundationMutationPlan:
    return FoundationMutationPlan(
        (UpsertRows("source_record", ({"source_record_id": "fixture:one", "source_system": "fixture"},)),),
        "2026-08-17T00:00:00Z",
    )


def test_closed_mutation_codec_round_trips_and_rejects_unknown_policy() -> None:
    payload = mutation_plan_payload(_plan())
    assert mutation_plan_from_payload(payload) == _plan()
    payload["operations"][0]["policies"] = [["source_system", "arbitrary_sql"]]
    with pytest.raises(RefreshArtifactError, match="policies"):
        mutation_plan_from_payload(payload)


def test_sealed_chain_rejects_fixture_or_bundle_drift_before_later_connection(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir(mode=0o700)
    directory = create_refresh_artifact_directory(root, "artifact-fixture")
    (directory / "bundles").mkdir(mode=0o700)
    (directory / "fixtures").mkdir(mode=0o700)
    bundle_digests = {}
    for kind in SOURCE_KINDS:
        bundle = capture_source_bundle(
            directory / "bundles" / kind,
            source_kind=kind,
            source_scope={"fixture": kind},
            normalization_config={},
            responses=[CapturedResponse("body", "https://fixture.invalid/", "application/json", kind.encode())],
            captured_at="2026-08-17T00:00:00Z",
        )
        bundle_digests[kind] = bundle.digest
    fixture_digests = {}
    for name in FIXTURE_SLOT_NAMES:
        body = f'{{"fixture":"{name}"}}'.encode()
        path = directory / "fixtures" / f"{name}.json"
        path.write_bytes(body)
        path.chmod(0o600)
        fixture_digests[name] = sha256(body).hexdigest()

    request = RefreshRequest("artifact-fixture", date(2026, 8, 16), bundle_digests, fixture_digests)
    write_refresh_request(directory, request)
    # The aggregate values are derived from the fixed slots, not supplied as
    # arbitrary caller-selected files or selectors.
    from foundation.refresh_artifacts import _set_digest
    reconciliation = RefreshReconciliation(request.digest, "a" * 64, "b" * 64, _set_digest("fixtures", fixture_digests), _set_digest("bundles", bundle_digests))
    write_reconciliation(directory, reconciliation)
    plans = ApprovedRefreshPlans(tuple(ApprovedRefreshStep(name, _plan()) for name in APPROVED_PROJECTION_ORDER))
    sealed = SealedRefreshPlan(request.digest, reconciliation.digest, reconciliation.baseline_digest, reconciliation.historical_checksum, plans)
    write_refresh_plan(directory, sealed)
    assert validate_artifact_chain(directory)[2].digest == sealed.digest

    fixture = directory / "fixtures" / f"{FIXTURE_SLOT_NAMES[0]}.json"
    fixture.write_bytes(b"tampered")
    fixture.chmod(0o600)
    with pytest.raises(RefreshArtifactError, match="drifted"):
        load_refresh_request(directory)


def test_plan_rejects_reordered_steps_and_broken_request_binding(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir(mode=0o700)
    directory = create_refresh_artifact_directory(root, "plan-bindings")
    # Artifact parsing rejects chain drift before this test needs any DB fake.
    request = RefreshRequest("plan-bindings", date(2026, 8, 16), {kind: "a" * 64 for kind in SOURCE_KINDS}, {name: "b" * 64 for name in FIXTURE_SLOT_NAMES})
    reconciliation = RefreshReconciliation(request.digest, "c" * 64, "d" * 64, "e" * 64, "f" * 64)
    plans = ApprovedRefreshPlans(tuple(ApprovedRefreshStep(name, _plan()) for name in APPROVED_PROJECTION_ORDER))
    sealed = SealedRefreshPlan(request.digest, reconciliation.digest, "c" * 64, "d" * 64, plans)
    payload = __import__("foundation.refresh_artifacts", fromlist=["refresh_plan_payload"]).refresh_plan_payload(sealed)
    payload["steps"][0], payload["steps"][1] = payload["steps"][1], payload["steps"][0]
    # Reordered payload is not a representable closed plan even if a caller
    # could otherwise recalculate its outer digest.
    import json
    (directory / "refresh-plan.json").write_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    (directory / "refresh-plan.json").chmod(0o600)
    with pytest.raises(RefreshArtifactError, match="invalid|closed|plan"):
        load_refresh_plan(directory, request=request, reconciliation=reconciliation)
