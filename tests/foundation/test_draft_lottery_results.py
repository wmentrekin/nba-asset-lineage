from __future__ import annotations

from datetime import date
from inspect import getsource
from pathlib import Path

import pytest

import foundation.draft_lottery_results as draft_lottery_results
from foundation.draft_lottery_results import (
    DEFAULT_DRAFT_LOTTERY_RESULTS_FIXTURE_PATH,
    DraftLotteryFixture,
    DraftLotteryFixtureRow,
    ExistingDraftLotteryResult,
    build_draft_lottery_result_rows,
    build_draft_lottery_results_preview,
    load_draft_lottery_results,
    load_draft_lottery_results_fixture,
)


def make_fixture(rows: list[DraftLotteryFixtureRow]) -> DraftLotteryFixture:
    return DraftLotteryFixture(
        fixture_id="seed_v1",
        team_code="MEM",
        coverage_start_year=2016,
        coverage_end_year=2026,
        coverage_statement="test fixture",
        source_set=[{"label": "test", "locator": "https://example.test"}],
        confidence_rubric={"high": ["official"], "medium": ["secondary"], "low": ["ambiguous"]},
        rows=rows,
    )


def make_row(
    *,
    lottery_result_id: str = "draft-lottery-result:mem:2024",
    draft_year: int = 2024,
    team_code: str = "MEM",
    lottery_position: int | None = 7,
    result_pick_slot: int = 9,
    confidence: str = "high",
    loadable: bool = True,
    source_urls: list[str] | None = None,
    source_labels: list[str] | None = None,
    retrieved_at: date | None = date(2026, 5, 13),
) -> DraftLotteryFixtureRow:
    return DraftLotteryFixtureRow(
        lottery_result_id=lottery_result_id,
        draft_year=draft_year,
        lottery_date=date(2024, 5, 12),
        team_code=team_code,
        owner_team_code=team_code,
        original_team_code="MEM",
        lottery_position=lottery_position,
        result_pick_slot=result_pick_slot,
        pre_lottery_odds="7.5%",
        source_urls=source_urls if source_urls is not None else ["https://example.test/source"],
        source_labels=source_labels if source_labels is not None else ["Example source"],
        retrieved_at=retrieved_at,
        confidence=confidence,  # type: ignore[arg-type]
        loadable=loadable,
        notes="test row",
    )


def test_fixture_validation_accepts_source_backed_loadable_rows_and_excludes_non_loadable_rows() -> None:
    fixture = make_fixture(
        [
            make_row(),
            make_row(
                lottery_result_id="draft-lottery-result:mem:2020-bos-from-mem-excluded",
                draft_year=2020,
                loadable=False,
                source_urls=[],
                source_labels=[],
                retrieved_at=None,
            ),
        ]
    )

    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[],
    )

    assert preview.blocked_rows == 0
    assert preview.loadable_rows == 1
    assert preview.ready_rows == 1
    assert preview.rows[1].existing_status == "not_loadable"
    row = build_draft_lottery_result_rows(fixture, preview)[0]
    assert row.lottery_result_id == "draft-lottery-result:mem:2024"
    assert row.owner_team_code == "MEM"
    assert row.original_team_code == "MEM"


def test_missing_source_metadata_blocks_loadable_rows() -> None:
    row = make_row(source_urls=[], source_labels=[], retrieved_at=None)
    row.owner_team_code = None
    row.original_team_code = None
    fixture = make_fixture([row])

    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[],
    )

    assert preview.blocked_rows == 1
    assert "loadable rows require at least one source URL" in preview.rows[0].issues
    assert "loadable rows require at least one source label" in preview.rows[0].issues
    assert "loadable rows require retrieved_at" in preview.rows[0].issues
    assert "loadable rows require owner_team_code" in preview.rows[0].issues
    assert "loadable rows require original_team_code" in preview.rows[0].issues


