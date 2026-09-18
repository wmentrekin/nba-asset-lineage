"""Tests for the lineage CLI skeleton."""

import json
import subprocess
import sys

import pytest

from lineage.cli import VERBS


def test_help_lists_all_verbs():
    result = subprocess.run(
        [sys.executable, "-m", "lineage.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    for verb in VERBS:
        assert verb in result.stdout


@pytest.mark.parametrize("verb", ["validate", "export", "render", "load"])
def test_stub_verb_exits_2(verb):
    result = subprocess.run(
        [sys.executable, "-m", "lineage.cli", verb],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "not implemented yet" in result.stdout


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
