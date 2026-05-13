from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import foundation.two_way_status as two_way_status
from foundation.two_way_status import (
    DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
    TwoWayPlayerIdentity,
    TwoWaySnapshotPlayer,
    TwoWayStatusFixture,
    TwoWayStatusFixtureRow,
    build_two_way_status_preview,
    interval_matches_snapshot,
    load_two_way_status,
    load_two_way_status_fixture,
)


def make_fixture(rows: list[TwoWayStatusFixtureRow]) -> TwoWayStatusFixture:
    return TwoWayStatusFixture(
        fixture_id="seed_v1",
        team_code="MEM",
        coverage_start=date(2017, 7, 1),
        coverage_end=None,
        coverage_statement="test fixture",
        source_set=[{"label": "test", "locator": "https://example.test"}],
        confidence_rubric={"high": ["official"], "medium": ["secondary"], "low": ["ambiguous"]},
        rows=rows,
    )


def make_row(
    *,
    status_id: str = "row-1",
    player_name: str = "Test Player",
    player_id: str | None = "player:test-player",
    team_code: str = "MEM",
    start_date: date = date(2024, 1, 10),
    end_date: date | None = date(2024, 2, 1),
    confidence: str = "high",
    loadable: bool = True,
) -> TwoWayStatusFixtureRow:
    return TwoWayStatusFixtureRow(
        status_id=status_id,
        player_name=player_name,
        player_id=player_id,
        team_code=team_code,
        start_date=start_date,
        end_date=end_date,
        source_urls=["https://example.test/source"],
        confidence=confidence,  # type: ignore[arg-type]
        loadable=loadable,
    )


def test_interval_projection_uses_inclusive_start_and_exclusive_end() -> None:
    row = make_row(start_date=date(2024, 1, 10), end_date=date(2024, 2, 1))

    assert interval_matches_snapshot(
        row,
        TwoWaySnapshotPlayer(
            snapshot_id="start",
            snapshot_date=date(2024, 1, 10),
            team_code="MEM",
            player_id="player:test-player",
        ),
    )
    assert not interval_matches_snapshot(
        row,
        TwoWaySnapshotPlayer(
            snapshot_id="end",
            snapshot_date=date(2024, 2, 1),
            team_code="MEM",
            player_id="player:test-player",
        ),
    )


def test_open_ended_interval_projects_through_latest_matching_snapshot() -> None:
    report = build_two_way_status_preview(
        fixture=make_fixture([make_row(end_date=None)]),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[TwoWayPlayerIdentity(player_id="player:test-player", display_name="Test Player")],
        snapshot_players=[
            TwoWaySnapshotPlayer(
                snapshot_id="snapshot:before",
                snapshot_date=date(2024, 1, 9),
                team_code="MEM",
                player_id="player:test-player",
            ),
            TwoWaySnapshotPlayer(
                snapshot_id="snapshot:latest",
                snapshot_date=date(2026, 4, 15),
                team_code="MEM",
                player_id="player:test-player",
            ),
        ],
    )

    assert report.projected_two_way_rows == 1
    assert report.rows[0].matched_snapshot_ids == ["snapshot:latest"]


def test_conversion_day_boundary_excludes_end_date_snapshot() -> None:
    report = build_two_way_status_preview(
        fixture=make_fixture([make_row(start_date=date(2024, 1, 10), end_date=date(2024, 1, 20))]),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[TwoWayPlayerIdentity(player_id="player:test-player", display_name="Test Player")],
        snapshot_players=[
            TwoWaySnapshotPlayer(
                snapshot_id="snapshot:two-way",
                snapshot_date=date(2024, 1, 19),
                team_code="MEM",
                player_id="player:test-player",
            ),
            TwoWaySnapshotPlayer(
                snapshot_id="snapshot:standard",
                snapshot_date=date(2024, 1, 20),
                team_code="MEM",
                player_id="player:test-player",
            ),
        ],
    )

    assert report.rows[0].matched_snapshot_ids == ["snapshot:two-way"]