def test_fixture_validation_blocks_bad_earlier_loadable_row_in_multi_row_fixture() -> None:
    invalid_row = make_row(
        lottery_result_id="draft-lottery-result:mem:2019",
        draft_year=2019,
        source_urls=[],
    )
    valid_non_loadable_row = make_row(
        lottery_result_id="draft-lottery-result:mem:2020-excluded",
        draft_year=2020,
        loadable=False,
    )
    fixture = make_fixture([invalid_row, valid_non_loadable_row])

    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[],
    )

    assert preview.blocked_rows == 1
    assert preview.ready_rows == 0
    assert "loadable rows require at least one source URL" in preview.rows[0].issues
    assert preview.rows[1].issues == []
    assert preview.rows[1].existing_status == "not_loadable"


def test_duplicate_year_team_blocks_preview() -> None:
    fixture = make_fixture(
        [
            make_row(lottery_result_id="draft-lottery-result:mem:2024-a"),
            make_row(lottery_result_id="draft-lottery-result:mem:2024-b"),
        ]
    )

    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[],
    )

    assert preview.blocked_rows == 1
    assert "duplicate fixture draft_year/team_code pair 2024/MEM" in preview.rows[1].issues


def test_team_mismatch_and_unsafe_result_slot_block_loadable_rows() -> None:
    fixture = make_fixture([make_row(team_code="BOS", result_pick_slot=15)])

    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[],
    )

    assert preview.blocked_rows == 1
    assert "row team_code BOS does not match expected team MEM" in preview.rows[0].issues
    assert "result_pick_slot must be between 1 and 14" in preview.rows[0].issues


def test_conflicting_existing_db_year_team_row_blocks_before_write() -> None:
    fixture = make_fixture([make_row()])

    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[
            ExistingDraftLotteryResult(
                lottery_result_id="draft-lottery-result:mem:2024-stale",
                draft_year=2024,
                team_code="MEM",
            )
        ],
    )

    assert preview.blocked_rows == 1
    assert preview.existing_conflicting_rows == 1
    assert preview.rows[0].existing_status == "conflicting"
    assert "existing DB row for 2024/MEM" in preview.rows[0].issues[0]


def test_excluded_existing_db_year_team_row_warns_without_blocking() -> None:
    fixture = make_fixture(
        [
            make_row(
                lottery_result_id="draft-lottery-result:mem:2020-bos-from-mem-excluded",
                draft_year=2020,
                loadable=False,
            )
        ]
    )

    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[
            ExistingDraftLotteryResult(
                lottery_result_id="draft-lottery-result:mem:2020-stale",
                draft_year=2020,
                team_code="MEM",
            )
        ],
    )

    assert preview.blocked_rows == 0
    assert preview.warning_rows == 1
    assert preview.rows[0].existing_status == "not_loadable"
    assert preview.rows[0].existing_lottery_result_id == "draft-lottery-result:mem:2020-stale"
    assert "loadable=false row maps to an existing DB year/team row" in preview.rows[0].warnings[0]


