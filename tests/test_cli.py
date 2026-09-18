"""Tests for the lineage CLI."""

import json
import pathlib
import subprocess
import sys

from lineage.cli import VERBS

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FEED_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "nba_player_movement_mem_2025_26.json"


def test_help_lists_all_verbs():
    result = subprocess.run(
        [sys.executable, "-m", "lineage.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    for verb in VERBS:
        assert verb in result.stdout


def test_validate_runs_offline_against_the_fixture():
    result = subprocess.run(
        [sys.executable, "-m", "lineage.cli", "validate", "--feed-fixture", str(FEED_FIXTURE)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Errors (0):" in result.stdout


def test_validate_strict_exits_nonzero_on_current_data():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lineage.cli",
            "validate",
            "--feed-fixture",
            str(FEED_FIXTURE),
            "--strict",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


def test_export_then_render_offline_against_the_fixture(tmp_path):
    graph_path = tmp_path / "graph.json"
    svg_path = tmp_path / "graph.svg"

    export_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lineage.cli",
            "export",
            "--feed-fixture",
            str(FEED_FIXTURE),
            "--out",
            str(graph_path),
        ],
        capture_output=True,
        text=True,
    )
    assert export_result.returncode == 0
    assert graph_path.exists()

    render_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "lineage.cli",
            "render",
            "--in",
            str(graph_path),
            "--out",
            str(svg_path),
        ],
        capture_output=True,
        text=True,
    )
    assert render_result.returncode == 0
    assert svg_path.exists()
    assert svg_path.read_text().startswith("<svg")


def test_load_runs_fetch_free_offline_pipeline_against_the_fixture():
    # `load` with a fixture writes to the repo's own exports/ dir (as `mise run load` does);
    # exports/ is gitignored, so this just needs to succeed and leave both files behind.
    result = subprocess.run(
        [sys.executable, "-m", "lineage.cli", "load", "--feed-fixture", str(FEED_FIXTURE)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (REPO_ROOT / "exports" / "graph.json").exists()
    assert (REPO_ROOT / "exports" / "graph.svg").exists()


def test_derive_is_implemented_and_reports_bad_input_without_a_traceback(tmp_path):
    fixture = tmp_path / "feed.json"
    fixture.write_text(json.dumps({"NBA_Player_Movement": {"rows": []}}))

    result = subprocess.run(
        [sys.executable, "-m", "lineage.cli", "derive", "--feed-fixture", str(fixture)],
        capture_output=True,
        text=True,
    )

    # The captured feed cannot resolve every curated snapshot player, so derive stops with
    # a readable message rather than loading a half-built graph.
    assert result.returncode == 1
    assert "derive failed:" in result.stderr
    assert "Traceback" not in result.stderr