def test_identity_resolution_blocks_unresolved_ambiguous_and_mismatched_rows() -> None:
    report = build_two_way_status_preview(
        fixture=make_fixture(
            [
                make_row(status_id="missing-id", player_id="player:missing"),
                make_row(status_id="ambiguous-name", player_id=None, player_name="Shared Name"),
                make_row(status_id="mismatch", player_id="player:test-player", player_name="Wrong Name"),
            ]
        ),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[
            TwoWayPlayerIdentity(player_id="player:test-player", display_name="Test Player"),
            TwoWayPlayerIdentity(player_id="player:shared-a", display_name="Shared Name"),
            TwoWayPlayerIdentity(player_id="player:shared-b", display_name="Shared Name"),
        ],
        snapshot_players=[],
    )

    assert report.blocked_rows == 3
    assert [row.identity_status for row in report.rows] == ["unresolved", "ambiguous", "mismatch"]
    assert all(not row.ready_for_load for row in report.rows)


def test_identity_resolution_ignores_trailing_two_way_status_suffix() -> None:
    report = build_two_way_status_preview(
        fixture=make_fixture([make_row(player_id="player:javon-small-tw", player_name="Javon Small")]),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[TwoWayPlayerIdentity(player_id="player:javon-small-tw", display_name="Javon Small (TW)")],
        snapshot_players=[
            TwoWaySnapshotPlayer(
                snapshot_id="snapshot:1",
                snapshot_date=date(2025, 10, 1),
                team_code="MEM",
                player_id="player:javon-small-tw",
            )
        ],
    )

    assert report.blocked_rows == 0
    assert report.ready_rows == 1
    assert report.rows[0].resolved_display_name == "Javon Small (TW)"


def test_preview_reports_non_matching_interval_as_warning_not_blocker() -> None:
    report = build_two_way_status_preview(
        fixture=make_fixture([make_row()]),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[TwoWayPlayerIdentity(player_id="player:test-player", display_name="Test Player")],
        snapshot_players=[],
    )

    assert report.blocked_rows == 0
    assert report.warning_rows == 1
    assert report.rows[0].ready_for_load
    assert "no matching snapshot-player rows" in report.rows[0].warnings[0]


def test_medium_confidence_loadable_row_is_blocked() -> None:
    report = build_two_way_status_preview(
        fixture=make_fixture([make_row(confidence="medium", loadable=True)]),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[TwoWayPlayerIdentity(player_id="player:test-player", display_name="Test Player")],
        snapshot_players=[],
    )

    assert report.blocked_rows == 1
    assert "only high-confidence rows may be loadable" in report.rows[0].issues


def test_fixture_validation_blocks_filtered_out_team_mismatch_rows() -> None:
    report = build_two_way_status_preview(
        fixture=make_fixture([make_row(status_id="bad-team", team_code="BOS")]),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[TwoWayPlayerIdentity(player_id="player:test-player", display_name="Test Player")],
        snapshot_players=[],
    )

    assert report.rows == []
    assert report.blocked_rows == 1
    assert any("row team_code BOS does not match fixture team MEM" in warning for warning in report.warnings)


def test_overlapping_loadable_intervals_block_preview_and_dedupe_projection() -> None:
    report = build_two_way_status_preview(
        fixture=make_fixture(
            [
                make_row(status_id="interval-a", start_date=date(2024, 1, 1), end_date=date(2024, 2, 1)),
                make_row(status_id="interval-b", start_date=date(2024, 1, 15), end_date=date(2024, 3, 1)),
            ]
        ),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[TwoWayPlayerIdentity(player_id="player:test-player", display_name="Test Player")],
        snapshot_players=[
            TwoWaySnapshotPlayer(
                snapshot_id="snapshot:overlap",
                snapshot_date=date(2024, 1, 20),
                team_code="MEM",
                player_id="player:test-player",
            )
        ],
    )

    assert report.blocked_rows == 1
    assert report.projected_two_way_rows == 1
    assert any("overlapping loadable two-way intervals" in warning for warning in report.warnings)


