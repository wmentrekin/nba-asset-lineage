from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from foundation.ingest import DraftLotteryResultRow, upsert_draft_lottery_results


DEFAULT_DRAFT_LOTTERY_RESULTS_FIXTURE_PATH = Path("configs/data/memphis_draft_lottery_results_2016_2026.json")

LotteryConfidence = Literal["high", "medium", "low"]


class DraftLotterySourceSetItem(BaseModel):
    label: str
    locator: str


class DraftLotteryFixtureRow(BaseModel):
    lottery_result_id: str
    draft_year: int
    lottery_date: date | None = None
    team_code: str
    owner_team_code: str | None = None
    original_team_code: str | None = None
    lottery_position: int | None = None
    result_pick_slot: int
    pre_lottery_odds: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)
    retrieved_at: date | None = None
    confidence: LotteryConfidence
    loadable: bool
    notes: str | None = None


class DraftLotteryFixture(BaseModel):
    fixture_id: Literal["seed_v1"]
    team_code: str
    coverage_start_year: int
    coverage_end_year: int
    coverage_statement: str
    source_set: list[DraftLotterySourceSetItem]
    confidence_rubric: dict[str, list[str]]
    rows: list[DraftLotteryFixtureRow]


class ExistingDraftLotteryResult(BaseModel):
    lottery_result_id: str
    draft_year: int
    team_code: str
    owner_team_code: str | None = None
    original_team_code: str | None = None


class DraftLotteryPreviewRow(BaseModel):
    lottery_result_id: str
    draft_year: int
    lottery_date: date | None
    team_code: str
    owner_team_code: str | None = None
    original_team_code: str | None = None
    lottery_position: int | None
    result_pick_slot: int
    pre_lottery_odds: str | None
    confidence: LotteryConfidence
    loadable: bool
    ready_for_load: bool
    existing_lottery_result_id: str | None = None
    existing_status: Literal["missing", "matching", "conflicting", "not_loadable"] = "missing"
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)
    retrieved_at: date | None = None
    notes: str | None = None


class DraftLotteryPreview(BaseModel):
    status: Literal["ok"] = "ok"
    fixture_id: str
    fixture_path: str
    team_code: str
    coverage_start_year: int
    coverage_end_year: int
    fixture_rows: int
    loadable_rows: int
    ready_rows: int
    blocked_rows: int
    warning_rows: int
    existing_matching_rows: int
    existing_conflicting_rows: int
    rows: list[DraftLotteryPreviewRow]
    warnings: list[str]
    known_limitations: list[str]


class DraftLotteryLoadResult(BaseModel):
    status: Literal["ok"] = "ok"
    fixture_id: str
    fixture_path: str
    team_code: str
    dry_run: bool
    blocked_rows: int
    warning_rows: int
    rows_ready: int
    rows_written: int
    rows: list[DraftLotteryPreviewRow]
    warnings: list[str]


def load_draft_lottery_results_fixture(path: Path = DEFAULT_DRAFT_LOTTERY_RESULTS_FIXTURE_PATH) -> DraftLotteryFixture:
    return DraftLotteryFixture.model_validate(json.loads(path.read_text(encoding="utf-8")))


def validate_draft_lottery_results_fixture(fixture: DraftLotteryFixture, *, team_code: str) -> list[str]:
    issues: list[str] = []
    expected_team_code = team_code.upper()
    if fixture.team_code.upper() != expected_team_code:
        issues.append(f"fixture team_code {fixture.team_code} does not match expected team {expected_team_code}")
    if fixture.coverage_start_year > fixture.coverage_end_year:
        issues.append("fixture coverage_start_year must be before or equal to coverage_end_year")

    seen_result_ids: set[str] = set()
    seen_year_team: set[tuple[int, str]] = set()
    for row in fixture.rows:
        row_team_code = row.team_code.upper()
        row_key = (row.draft_year, row_team_code)
        if row.lottery_result_id in seen_result_ids:
            issues.append(f"{row.lottery_result_id}: duplicate lottery_result_id in fixture")
        seen_result_ids.add(row.lottery_result_id)
        if row_key in seen_year_team:
            issues.append(f"{row.lottery_result_id}: duplicate fixture draft_year/team_code pair {row.draft_year}/{row_team_code}")
        seen_year_team.add(row_key)
        if not (fixture.coverage_start_year <= row.draft_year <= fixture.coverage_end_year):
            issues.append(f"{row.lottery_result_id}: draft_year is outside fixture coverage")
        if row_team_code != fixture.team_code.upper():
            issues.append(f"{row.lottery_result_id}: row team_code {row.team_code} does not match fixture team {fixture.team_code}")
    if row.loadable:
        issues.extend(validate_loadable_fixture_row(row))
    return issues