def test_preview_queries_existing_rows_for_all_fixture_years(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = make_fixture(
        [
            make_row(
                lottery_result_id="draft-lottery-result:mem:2020-bos-from-mem-excluded",
                draft_year=2020,
                loadable=False,
            ),
            make_row(draft_year=2024),
        ]
    )
    captured_draft_years: list[int] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_load_existing(
        connection: object,
        *,
        team_code: str,
        draft_years: list[int],
    ) -> list[ExistingDraftLotteryResult]:
        captured_draft_years.extend(draft_years)
        return []

    monkeypatch.setattr(draft_lottery_results, "load_draft_lottery_results_fixture", lambda path: fixture)
    monkeypatch.setattr(draft_lottery_results, "load_existing_draft_lottery_results", fake_load_existing)
    monkeypatch.setattr(draft_lottery_results.psycopg, "connect", lambda *args, **kwargs: FakeConnection())

    draft_lottery_results.preview_draft_lottery_results("postgresql://example", fixture_path=Path("fixture.json"))

    assert sorted(captured_draft_years) == [2020, 2024]


def test_load_draft_lottery_results_dry_run_does_not_open_write_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = build_draft_lottery_results_preview(
        fixture=make_fixture([make_row()]),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[],
    )
    monkeypatch.setattr(draft_lottery_results, "preview_draft_lottery_results", lambda *args, **kwargs: preview)
    monkeypatch.setattr(
        draft_lottery_results.psycopg,
        "connect",
        lambda *args, **kwargs: pytest.fail("dry-run should not open a write connection after preview"),
    )

    result = load_draft_lottery_results("postgresql://example", fixture_path=Path("fixture.json"), dry_run=True)

    assert result.dry_run
    assert result.rows_ready == 1
    assert result.rows_written == 0


def test_load_draft_lottery_results_blocked_preview_does_not_open_write_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = build_draft_lottery_results_preview(
        fixture=make_fixture([make_row(source_urls=[])]),
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[],
    )
    monkeypatch.setattr(draft_lottery_results, "preview_draft_lottery_results", lambda *args, **kwargs: preview)
    monkeypatch.setattr(
        draft_lottery_results.psycopg,
        "connect",
        lambda *args, **kwargs: pytest.fail("blocked preview should not open a write connection"),
    )

    result = load_draft_lottery_results("postgresql://example", fixture_path=Path("fixture.json"))

    assert result.blocked_rows == 1
    assert result.rows_written == 0


def test_load_draft_lottery_results_is_transactional_and_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = make_fixture([make_row()])
    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[],
    )
    state: dict[tuple[int, str], str] = {}
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def commit(self) -> None:
            calls.append("commit")

        def rollback(self) -> None:
            calls.append("rollback")

    def fake_load_existing(connection: object, *, team_code: str, draft_years: list[int]) -> list[ExistingDraftLotteryResult]:
        return [
            ExistingDraftLotteryResult(lottery_result_id=result_id, draft_year=draft_year, team_code=row_team_code)
            for (draft_year, row_team_code), result_id in sorted(state.items())
            if row_team_code == team_code and draft_year in draft_years
        ]

    def fake_upsert(connection: object, rows: list[object]) -> None:
        calls.append("upsert")
        for row in rows:
            state[(row.draft_year, row.team_code)] = row.lottery_result_id

    monkeypatch.setattr(draft_lottery_results, "preview_draft_lottery_results", lambda *args, **kwargs: preview)
    monkeypatch.setattr(draft_lottery_results, "load_draft_lottery_results_fixture", lambda path: fixture)
    monkeypatch.setattr(draft_lottery_results, "load_existing_draft_lottery_results", fake_load_existing)
    monkeypatch.setattr(draft_lottery_results, "upsert_draft_lottery_results", fake_upsert)
    monkeypatch.setattr(draft_lottery_results.psycopg, "connect", lambda *args, **kwargs: FakeConnection())

    result = load_draft_lottery_results("postgresql://example", fixture_path=Path("fixture.json"))
    second_result = load_draft_lottery_results("postgresql://example", fixture_path=Path("fixture.json"))

    assert calls == ["upsert", "commit", "upsert", "commit"]
    assert result.rows_written == 1
    assert second_result.rows_written == 1
    assert state == {(2024, "MEM"): "draft-lottery-result:mem:2024"}


