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


def test_snapshot_capture_cli_requires_execute_before_database_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(redesign_cli, "load_database_url", lambda: pytest.fail("must not load database URL"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "redesign_cli.py",
            "capture-foundation-refresh-snapshot",
            "--repo-root",
            str(tmp_path),
            "--refresh-id",
            "refresh-2026-08-17",
        ],
    )

    with pytest.raises(ValueError, match="requires --execute"):
        redesign_cli.main()
    assert not (tmp_path / "tmp").exists()


@pytest.mark.parametrize(
    "command",
    [
        "capture-foundation-refresh-snapshot",
        "record-refresh-approval",
        "preview-refresh-projection",
        "run-approved-foundation-refresh",
        "restore-foundation-refresh-snapshot",
    ],
)
def test_refresh_artifact_commands_are_available_from_cli_help(
    command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["redesign_cli.py", command, "--help"])
    with pytest.raises(SystemExit) as error:
        redesign_cli.main()

    assert error.value.code == 0
    assert command in capsys.readouterr().out


@pytest.mark.parametrize(
    ("command", "extra"),
    [
        ("preview-refresh-projection", []),
        ("run-approved-foundation-refresh", ["--execute"]),
        ("restore-foundation-refresh-snapshot", ["--execute"]),
    ],
)
def test_sealed_operational_commands_reject_missing_artifacts_before_database_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    extra: list[str],
) -> None:
    monkeypatch.setattr(redesign_cli, "load_database_url", lambda: pytest.fail("artifact validation must precede database lookup"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["redesign_cli.py", command, "--artifact-directory", str(tmp_path / "missing"), *extra],
    )
    with pytest.raises(Exception, match="Artifact|artifact|missing"):
        redesign_cli.main()


@pytest.mark.parametrize("command", ["run-approved-foundation-refresh", "restore-foundation-refresh-snapshot"])
def test_sealed_destructive_commands_require_execute_before_artifact_or_database_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    monkeypatch.setattr(redesign_cli, "load_database_url", lambda: pytest.fail("must not load database URL"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["redesign_cli.py", command, "--artifact-directory", str(tmp_path / "missing")],
    )
    with pytest.raises(ValueError, match="requires --execute"):
        redesign_cli.main()


def test_sealed_runner_rejects_report_blockers_before_connection_or_runner_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_directory = tmp_path / "untrusted-artifact-leaf"
    marker = object()
    monkeypatch.setattr(redesign_cli, "validate_artifact_chain", lambda _: (marker, marker, marker))
    monkeypatch.setattr(
        redesign_cli,
        "load_sealed_projection_report",
        lambda *_args, **_kwargs: {"blockers": ["unresolved candidate alias"]},
    )
    monkeypatch.setattr(redesign_cli, "load_foundation_snapshot", lambda *_: pytest.fail("snapshot load must follow blocker rejection"))
    monkeypatch.setattr(redesign_cli, "load_database_url", lambda: pytest.fail("blocker rejection must precede database lookup"))
    monkeypatch.setattr(redesign_cli.psycopg, "connect", lambda *_args, **_kwargs: pytest.fail("blocker rejection must precede connection"))
    monkeypatch.setattr(redesign_cli, "run_approved_foundation_refresh", lambda *_args, **_kwargs: pytest.fail("blocker rejection must precede runner"))

    with pytest.raises(Exception, match="contains blockers"):
        redesign_cli._run_sealed_refresh(artifact_directory)


@pytest.mark.parametrize(
    ("command", "extra", "adapter", "expected"),
    [
        ("preview-refresh-projection", [], "_preview_sealed_refresh", {"status": "projected"}),
        ("run-approved-foundation-refresh", ["--execute"], "_run_sealed_refresh", {"status": "completed"}),
        ("restore-foundation-refresh-snapshot", ["--execute"], "_restore_sealed_refresh", {"status": "restored"}),
    ],
)
def test_sealed_cli_commands_expose_only_artifact_directory_to_injected_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    extra: list[str],
    adapter: str,
    expected: dict[str, str],
) -> None:
    observed: list[Path] = []

    def fake_adapter(directory: Path) -> dict[str, str]:
        observed.append(directory)
        return expected

    monkeypatch.setattr(redesign_cli, adapter, fake_adapter)
    artifact_directory = tmp_path / "only-artifact-input"
    monkeypatch.setattr(
        sys,
        "argv",
        ["redesign_cli.py", command, "--artifact-directory", str(artifact_directory), *extra],
    )
    redesign_cli.main()

    assert observed == [artifact_directory]
    assert json.loads(capsys.readouterr().out) == expected
