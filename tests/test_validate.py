"""Tests for lineage.validate: findings on the captured feed and on planted breakage."""

import dataclasses

import pytest

from lineage.derive import CONTRACT_DRAFT_RIGHTS, build_graph
from lineage.validate import (
    format_report,
    validate_graph,
)


@pytest.fixture
def graph(feed_payload, resolvable_inputs):
    snapshot, curated, corrections = resolvable_inputs
    return build_graph(feed_payload, snapshot, curated, corrections)


@pytest.fixture
def snapshot_and_curated(resolvable_inputs):
    snapshot, curated, _ = resolvable_inputs
    return snapshot, curated


def test_current_data_has_no_errors_and_the_expected_warning_counts(
    graph, snapshot_and_curated
):
    snapshot, curated = snapshot_and_curated

    findings = validate_graph(graph, snapshot, curated)

    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warn"]
    assert errors == []

    by_code = {}
    for finding in warnings:
        by_code[finding.code] = by_code.get(finding.code, 0) + 1
    # W1: Trade-2025037, Trade-2026014 (above). W2: none (Saunders has his real person id).
    # W3: 10 unverified snapshot players. W5: three trades whose footnotes flag an uncurated
    # asset (2025037, 2026006, 2026014). W6: six unverified snapshot picks (the 2nds with no
    # source either way). W7: none (no camp cuts in the captured fixture).
    assert by_code == {"W1": 2, "W3": 10, "W5": 3, "W6": 6}


def test_report_groups_findings_by_level_with_counts(graph, snapshot_and_curated):
    snapshot, curated = snapshot_and_curated
    findings = validate_graph(graph, snapshot, curated)

    report = format_report(findings)

    assert "Errors (0):" in report
    assert "Warnings (21):" in report
    assert all(f"[{code}]" in report for code in ("W1", "W3", "W5", "W6"))


def test_camp_cut_waivers_raise_w7_warnings_and_no_errors(
    feed_payload_with_camp_cuts, resolvable_inputs
):
    snapshot, curated, corrections = resolvable_inputs
    graph = build_graph(feed_payload_with_camp_cuts, snapshot, curated, corrections)

    findings = validate_graph(graph, snapshot, curated)

    assert [f for f in findings if f.level == "error"] == []
    w7 = [f for f in findings if f.code == "W7"]
    assert [f.message for f in w7] == [
        "Waive-1154381: skipped waiver of Yuri Collins (1641879): not held by MEM "
        "(camp signing absent from feed)",
        "Waive-1154444: skipped waiver of Lawson Lovering (1643133): not held by MEM "
        "(camp signing absent from feed)",
    ]
    assert all(f.level == "warn" for f in w7)


def test_a_non_waiver_exit_of_an_unheld_player_is_still_an_e1_error(
    feed_payload, resolvable_inputs
):
    snapshot, curated, corrections = resolvable_inputs
    feed_payload["NBA_Player_Movement"]["rows"].append(
        {
            "TEAM_ID": 1610612753.0,  # ORL receives, from MEM
            "GroupSort": "Trade 9100001",
            "PLAYER_ID": 9100001.0,
            "TEAM_SLUG": "magic",
            "PLAYER_SLUG": "test-player",
            "Additional_Sort": 1610612763.0,
            "TRANSACTION_DATE": "2026-09-29T00:00:00",
            "Transaction_Type": "Trade",
            "TRANSACTION_DESCRIPTION": (
                "Orlando Magic received guard Test Player from Memphis Grizzlies."
            ),
        }
    )
    graph = build_graph(feed_payload, snapshot, curated, corrections)

    findings = validate_graph(graph, snapshot, curated)

    assert any(
        f.level == "error" and f.code == "E1" and "9100001" in f.message for f in findings
    )
    assert not [f for f in findings if f.code == "W7"]


def test_a_planted_discontinuity_is_an_e1_error(graph, snapshot_and_curated):
    snapshot, curated = snapshot_and_curated
    landale_movement = next(
        m
        for m in graph.movements
        if m.asset_type == "player" and m.asset_id == "1629111" and m.from_holder == "MEM"
    )
    broken = dataclasses.replace(landale_movement, from_holder="BOS")
    graph.movements[graph.movements.index(landale_movement)] = broken

    findings = validate_graph(graph, snapshot, curated)

    errors = [f for f in findings if f.level == "error"]
    assert any(f.code == "E1" for f in errors)


def test_a_planted_duplicate_movement_is_an_e2_error(graph, snapshot_and_curated):
    snapshot, curated = snapshot_and_curated
    graph.movements.append(graph.movements[0])

    findings = validate_graph(graph, snapshot, curated)

    errors = [f for f in findings if f.level == "error"]
    assert any(f.code == "E2" for f in errors)


def test_a_missing_expiry_for_a_ten_day_is_an_e6_error(graph, snapshot_and_curated):
    snapshot, curated = snapshot_and_curated
    graph.transactions = [t for t in graph.transactions if t.id != "Expire-1139430"]
    graph.movements = [m for m in graph.movements if m.transaction_id != "Expire-1139430"]

    findings = validate_graph(graph, snapshot, curated)

    errors = [f for f in findings if f.level == "error"]
    assert any(f.code == "E6" and "1629646" in f.message for f in errors)


def test_a_draft_selection_missing_draft_rights_is_an_e5_error(graph, snapshot_and_curated):
    snapshot, curated = snapshot_and_curated
    node_id = "Draft-2026-06-23-2026-R1-MEM"
    player_movement = next(
        m
        for m in graph.movements
        if m.transaction_id == node_id and m.asset_type == "player"
    )
    broken = dataclasses.replace(player_movement, contract_type="standard")
    graph.movements[graph.movements.index(player_movement)] = broken

    findings = validate_graph(graph, snapshot, curated)

    errors = [f for f in findings if f.level == "error"]
    assert any(f.code == "E5" and node_id in f.message for f in errors)


def test_a_contract_void_kind_is_allowed_by_e3(graph, snapshot_and_curated):
    snapshot, curated = snapshot_and_curated

    findings = validate_graph(graph, snapshot, curated)

    assert not [f for f in findings if f.code == "E3"]
    assert any(t.kind == "contract_void" for t in graph.transactions)


def test_draft_rights_movement_carries_the_contract_type(graph):
    node_id = "Draft-2026-06-23-2026-R1-MEM"
    player_movement = next(
        m
        for m in graph.movements
        if m.transaction_id == node_id and m.asset_type == "player"
    )

    assert player_movement.contract_type == CONTRACT_DRAFT_RIGHTS


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


def test_pick_horizon_new_origin_is_valid_but_only_for_pick_horizon(graph, snapshot_and_curated):
    snapshot, curated = snapshot_and_curated
    assert not [f for f in validate_graph(graph, snapshot, curated) if f.level == "error"]

    move = next(m for m in graph.movements if m.transaction_id == "Horizon-2033")
    wrong = dataclasses.replace(move, transaction_id="Trade-2025022")
    graph.movements[graph.movements.index(move)] = wrong
    findings = validate_graph(graph, snapshot, curated)
    assert any(f.code == "E1" and "NEW" in f.message for f in findings)
