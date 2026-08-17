import json
import os
from pathlib import Path

import pytest

from foundation.live_sources import build_locked_source_rows
from foundation.source_payloads import (
    CapturedResponse,
    SourceBundleError,
    canonical_json_bytes,
    capture_source_bundle,
    capture_source_bundle_from_fetcher,
    load_source_bundle,
)


def _private_root(tmp_path: Path) -> Path:
    root = tmp_path / "refresh"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def _movement_response() -> CapturedResponse:
    return CapturedResponse(
        stable_key="movement",
        source_url="https://example.test/movement.json",
        media_type="application/json",
        body=json.dumps(
            {"rows": [{"TEAM_ID": "1610612763", "TRANSACTION_DATE": "2026-07-01", "PLAYER_NAME": "Test Player", "TRANSACTION_TYPE": "Signing", "TRANSACTION_DESCRIPTION": "Memphis Grizzlies signed Test Player."}]}
        ).encode(),
        response_metadata={"status_code": 200, "content_type": "application/json"},
    )


def test_capture_validates_deterministic_bundle_and_normalizes_exact_bytes(tmp_path: Path) -> None:
    root = _private_root(tmp_path)
    bundle = capture_source_bundle(
        root / "movement",
        source_kind="nba_player_movement",
        source_scope={"team_code": "MEM"},
        normalization_config={"endpoint_url": "https://example.test/movement.json"},
        responses=[_movement_response()],
        captured_at="2026-08-17T00:00:00Z",
    )

    reread = load_source_bundle(root / "movement", expected_digest=bundle.digest, expected_source_kind="nba_player_movement")
    first = build_locked_source_rows(reread)
    second = build_locked_source_rows(reread)

    assert reread.bodies["movement"] == _movement_response().body
    assert [row.model_dump(mode="json") for row in first[0]] == [row.model_dump(mode="json") for row in second[0]]
    assert [row.model_dump(mode="json") for row in first[1]] == [row.model_dump(mode="json") for row in second[1]]


def test_load_rejects_tampering_and_scope_mismatch_before_normalization(tmp_path: Path) -> None:
    root = _private_root(tmp_path)
    bundle = capture_source_bundle(
        root / "movement",
        source_kind="nba_player_movement",
        source_scope={"team_code": "MEM"},
        normalization_config={},
        responses=[_movement_response()],
        captured_at="2026-08-17T00:00:00Z",
    )

    with pytest.raises(SourceBundleError, match="scope"):
        load_source_bundle(bundle.path, expected_source_scope={"team_code": "BOS"})
    (bundle.path / "bodies" / "movement.bin").write_bytes(b"tampered")
    with pytest.raises(SourceBundleError, match="does not match"):
        load_source_bundle(bundle.path, expected_digest=bundle.digest)


def test_capture_is_atomic_and_fetches_each_url_once(tmp_path: Path) -> None:
    root = _private_root(tmp_path)
    calls: list[str] = []

    def fetcher(url: str) -> tuple[bytes, dict[str, object]]:
        calls.append(url)
        return b"<html></html>", {"status_code": 200}

    bundle = capture_source_bundle_from_fetcher(
        root / "bref",
        source_kind="bref_transactions",
        source_scope={"team_code": "MEM"},
        normalization_config={"season_end_year_by_stable_key": {"season-2026": 2026}},
        requests=[("season-2026", "https://example.test/2026", "text/html")],
        fetcher=fetcher,
        captured_at="2026-08-17T00:00:00Z",
    )

    assert calls == ["https://example.test/2026"]
    assert bundle.path.exists()
    with pytest.raises(SourceBundleError, match="Duplicate stable_key"):
        capture_source_bundle(
            root / "partial",
            source_kind="bref_transactions",
            source_scope={"team_code": "MEM"},
            normalization_config={},
            responses=[
                CapturedResponse("same", "https://example.test/a", "text/html", b"a"),
                CapturedResponse("same", "https://example.test/b", "text/html", b"b"),
            ],
        )
    assert not (root / "partial").exists()


def test_load_rejects_path_traversal_duplicate_metadata_and_manifest_drift(tmp_path: Path) -> None:
    root = _private_root(tmp_path)
    bundle = capture_source_bundle(
        root / "movement",
        source_kind="nba_player_movement",
        source_scope={"team_code": "MEM"},
        normalization_config={},
        responses=[_movement_response()],
        captured_at="2026-08-17T00:00:00Z",
    )
    manifest_path = bundle.path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["items"][0]["relative_body_path"] = "../movement.bin"
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(SourceBundleError, match="Unsafe relative"):
        load_source_bundle(bundle.path)
    with pytest.raises(SourceBundleError, match="Unsupported response metadata"):
        capture_source_bundle(
            root / "bad-metadata",
            source_kind="nba_player_movement",
            source_scope={"team_code": "MEM"},
            normalization_config={},
            responses=[CapturedResponse("bad", "https://example.test", "text/plain", b"x", {"cookie": "no"})],
        )