def validate_loadable_fixture_row(row: DraftLotteryFixtureRow) -> list[str]:
    issues: list[str] = []
    if row.confidence != "high":
        issues.append(f"{row.lottery_result_id}: only high-confidence rows may be loadable")
    if not row.source_urls:
        issues.append(f"{row.lottery_result_id}: loadable rows require at least one source URL")
    if not row.source_labels:
        issues.append(f"{row.lottery_result_id}: loadable rows require at least one source label")
    if row.retrieved_at is None:
        issues.append(f"{row.lottery_result_id}: loadable rows require retrieved_at")
    if row.result_pick_slot < 1 or row.result_pick_slot > 14:
        issues.append(f"{row.lottery_result_id}: result_pick_slot must be between 1 and 14")
    if row.lottery_position is not None and (row.lottery_position < 1 or row.lottery_position > 14):
        issues.append(f"{row.lottery_result_id}: lottery_position must be between 1 and 14 when present")
    if row.lottery_date is None:
        issues.append(f"{row.lottery_result_id}: loadable rows require lottery_date")
    if row.owner_team_code is None:
        issues.append(f"{row.lottery_result_id}: loadable rows require owner_team_code")
    if row.original_team_code is None:
        issues.append(f"{row.lottery_result_id}: loadable rows require original_team_code")
    return issues


def build_draft_lottery_results_preview(
    *,
    fixture: DraftLotteryFixture,
    fixture_path: Path,
    team_code: str,
    existing_rows: list[ExistingDraftLotteryResult],
) -> DraftLotteryPreview:
    expected_team_code = team_code.upper()
    fixture_issues = validate_draft_lottery_results_fixture(fixture, team_code=team_code)
    row_issue_by_id: dict[str, list[str]] = {}
    global_issues: list[str] = []
    for issue in fixture_issues:
        if ": " in issue:
            row_id, detail = issue.split(": ", 1)
            row_issue_by_id.setdefault(row_id, []).append(detail)
        else:
            global_issues.append(issue)

    existing_by_year_team = {
        (row.draft_year, row.team_code.upper()): row
        for row in existing_rows
    }
    rows = [
        build_draft_lottery_preview_row(
            row,
            expected_team_code=expected_team_code,
            existing_row=existing_by_year_team.get((row.draft_year, row.team_code.upper())),
            extra_issues=row_issue_by_id.get(row.lottery_result_id, []),
        )
        for row in fixture.rows
    ]
    for row_id, issues in row_issue_by_id.items():
        if not any(row.lottery_result_id == row_id for row in rows):
            global_issues.extend(issues)

    warnings = [
        "blocking fixture issue: " + issue
        for issue in global_issues
    ]
    for row in rows:
        warnings.extend(row.warnings)

    return DraftLotteryPreview(
        fixture_id=fixture.fixture_id,
        fixture_path=str(fixture_path),
        team_code=expected_team_code,
        coverage_start_year=fixture.coverage_start_year,
        coverage_end_year=fixture.coverage_end_year,
        fixture_rows=len(rows),
        loadable_rows=sum(1 for row in rows if row.loadable),
        ready_rows=sum(1 for row in rows if row.ready_for_load),
        blocked_rows=sum(1 for row in rows if row.issues) + len(global_issues),
        warning_rows=sum(1 for row in rows if row.warnings) + len(global_issues),
        existing_matching_rows=sum(1 for row in rows if row.existing_status == "matching"),
        existing_conflicting_rows=sum(1 for row in rows if row.existing_status == "conflicting"),
        rows=rows,
        warnings=warnings,
        known_limitations=[
            "seed_v1 is contextual lottery metadata, not part of the minimum graph export contract.",
            "team_code is the Memphis perspective scope; owner_team_code and original_team_code carry explicit pick semantics.",
            "Rows with loadable=false are never written.",
        ],
    )


