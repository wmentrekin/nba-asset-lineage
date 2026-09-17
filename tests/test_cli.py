"""Tests for the lineage CLI skeleton."""

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


@pytest.mark.parametrize("verb", ["migrate", "fetch", "derive", "validate", "export", "render", "load"])
def test_stub_verb_exits_2(verb):
    result = subprocess.run(
        [sys.executable, "-m", "lineage.cli", verb],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "not implemented yet" in result.stdout