def test_load_two_way_status_resets_then_applies_current_fixture_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = make_fixture([make_row()])
    preview = build_two_way_status_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[TwoWayPlayerIdentity(player_id="player:test-player", display_name="Test Player")],
        snapshot_players=[
            TwoWaySnapshotPlayer(
                snapshot_id="snapshot:1",
                snapshot_date=date(2024, 1, 10),
                team_code="MEM",
                player_id="player:test-player",
            )
        ],
    )
    state = {
        ("snapshot:1", "player:test-player"): "standard",
        ("snapshot:1", "player:stale-two-way"): "two_way",
    }
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def commit(self) -> None:
            calls.append("commit")

    def fake_connect(*args: object, **kwargs: object) -> FakeConnection:
        return FakeConnection()

    def fake_reset(*args: object, **kwargs: object) -> int:
        calls.append("reset")
        for key in state:
            state[key] = "standard"
        return len(state)

    def fake_apply(connection: object, pairs: list[tuple[str, str]]) -> int:
        calls.append("apply")
        for pair in pairs:
            state[pair] = "two_way"
        return len(pairs)

    monkeypatch.setattr(two_way_status, "preview_two_way_status", lambda *args, **kwargs: preview)
    monkeypatch.setattr(two_way_status, "load_two_way_status_fixture", lambda path: fixture)
    monkeypatch.setattr(two_way_status.psycopg, "connect", fake_connect)
    monkeypatch.setattr(two_way_status, "reset_two_way_snapshot_players", fake_reset)
    monkeypatch.setattr(two_way_status, "apply_two_way_snapshot_players", fake_apply)

    result = load_two_way_status("postgresql://example", fixture_path=Path("fixture.json"))
    second_result = load_two_way_status("postgresql://example", fixture_path=Path("fixture.json"))

    assert calls == ["reset", "apply", "commit", "reset", "apply", "commit"]
    assert result.reset_rows == 2
    assert result.applied_rows == 1
    assert second_result.applied_rows == 1
    assert state == {
        ("snapshot:1", "player:test-player"): "two_way",
        ("snapshot:1", "player:stale-two-way"): "standard",
    }


def test_load_two_way_status_dry_run_does_not_connect_when_preview_is_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = make_fixture([make_row()])
    preview = build_two_way_status_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[TwoWayPlayerIdentity(player_id="player:test-player", display_name="Test Player")],
        snapshot_players=[
            TwoWaySnapshotPlayer(
                snapshot_id="snapshot:1",
                snapshot_date=date(2024, 1, 10),
                team_code="MEM",
                player_id="player:test-player",
            )
        ],
    )

    monkeypatch.setattr(two_way_status, "preview_two_way_status", lambda *args, **kwargs: preview)
    monkeypatch.setattr(
        two_way_status.psycopg,
        "connect",
        lambda *args, **kwargs: pytest.fail("dry-run should not open a write connection"),
    )

    result = load_two_way_status("postgresql://example", fixture_path=Path("fixture.json"), dry_run=True)

    assert result.dry_run
    assert result.reset_rows == 1
    assert result.applied_rows == 1


def test_load_two_way_status_blocks_live_write_when_preview_has_identity_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = build_two_way_status_preview(
        fixture=make_fixture([make_row(player_id="player:missing")]),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        players=[],
        snapshot_players=[],
    )

    monkeypatch.setattr(two_way_status, "preview_two_way_status", lambda *args, **kwargs: preview)
    monkeypatch.setattr(
        two_way_status.psycopg,
        "connect",
        lambda *args, **kwargs: pytest.fail("blocked preview should not open a write connection"),
    )

    result = load_two_way_status("postgresql://example", fixture_path=Path("fixture.json"))

    assert result.blocked_rows == 1
    assert result.reset_rows == 0
    assert result.applied_rows == 0


def test_default_seed_fixture_contract_loads() -> None:
    fixture = load_two_way_status_fixture(DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH)

    assert fixture.fixture_id == "seed_v1"
    assert fixture.team_code == "MEM"
    assert fixture.coverage_start == date(2017, 7, 1)
    assert len(fixture.rows) > 0
    assert all(row.confidence == "high" for row in fixture.rows if row.loadable)
