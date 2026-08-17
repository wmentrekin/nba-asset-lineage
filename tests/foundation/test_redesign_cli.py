import json
import os
import sys
from pathlib import Path

import pytest

import redesign_cli
from foundation.source_payloads import CapturedResponse, SourceBundleError, capture_source_bundle


def _private_root(tmp_path: Path) -> Path:
    root = tmp_path / "refresh"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def _movement_bundle(tmp_path: Path):
    return capture_source_bundle(
        _private_root(tmp_path) / "movement",
        source_kind="nba_player_movement",
        source_scope={"team_code": "MEM"},
        normalization_config={"endpoint_url": "https://example.test/movement"},
        responses=[
            CapturedResponse(
                "movement",
                "https://example.test/movement",
                "application/json",
                json.dumps(
                    {"transactions": [{"TEAM_ID": 1610612763, "TRANSACTION_DATE": "2026-07-01", "TRANSACTION_TYPE": "Signing", "TRANSACTION_DESCRIPTION": "Memphis Grizzlies signed Test Player."}]}
                ).encode(),
            )
        ],
        captured_at="2026-08-17T00:00:00Z",
    )


def test_locked_source_cli_rejects_digest_before_database_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _movement_bundle(tmp_path)
    monkeypatch.setattr(redesign_cli, "load_database_url", lambda: pytest.fail("must not load database URL"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "redesign_cli.py",
            "load-nba-player-movement",
            "--payload-bundle-path",
            str(bundle.path),
            "--expected-bundle-sha256",
            "0" * 64,
            "--execute",
        ],
    )

    with pytest.raises(SourceBundleError, match="digest"):
        redesign_cli.main()


def test_locked_source_cli_preview_uses_bundle_without_database_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _movement_bundle(tmp_path)
    monkeypatch.setattr(redesign_cli, "load_database_url", lambda: pytest.fail("preview must not load database URL"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "redesign_cli.py",
            "preview-nba-player-movement",
            "--payload-bundle-path",
            str(bundle.path),
            "--expected-bundle-sha256",
            bundle.digest,
        ],
    )

    redesign_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["bundle_sha256"] == bundle.digest
    assert payload["dry_run"] is True
    assert payload["writes_to_database"] is False