def test_load_transactional_recheck_queries_existing_rows_for_all_fixture_years(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = make_fixture(
        [
            make_row(
                lottery_result_id="draft-lottery-result:mem:2020-bos-from-mem-excluded",
                draft_year=2020,
                loadable=False,
            ),
            make_row(draft_year=2024),
        ]
    )
    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[],
    )
    captured_draft_years: list[int] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def commit(self) -> None:
            return None

    def fake_load_existing(
        connection: object,
        *,
        team_code: str,
        draft_years: list[int],
    ) -> list[ExistingDraftLotteryResult]:
        captured_draft_years.extend(draft_years)
        return []

    monkeypatch.setattr(draft_lottery_results, "preview_draft_lottery_results", lambda *args, **kwargs: preview)
    monkeypatch.setattr(draft_lottery_results, "load_draft_lottery_results_fixture", lambda path: fixture)
    monkeypatch.setattr(draft_lottery_results, "load_existing_draft_lottery_results", fake_load_existing)
    monkeypatch.setattr(draft_lottery_results, "upsert_draft_lottery_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(draft_lottery_results.psycopg, "connect", lambda *args, **kwargs: FakeConnection())

    result = load_draft_lottery_results("postgresql://example", fixture_path=Path("fixture.json"))

    assert result.rows_written == 1
    assert sorted(captured_draft_years) == [2020, 2024]


def test_transactional_recheck_blocks_new_existing_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = make_fixture([make_row()])
    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=Path("fixture.json"),
        team_code="MEM",
        existing_rows=[],
    )
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def commit(self) -> None:
            calls.append("commit")

        def rollback(self) -> None:
            calls.append("rollback")

    monkeypatch.setattr(draft_lottery_results, "preview_draft_lottery_results", lambda *args, **kwargs: preview)
    monkeypatch.setattr(draft_lottery_results, "load_draft_lottery_results_fixture", lambda path: fixture)
    monkeypatch.setattr(
        draft_lottery_results,
        "load_existing_draft_lottery_results",
        lambda *args, **kwargs: [
            ExistingDraftLotteryResult(
                lottery_result_id="draft-lottery-result:mem:2024-stale",
                draft_year=2024,
                team_code="MEM",
            )
        ],
    )
    monkeypatch.setattr(
        draft_lottery_results,
        "upsert_draft_lottery_results",
        lambda *args, **kwargs: pytest.fail("conflicting recheck should block before upsert"),
    )
    monkeypatch.setattr(draft_lottery_results.psycopg, "connect", lambda *args, **kwargs: FakeConnection())

    result = load_draft_lottery_results("postgresql://example", fixture_path=Path("fixture.json"))

    assert result.blocked_rows == 1
    assert result.rows_written == 0
    assert calls == ["rollback"]


def test_default_seed_fixture_contract_loads() -> None:
    fixture = load_draft_lottery_results_fixture(DEFAULT_DRAFT_LOTTERY_RESULTS_FIXTURE_PATH)
    preview = build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=DEFAULT_DRAFT_LOTTERY_RESULTS_FIXTURE_PATH,
        team_code="MEM",
        existing_rows=[],
    )

    assert fixture.fixture_id == "seed_v1"
    assert fixture.team_code == "MEM"
    assert [row.draft_year for row in fixture.rows if row.loadable] == [2018, 2019, 2020, 2024, 2026]
    assert preview.blocked_rows == 0
    assert preview.ready_rows == 5
    result_2020 = next(row for row in fixture.rows if row.draft_year == 2020)
    assert result_2020.owner_team_code == "BOS"
    assert result_2020.original_team_code == "MEM"
    assert all(row.confidence == "high" for row in fixture.rows if row.loadable)
    assert all(row.source_urls and row.source_labels and row.retrieved_at for row in fixture.rows if row.loadable)
    result_2026 = next(row for row in fixture.rows if row.draft_year == 2026)
    assert "https://basketball.realgm.com/nba/teams/Memphis-Grizzlies/14/Lottery-History" in result_2026.source_urls
    assert "RealGM Memphis Grizzlies Lottery History" in result_2026.source_labels


def test_graph_export_does_not_consume_draft_lottery_results() -> None:
    from foundation.export import build_base_export_from_database

    assert "draft_lottery_result" not in getsource(build_base_export_from_database)
