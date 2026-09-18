"""Tests for lineage.validate: findings on the captured feed and on planted breakage."""

import dataclasses

import pytest

from lineage.derive import build_graph
from lineage.validate import (
    Finding,
    format_report,
    validate_graph,
)


@pytest.fixture
def graph(feed_payload, resolvable_inputs):
    snapshot, pick_events, corrections = resolvable_inputs
    return build_graph(feed_payload, snapshot, pick_events, corrections)


@pytest.fixture
def snapshot_and_pick_events(resolvable_inputs):
    snapshot, pick_events, _ = resolvable_inputs
    return snapshot, pick_events


def test_current_data_has_no_errors_and_the_expected_warning_counts(
    graph, snapshot_and_pick_events
):
    snapshot, pick_events = snapshot_and_pick_events

    findings = validate_graph(graph, snapshot, pick_events)

    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warn"]
    assert errors == []

    by_code = {}
    for finding in warnings:
        by_code[finding.code] = by_code.get(finding.code, 0) + 1
    assert by_code == {"W1": 4, "W2": 2, "W3": 10}


def test_report_groups_findings_by_level_with_counts(graph, snapshot_and_pick_events):
    snapshot, pick_events = snapshot_and_pick_events
    findings = validate_graph(graph, snapshot, pick_events)

    report = format_report(findings)

    assert "Errors (0):" in report
    assert "Warnings (16):" in report
    assert "[W1]" in report and "[W2]" in report and "[W3]" in report


def test_a_planted_discontinuity_is_an_e1_error(graph, snapshot_and_pick_events):
    snapshot, pick_events = snapshot_and_pick_events
    landale_movement = next(
        m
        for m in graph.movements
        if m.asset_type == "player" and m.asset_id == "1629111" and m.from_holder == "MEM"
    )
    broken = dataclasses.replace(landale_movement, from_holder="BOS")
    graph.movements[graph.movements.index(landale_movement)] = broken

    findings = validate_graph(graph, snapshot, pick_events)

    errors = [f for f in findings if f.level == "error"]
    assert any(f.code == "E1" for f in errors)


def test_a_planted_duplicate_movement_is_an_e2_error(graph, snapshot_and_pick_events):
    snapshot, pick_events = snapshot_and_pick_events
    graph.movements.append(graph.movements[0])

    findings = validate_graph(graph, snapshot, pick_events)

    errors = [f for f in findings if f.level == "error"]
    assert any(f.code == "E2" for f in errors)


def test_strict_exits_nonzero_on_the_current_data_via_run_validate(tmp_path, monkeypatch):
    import pathlib

    from lineage.validate import run_validate

    fixture_path = (
        pathlib.Path(__file__).resolve().parent
        / "fixtures"
        / "nba_player_movement_mem_2025_26.json"
    )
    data_dir = pathlib.Path(__file__).resolve().parent.parent / "data"

    assert run_validate(str(fixture_path), data_dir, strict=False) == 0
    assert run_validate(str(fixture_path), data_dir, strict=True) == 1