def build_draft_lottery_preview_row(
    row: DraftLotteryFixtureRow,
    *,
    expected_team_code: str,
    existing_row: ExistingDraftLotteryResult | None,
    extra_issues: list[str] | None = None,
) -> DraftLotteryPreviewRow:
    issues = list(extra_issues or [])
    warnings: list[str] = []
    if row.team_code.upper() != expected_team_code:
        issues.append(f"row team_code {row.team_code} does not match expected team {expected_team_code}")

    existing_status: Literal["missing", "matching", "conflicting", "not_loadable"] = "missing"
    existing_lottery_result_id = existing_row.lottery_result_id if existing_row is not None else None
    if not row.loadable:
        existing_status = "not_loadable"
        if existing_row is not None:
            warnings.append(
                f"{row.lottery_result_id}: loadable=false row maps to an existing DB year/team row and will not be written"
            )
    elif existing_row is not None and existing_row.lottery_result_id == row.lottery_result_id:
        existing_status = "matching"
    elif existing_row is not None:
        existing_status = "conflicting"
        issues.append(
            f"existing DB row for {row.draft_year}/{row.team_code.upper()} has lottery_result_id "
            f"{existing_row.lottery_result_id}, expected {row.lottery_result_id}"
        )

    ready_for_load = row.loadable and not issues
    return DraftLotteryPreviewRow(
        lottery_result_id=row.lottery_result_id,
        draft_year=row.draft_year,
        lottery_date=row.lottery_date,
        team_code=row.team_code.upper(),
        owner_team_code=row.owner_team_code.upper() if row.owner_team_code else None,
        original_team_code=row.original_team_code.upper() if row.original_team_code else None,
        lottery_position=row.lottery_position,
        result_pick_slot=row.result_pick_slot,
        pre_lottery_odds=row.pre_lottery_odds,
        confidence=row.confidence,
        loadable=row.loadable,
        ready_for_load=ready_for_load,
        existing_lottery_result_id=existing_lottery_result_id,
        existing_status=existing_status,
        issues=issues,
        warnings=warnings,
        source_urls=row.source_urls,
        source_labels=row.source_labels,
        retrieved_at=row.retrieved_at,
        notes=row.notes,
    )


def preview_draft_lottery_results(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_DRAFT_LOTTERY_RESULTS_FIXTURE_PATH,
) -> DraftLotteryPreview:
    fixture = load_draft_lottery_results_fixture(fixture_path)
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        existing_rows = load_existing_draft_lottery_results(
            connection,
            team_code=team_code,
            draft_years=[row.draft_year for row in fixture.rows],
        )
    return build_draft_lottery_results_preview(
        fixture=fixture,
        fixture_path=fixture_path,
        team_code=team_code,
        existing_rows=existing_rows,
    )


def load_draft_lottery_results(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_DRAFT_LOTTERY_RESULTS_FIXTURE_PATH,
    dry_run: bool = False,
) -> DraftLotteryLoadResult:
    preview = preview_draft_lottery_results(database_url, team_code=team_code, fixture_path=fixture_path)
    if preview.blocked_rows:
        return DraftLotteryLoadResult(
            fixture_id=preview.fixture_id,
            fixture_path=preview.fixture_path,
            team_code=preview.team_code,
            dry_run=dry_run,
            blocked_rows=preview.blocked_rows,
            warning_rows=preview.warning_rows,
            rows_ready=0,
            rows_written=0,
            rows=preview.rows,
            warnings=preview.warnings,
        )
    if dry_run:
        return DraftLotteryLoadResult(
            fixture_id=preview.fixture_id,
            fixture_path=preview.fixture_path,
            team_code=preview.team_code,
            dry_run=True,
            blocked_rows=0,
            warning_rows=preview.warning_rows,
            rows_ready=preview.ready_rows,
            rows_written=0,
            rows=preview.rows,
            warnings=preview.warnings,
        )

    fixture = load_draft_lottery_results_fixture(fixture_path)
    rows_to_write = build_draft_lottery_result_rows(fixture, preview)
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        existing_rows = load_existing_draft_lottery_results(
            connection,
            team_code=team_code,
            draft_years=[row.draft_year for row in fixture.rows],
        )
        transactional_preview = build_draft_lottery_results_preview(
            fixture=fixture,
            fixture_path=fixture_path,
            team_code=team_code,
            existing_rows=existing_rows,
        )
        if transactional_preview.blocked_rows:
            connection.rollback()
            return DraftLotteryLoadResult(
                fixture_id=transactional_preview.fixture_id,
                fixture_path=transactional_preview.fixture_path,
                team_code=transactional_preview.team_code,
                dry_run=False,
                blocked_rows=transactional_preview.blocked_rows,
                warning_rows=transactional_preview.warning_rows,
                rows_ready=0,
                rows_written=0,
                rows=transactional_preview.rows,
                warnings=transactional_preview.warnings,
            )
        upsert_draft_lottery_results(connection, rows_to_write)
        connection.commit()

    return DraftLotteryLoadResult(
        fixture_id=preview.fixture_id,
        fixture_path=preview.fixture_path,
        team_code=preview.team_code,
        dry_run=False,
        blocked_rows=0,
        warning_rows=preview.warning_rows,
        rows_ready=preview.ready_rows,
        rows_written=len(rows_to_write),
        rows=preview.rows,
        warnings=preview.warnings,
    )


def build_draft_lottery_result_rows(
    fixture: DraftLotteryFixture,
    preview: DraftLotteryPreview,
) -> list[DraftLotteryResultRow]:
    ready_ids = {row.lottery_result_id for row in preview.rows if row.ready_for_load}
    return [
        DraftLotteryResultRow(
            lottery_result_id=row.lottery_result_id,
            draft_year=row.draft_year,
            lottery_date=row.lottery_date.isoformat() if row.lottery_date is not None else None,
            team_code=row.team_code.upper(),
            owner_team_code=row.owner_team_code.upper() if row.owner_team_code else None,
            original_team_code=row.original_team_code.upper() if row.original_team_code else None,
            lottery_position=row.lottery_position,
            result_pick_slot=row.result_pick_slot,
            pre_lottery_odds=row.pre_lottery_odds,
            notes=build_draft_lottery_notes(row),
        )
        for row in fixture.rows
        if row.lottery_result_id in ready_ids
    ]


def build_draft_lottery_notes(row: DraftLotteryFixtureRow) -> str:
    parts = [
        row.notes or "Curated draft lottery seed row.",
        f"Fixture seed_v1; confidence={row.confidence}; retrieved_at={row.retrieved_at.isoformat() if row.retrieved_at else 'unknown'}.",
    ]
    if row.source_labels:
        parts.append("Sources: " + "; ".join(row.source_labels) + ".")
    return " ".join(parts)


def load_existing_draft_lottery_results(
    connection: psycopg.Connection,
    *,
    team_code: str,
    draft_years: list[int],
) -> list[ExistingDraftLotteryResult]:
    if not draft_years:
        return []
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('foundation.draft_lottery_result')")
        if cursor.fetchone()[0] is None:
            return []
        cursor.execute(
            """
            select lottery_result_id, draft_year, team_code, owner_team_code, original_team_code
            from foundation.draft_lottery_result
            where team_code = %s
              and draft_year = any(%s)
            order by draft_year, team_code
            """,
            (team_code.upper(), sorted(set(draft_years))),
        )
        return [
            ExistingDraftLotteryResult(
                lottery_result_id=str(row[0]),
                draft_year=int(row[1]),
                team_code=str(row[2]),
                owner_team_code=str(row[3]) if row[3] is not None else None,
                original_team_code=str(row[4]) if row[4] is not None else None,
            )
            for row in cursor.fetchall()
        ]
