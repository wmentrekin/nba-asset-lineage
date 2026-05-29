from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, Field, computed_field, model_validator

from foundation.export import draft_resolution_event_date
from foundation.ingest import AssetRow
from foundation.ingest import PickInventoryObligationRow
from foundation.ingest import PickRow
from foundation.ingest import RosterSnapshotPickRow
from foundation.ingest import replace_roster_snapshot_picks
from foundation.ingest import upsert_assets
from foundation.ingest import upsert_pick_inventory_obligations
from foundation.ingest import upsert_picks
from foundation.models import CompositePickRight, derive_composite_pick_right


DEFAULT_FUTURE_PICK_OBLIGATION_PATH = Path("configs/data/memphis_future_pick_obligations_2016_2026.json")

PickInventoryDirection = Literal["incoming", "outgoing", "own", "swap_right", "swap_obligation"]
PickInventoryHoldingStatus = Literal["owned", "owed_out", "swap_right", "encumbered", "conditional"]
PickInventoryObligationType = Literal["own_pick", "traded_pick", "swap", "conditional_fallback"]
PickInventoryConfidence = Literal["derived", "curated", "validated", "uncertain"]


class PickInventorySnapshot(BaseModel):
    snapshot_id: str
    snapshot_date: str
    snapshot_kind: str
    season: str
    team_code: str


class PickInventoryObligation(BaseModel):
    obligation_id: str
    effective_date: str
    team_code: str | None = None
    perspective_team_code: str | None = None
    owner_team_code: str | None = None
    draft_year: int
    round_number: int
    original_team: str | None = None
    original_team_code: str | None = None
    direction: PickInventoryDirection
    holding_status: PickInventoryHoldingStatus
    obligation_type: PickInventoryObligationType
    protection_text: str | None = None
    swap_text: str | None = None
    condition_text: str | None = None
    source_event_id: str | None = None
    canonical_event_id: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)
    retrieved_at: str | None = None
    confidence: PickInventoryConfidence = "curated"
    loadable: bool = True
    notes: str | None = None

    @computed_field
    @property
    def composite_right(self) -> CompositePickRight | None:
        return derive_composite_pick_right(
            source_obligation_id=self.obligation_id,
            draft_year=self.draft_year,
            round_number=self.round_number,
            original_team_code=self.original_team_code,
        )

    @model_validator(mode="after")
    def normalize_codes(self) -> "PickInventoryObligation":
        perspective_team_code = normalize_team_code(self.perspective_team_code or self.team_code)
        original_team_code = normalize_team_code(self.original_team_code or self.original_team)
        if not perspective_team_code:
            raise ValueError("perspective_team_code or team_code is required")
        if not original_team_code:
            raise ValueError("original_team_code or original_team is required")

        owner_team_code = normalize_team_code(self.owner_team_code)
        if not owner_team_code:
            owner_team_code = infer_owner_team_code(
                perspective_team_code=perspective_team_code,
                direction=self.direction,
            )

        self.perspective_team_code = perspective_team_code
        self.team_code = perspective_team_code
        self.owner_team_code = owner_team_code
        self.original_team_code = original_team_code
        self.original_team = original_team_code
        self.source_urls = [url.strip() for url in self.source_urls if url.strip()]
        self.source_labels = [label.strip() for label in self.source_labels if label.strip()]
        return self


class ProjectedPickInventoryRow(BaseModel):
    snapshot_id: str
    snapshot_date: str
    pick_id: str
    asset_id: str
    draft_year: int
    round_number: int
    original_team: str
    holding_status: PickInventoryHoldingStatus
    display_order: int
    source_obligation_id: str | None = None
    confidence: PickInventoryConfidence = "derived"
    notes: str | None = None

    @computed_field
    @property
    def composite_right(self) -> CompositePickRight | None:
        return derive_composite_pick_right(
            source_obligation_id=self.source_obligation_id,
            draft_year=self.draft_year,
            round_number=self.round_number,
            original_team_code=self.original_team,
        )


class PickInventoryFixture(BaseModel):
    fixture_id: str = "legacy_list"
    team_code: str = "MEM"
    rows: list[PickInventoryObligation]
    row_field_names: dict[str, set[str]] = Field(default_factory=dict)


class ExistingPickInventoryObligation(BaseModel):
    obligation_id: str
    effective_date: str
    perspective_team_code: str
    owner_team_code: str
    original_team_code: str
    draft_year: int
    round_number: int
    direction: PickInventoryDirection
    holding_status: PickInventoryHoldingStatus
    obligation_type: PickInventoryObligationType
    confidence: PickInventoryConfidence
    loadable: bool


class PickInventoryObligationPreviewRow(BaseModel):
    obligation_id: str
    effective_date: str
    perspective_team_code: str
    owner_team_code: str
    original_team_code: str
    draft_year: int
    round_number: int
    direction: PickInventoryDirection
    holding_status: PickInventoryHoldingStatus
    obligation_type: PickInventoryObligationType
    confidence: PickInventoryConfidence
    loadable: bool
    ready_for_load: bool
    existing_obligation_id: str | None = None
    existing_status: Literal["missing", "matching", "conflicting", "not_loadable"] = "missing"
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)
    retrieved_at: str | None = None
    source_event_id: str | None = None
    canonical_event_id: str | None = None
    protection_text: str | None = None
    swap_text: str | None = None
    condition_text: str | None = None
    notes: str | None = None

    @computed_field
    @property
    def composite_right(self) -> CompositePickRight | None:
        return derive_composite_pick_right(
            source_obligation_id=self.obligation_id,
            draft_year=self.draft_year,
            round_number=self.round_number,
            original_team_code=self.original_team_code,
        )


class PickInventoryObligationPreview(BaseModel):
    status: Literal["ok"] = "ok"
    fixture_id: str
    fixture_path: str
    team_code: str
    fixture_rows: int
    loadable_rows: int
    ready_rows: int
    blocked_rows: int
    warning_rows: int
    existing_matching_rows: int
    existing_conflicting_rows: int
    rows: list[PickInventoryObligationPreviewRow]
    warnings: list[str]
    known_limitations: list[str]


class PickInventoryObligationLoadResult(BaseModel):
    status: Literal["ok"] = "ok"
    fixture_id: str
    fixture_path: str
    team_code: str
    dry_run: bool
    blocked_rows: int
    warning_rows: int
    rows_ready: int
    obligations_written: int
    picks_upserted: int
    assets_upserted: int
    rows: list[PickInventoryObligationPreviewRow]
    warnings: list[str]


class PickInventorySnapshotLoadResult(BaseModel):
    status: Literal["ok"] = "ok"
    team_code: str
    max_draft_year: int
    dry_run: bool
    snapshots: int
    obligations: int
    blocked_obligations: int
    existing_snapshot_pick_rows: int
    projected_rows: int
    picks_upserted: int
    assets_upserted: int
    rows_written: int
    warnings: list[str]
    sample_rows: list[dict[str, object]]


class PickInventoryPreviewResult(BaseModel):
    status: Literal["ok"] = "ok"
    team_code: str
    max_draft_year: int
    snapshots: int
    obligations: int
    existing_snapshot_pick_rows: int
    projected_rows: int
    proposed_pick_ids: int
    proposed_asset_ids: int
    by_snapshot_kind: dict[str, int]
    by_holding_status: dict[str, int]
    latest_snapshot: dict[str, object] | None
    sample_rows: list[dict[str, object]]


def load_future_pick_obligations(path: Path = DEFAULT_FUTURE_PICK_OBLIGATION_PATH) -> list[PickInventoryObligation]:
    return load_pick_inventory_fixture(path).rows


def load_projectable_future_pick_obligations(
    path: Path = DEFAULT_FUTURE_PICK_OBLIGATION_PATH,
) -> list[PickInventoryObligation]:
    return [
        row
        for row in load_future_pick_obligations(path)
        if is_projectable_pick_inventory_obligation(row)
    ]


def load_pick_inventory_fixture(path: Path = DEFAULT_FUTURE_PICK_OBLIGATION_PATH) -> PickInventoryFixture:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        raw_rows = payload
        fixture_id = "legacy_list"
        team_code = "MEM"
    elif isinstance(payload, dict):
        raw_rows = payload.get("rows", [])
        fixture_id = str(payload.get("fixture_id", "seed_v1"))
        team_code = str(payload.get("team_code", "MEM"))
    else:
        raise ValueError("pick inventory fixture must be a row list or an object with rows")
    if not isinstance(raw_rows, list):
        raise ValueError("pick inventory fixture rows must be a list")

    rows: list[PickInventoryObligation] = []
    row_field_names: dict[str, set[str]] = {}
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise ValueError("pick inventory fixture rows must be objects")
        row = PickInventoryObligation.model_validate(raw_row)
        rows.append(row)
        row_field_names[row.obligation_id] = set(str(key) for key in raw_row)
    return PickInventoryFixture(
        fixture_id=fixture_id,
        team_code=team_code,
        rows=rows,
        row_field_names=row_field_names,
    )


def preview_pick_inventory_obligations(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_FUTURE_PICK_OBLIGATION_PATH,
    allow_update_ids: set[str] | None = None,
) -> PickInventoryObligationPreview:
    fixture = load_pick_inventory_fixture(fixture_path)
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        existing_rows = load_existing_pick_inventory_obligations(
            connection,
            obligation_ids=[row.obligation_id for row in fixture.rows],
        )
    return build_pick_inventory_obligation_preview(
        fixture=fixture,
        fixture_path=fixture_path,
        team_code=team_code,
        existing_rows=existing_rows,
        allow_update_ids=allow_update_ids,
    )


def build_pick_inventory_obligation_preview(
    *,
    fixture: PickInventoryFixture,
    fixture_path: Path,
    team_code: str,
    existing_rows: list[ExistingPickInventoryObligation],
    allow_update_ids: set[str] | None = None,
) -> PickInventoryObligationPreview:
    expected_team_code = team_code.upper()
    allow_update_ids = allow_update_ids or set()
    fixture_issues = validate_pick_inventory_fixture(fixture, team_code=team_code)
    row_issue_by_id: dict[str, list[str]] = {}
    global_issues: list[str] = []
    for issue in fixture_issues:
        if ": " in issue:
            row_id, detail = issue.split(": ", 1)
            row_issue_by_id.setdefault(row_id, []).append(detail)
        else:
            global_issues.append(issue)

    existing_by_id = {row.obligation_id: row for row in existing_rows}
    rows = [
        build_pick_inventory_obligation_preview_row(
            row,
            expected_team_code=expected_team_code,
            existing_row=existing_by_id.get(row.obligation_id),
            extra_issues=row_issue_by_id.get(row.obligation_id, []),
            allow_update_ids=allow_update_ids,
        )
        for row in fixture.rows
        if row.perspective_team_code == expected_team_code
    ]
    for row_id, issues in row_issue_by_id.items():
        if not any(row.obligation_id == row_id for row in rows):
            global_issues.extend(f"{row_id}: {issue}" for issue in issues)

    warnings = [f"blocking fixture issue: {issue}" for issue in global_issues]
    for row in rows:
        warnings.extend(row.warnings)
    return PickInventoryObligationPreview(
        fixture_id=fixture.fixture_id,
        fixture_path=str(fixture_path),
        team_code=expected_team_code,
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
            "The loader writes source-backed obligation rows to durable obligation storage, but only projectable rows can flow into concrete pick/asset upserts and snapshot projection.",
            "Rows with loadable=false remain non-projectable and are excluded from concrete snapshot ownership even when they are durably stored.",
            "Snapshot projection is derived from loaded obligations plus own-pick baseline rules.",
        ],
    )


def validate_pick_inventory_fixture(fixture: PickInventoryFixture, *, team_code: str) -> list[str]:
    issues: list[str] = []
    expected_team_code = team_code.upper()
    if fixture.team_code.upper() != expected_team_code:
        issues.append(f"fixture team_code {fixture.team_code} does not match expected team {expected_team_code}")

    seen_obligation_ids: set[str] = set()
    for row in fixture.rows:
        if row.obligation_id in seen_obligation_ids:
            issues.append(f"{row.obligation_id}: duplicate obligation_id in fixture")
        seen_obligation_ids.add(row.obligation_id)
        if row.perspective_team_code != fixture.team_code.upper():
            issues.append(
                f"{row.obligation_id}: perspective_team_code {row.perspective_team_code} "
                f"does not match fixture team {fixture.team_code.upper()}"
            )
        if row.loadable:
            issues.extend(validate_loadable_pick_inventory_obligation(row, fixture.row_field_names.get(row.obligation_id, set())))
        elif not row.source_urls or not row.source_labels or row.retrieved_at is None:
            issues.append(f"{row.obligation_id}: non-projectable rows still require source metadata to be written durably")
    return issues


def validate_loadable_pick_inventory_obligation(
    row: PickInventoryObligation,
    field_names: set[str],
) -> list[str]:
    issues: list[str] = []
    for field_name in ("perspective_team_code", "owner_team_code", "original_team_code"):
        if field_name not in field_names:
            issues.append(f"{row.obligation_id}: loadable rows require {field_name}")
    if row.confidence == "uncertain":
        issues.append(f"{row.obligation_id}: uncertain rows cannot be loadable")
    if not row.source_urls:
        issues.append(f"{row.obligation_id}: loadable rows require at least one source URL")
    if not row.source_labels:
        issues.append(f"{row.obligation_id}: loadable rows require at least one source label")
    if row.source_urls and row.source_labels and len(row.source_urls) != len(row.source_labels):
        issues.append(f"{row.obligation_id}: source_urls and source_labels must have the same length")
    if row.retrieved_at is None:
        issues.append(f"{row.obligation_id}: loadable rows require retrieved_at")
    if row.source_event_id and row.source_event_id.startswith("canonical:"):
        issues.append(f"{row.obligation_id}: canonical IDs must use canonical_event_id, not source_event_id")
    return issues


def build_pick_inventory_obligation_preview_row(
    row: PickInventoryObligation,
    *,
    expected_team_code: str,
    existing_row: ExistingPickInventoryObligation | None,
    extra_issues: list[str] | None = None,
    allow_update_ids: set[str] | None = None,
) -> PickInventoryObligationPreviewRow:
    issues = list(extra_issues or [])
    warnings: list[str] = []
    allow_update_ids = allow_update_ids or set()
    if row.perspective_team_code != expected_team_code:
        issues.append(f"row perspective_team_code {row.perspective_team_code} does not match expected team {expected_team_code}")

    existing_status: Literal["missing", "matching", "conflicting", "not_loadable"] = "missing"
    existing_obligation_id = existing_row.obligation_id if existing_row is not None else None
    if existing_row is not None and existing_pick_inventory_obligation_matches(row, existing_row):
        existing_status = "matching"
    elif existing_row is not None:
        existing_status = "conflicting"
        if row.obligation_id in allow_update_ids and (row.loadable or not row.loadable):
            warnings.append(f"{row.obligation_id}: existing DB row conflicts and will be updated because it is explicitly listed in allow_update_ids")
        else:
            issues.append(f"existing DB row for {row.obligation_id} conflicts with the fixture row")
    elif not row.loadable:
        existing_status = "not_loadable"

    ready_for_load = not issues and (row.confidence != "uncertain" or not row.loadable)
    return PickInventoryObligationPreviewRow(
        obligation_id=row.obligation_id,
        effective_date=row.effective_date,
        perspective_team_code=row.perspective_team_code or expected_team_code,
        owner_team_code=row.owner_team_code or "",
        original_team_code=row.original_team_code or "",
        draft_year=row.draft_year,
        round_number=row.round_number,
        direction=row.direction,
        holding_status=row.holding_status,
        obligation_type=row.obligation_type,
        confidence=row.confidence,
        loadable=row.loadable,
        ready_for_load=ready_for_load,
        existing_obligation_id=existing_obligation_id,
        existing_status=existing_status,
        issues=issues,
        warnings=warnings,
        source_urls=row.source_urls,
        source_labels=row.source_labels,
        retrieved_at=row.retrieved_at,
        source_event_id=row.source_event_id,
        canonical_event_id=row.canonical_event_id,
        protection_text=row.protection_text,
        swap_text=row.swap_text,
        condition_text=row.condition_text,
        notes=row.notes,
    )


def existing_pick_inventory_obligation_matches(
    fixture_row: PickInventoryObligation,
    existing_row: ExistingPickInventoryObligation,
) -> bool:
    return (
        fixture_row.effective_date == existing_row.effective_date
        and fixture_row.perspective_team_code == existing_row.perspective_team_code
        and fixture_row.owner_team_code == existing_row.owner_team_code
        and fixture_row.original_team_code == existing_row.original_team_code
        and fixture_row.draft_year == existing_row.draft_year
        and fixture_row.round_number == existing_row.round_number
        and fixture_row.direction == existing_row.direction
        and fixture_row.holding_status == existing_row.holding_status
        and fixture_row.obligation_type == existing_row.obligation_type
        and fixture_row.confidence == existing_row.confidence
        and fixture_row.loadable == existing_row.loadable
    )


def load_pick_inventory_obligations(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_FUTURE_PICK_OBLIGATION_PATH,
    dry_run: bool = False,
    allow_update_ids: set[str] | None = None,
) -> PickInventoryObligationLoadResult:
    preview = preview_pick_inventory_obligations(
        database_url,
        team_code=team_code,
        fixture_path=fixture_path,
        allow_update_ids=allow_update_ids,
    )
    if preview.blocked_rows:
        return PickInventoryObligationLoadResult(
            fixture_id=preview.fixture_id,
            fixture_path=preview.fixture_path,
            team_code=preview.team_code,
            dry_run=dry_run,
            blocked_rows=preview.blocked_rows,
            warning_rows=preview.warning_rows,
            rows_ready=0,
            obligations_written=0,
            picks_upserted=0,
            assets_upserted=0,
            rows=preview.rows,
            warnings=preview.warnings,
        )

    fixture = load_pick_inventory_fixture(fixture_path)
    rows_to_write = build_pick_inventory_obligation_rows(fixture, preview)
    pick_rows, asset_rows = build_pick_and_asset_rows_for_obligations(
        [row for row in fixture.rows if row.obligation_id in {ready.obligation_id for ready in preview.rows if ready.ready_for_load}]
    )
    if dry_run:
        return PickInventoryObligationLoadResult(
            fixture_id=preview.fixture_id,
            fixture_path=preview.fixture_path,
            team_code=preview.team_code,
            dry_run=True,
            blocked_rows=0,
            warning_rows=preview.warning_rows,
            rows_ready=preview.ready_rows,
            obligations_written=0,
            picks_upserted=len(pick_rows),
            assets_upserted=len(asset_rows),
            rows=preview.rows,
            warnings=preview.warnings,
        )

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        existing_rows = load_existing_pick_inventory_obligations(
            connection,
            obligation_ids=[row.obligation_id for row in fixture.rows],
        )
        transactional_preview = build_pick_inventory_obligation_preview(
            fixture=fixture,
            fixture_path=fixture_path,
            team_code=team_code,
            existing_rows=existing_rows,
            allow_update_ids=allow_update_ids,
        )
        if transactional_preview.blocked_rows:
            connection.rollback()
            return PickInventoryObligationLoadResult(
                fixture_id=transactional_preview.fixture_id,
                fixture_path=transactional_preview.fixture_path,
                team_code=transactional_preview.team_code,
                dry_run=False,
                blocked_rows=transactional_preview.blocked_rows,
                warning_rows=transactional_preview.warning_rows,
                rows_ready=0,
                obligations_written=0,
                picks_upserted=0,
                assets_upserted=0,
                rows=transactional_preview.rows,
                warnings=transactional_preview.warnings,
            )
        upsert_picks(connection, pick_rows)
        upsert_assets(connection, asset_rows)
        upsert_pick_inventory_obligations(connection, rows_to_write)
        connection.commit()

    return PickInventoryObligationLoadResult(
        fixture_id=preview.fixture_id,
        fixture_path=preview.fixture_path,
        team_code=preview.team_code,
        dry_run=False,
        blocked_rows=0,
        warning_rows=preview.warning_rows,
        rows_ready=preview.ready_rows,
        obligations_written=len(rows_to_write),
        picks_upserted=len(pick_rows),
        assets_upserted=len(asset_rows),
        rows=preview.rows,
        warnings=preview.warnings,
    )


def build_pick_inventory_obligation_rows(
    fixture: PickInventoryFixture,
    preview: PickInventoryObligationPreview,
) -> list[PickInventoryObligationRow]:
    ready_ids = {row.obligation_id for row in preview.rows if row.ready_for_load}
    return [
        PickInventoryObligationRow(
            obligation_id=row.obligation_id,
            effective_date=row.effective_date,
            perspective_team_code=row.perspective_team_code or preview.team_code,
            owner_team_code=row.owner_team_code or preview.team_code,
            original_team_code=row.original_team_code or "",
            draft_year=row.draft_year,
            round_number=row.round_number,
            direction=row.direction,
            holding_status=row.holding_status,
            obligation_type=row.obligation_type,
            confidence=row.confidence,
            source_urls=row.source_urls,
            source_labels=row.source_labels,
            retrieved_at=row.retrieved_at or "",
            source_event_id=row.source_event_id,
            canonical_event_id=row.canonical_event_id,
            protection_text=row.protection_text,
            swap_text=row.swap_text,
            condition_text=row.condition_text,
            notes=row.notes,
            loadable=row.loadable,
        )
        for row in fixture.rows
        if row.obligation_id in ready_ids
    ]


def load_existing_pick_inventory_obligations(
    connection: psycopg.Connection,
    *,
    obligation_ids: list[str],
) -> list[ExistingPickInventoryObligation]:
    if not obligation_ids:
        return []
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('foundation.pick_inventory_obligation')")
        if cursor.fetchone()[0] is None:
            return []
        cursor.execute(
            """
            select obligation_id,
                   effective_date::text,
                   perspective_team_code,
                   owner_team_code,
                   original_team_code,
                   draft_year,
                   round_number,
                   direction,
                   holding_status,
                   obligation_type,
                   confidence,
                   loadable
            from foundation.pick_inventory_obligation
            where obligation_id = any(%s)
            order by obligation_id
            """,
            (sorted(set(obligation_ids)),),
        )
        return [
            ExistingPickInventoryObligation(
                obligation_id=str(row[0]),
                effective_date=str(row[1]),
                perspective_team_code=str(row[2]).upper(),
                owner_team_code=str(row[3]).upper(),
                original_team_code=str(row[4]).upper(),
                draft_year=int(row[5]),
                round_number=int(row[6]),
                direction=str(row[7]),  # type: ignore[arg-type]
                holding_status=str(row[8]),  # type: ignore[arg-type]
                obligation_type=str(row[9]),  # type: ignore[arg-type]
                confidence=str(row[10]),  # type: ignore[arg-type]
                loadable=bool(row[11]),
            )
            for row in cursor.fetchall()
        ]


def load_pick_inventory_obligations_from_database(
    connection: psycopg.Connection,
    *,
    team_code: str,
) -> list[PickInventoryObligation]:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('foundation.pick_inventory_obligation')")
        if cursor.fetchone()[0] is None:
            return []
        cursor.execute(
            """
            select obligation_id,
                   effective_date::text,
                   perspective_team_code,
                   owner_team_code,
                   original_team_code,
                   draft_year,
                   round_number,
                   direction,
                   holding_status,
                   obligation_type,
                   confidence,
                   source_urls,
                   source_labels,
                   retrieved_at::text,
                   source_event_id,
                   canonical_event_id,
                   protection_text,
                   swap_text,
                   condition_text,
                   notes,
                   loadable
            from foundation.pick_inventory_obligation
            where upper(perspective_team_code) = upper(%s)
            order by effective_date, obligation_id
            """,
            (team_code,),
        )
        return [
            PickInventoryObligation(
                obligation_id=str(row[0]),
                effective_date=str(row[1]),
                perspective_team_code=str(row[2]),
                owner_team_code=str(row[3]),
                original_team_code=str(row[4]),
                draft_year=int(row[5]),
                round_number=int(row[6]),
                direction=str(row[7]),  # type: ignore[arg-type]
                holding_status=str(row[8]),  # type: ignore[arg-type]
                obligation_type=str(row[9]),  # type: ignore[arg-type]
                confidence=str(row[10]),  # type: ignore[arg-type]
                source_urls=list(row[11] or []),
                source_labels=list(row[12] or []),
                retrieved_at=str(row[13]) if row[13] is not None else None,
                source_event_id=str(row[14]) if row[14] is not None else None,
                canonical_event_id=str(row[15]) if row[15] is not None else None,
                protection_text=str(row[16]) if row[16] is not None else None,
                swap_text=str(row[17]) if row[17] is not None else None,
                condition_text=str(row[18]) if row[18] is not None else None,
                notes=str(row[19]) if row[19] is not None else None,
                loadable=bool(row[20]),
            )
            for row in cursor.fetchall()
        ]


def load_pick_inventory_snapshots(
    database_url: str,
    *,
    team_code: str = "MEM",
    max_draft_year: int = 2032,
    dry_run: bool = False,
) -> PickInventorySnapshotLoadResult:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        snapshots = fetch_pick_inventory_snapshots_from_connection(connection, team_code=team_code)
        obligations = load_pick_inventory_obligations_from_database(connection, team_code=team_code)
        existing_snapshot_pick_rows = fetch_existing_snapshot_pick_count_from_connection(connection)
    return build_pick_inventory_snapshot_load_result(
        database_url=database_url,
        snapshots=snapshots,
        obligations=obligations,
        existing_snapshot_pick_rows=existing_snapshot_pick_rows,
        team_code=team_code,
        max_draft_year=max_draft_year,
        dry_run=dry_run,
    )


def build_pick_inventory_snapshot_load_result(
    *,
    database_url: str,
    snapshots: list[PickInventorySnapshot],
    obligations: list[PickInventoryObligation],
    existing_snapshot_pick_rows: int,
    team_code: str,
    max_draft_year: int,
    dry_run: bool,
) -> PickInventorySnapshotLoadResult:
    warnings = validate_loaded_obligations_for_snapshot_projection(obligations)
    if warnings:
        return PickInventorySnapshotLoadResult(
            team_code=team_code.upper(),
            max_draft_year=max_draft_year,
            dry_run=dry_run,
            snapshots=len(snapshots),
            obligations=len(obligations),
            blocked_obligations=len(warnings),
            existing_snapshot_pick_rows=existing_snapshot_pick_rows,
            projected_rows=0,
            picks_upserted=0,
            assets_upserted=0,
            rows_written=0,
            warnings=warnings,
            sample_rows=[],
        )

    projected_rows = project_pick_inventory_rows(
        snapshots=snapshots,
        obligations=obligations,
        team_code=team_code,
        max_draft_year=max_draft_year,
    )
    pick_rows, asset_rows = build_pick_and_asset_rows_from_projection(projected_rows)
    snapshot_pick_rows = build_roster_snapshot_pick_rows(projected_rows)
    if dry_run:
        return PickInventorySnapshotLoadResult(
            team_code=team_code.upper(),
            max_draft_year=max_draft_year,
            dry_run=True,
            snapshots=len(snapshots),
            obligations=len(obligations),
            blocked_obligations=0,
            existing_snapshot_pick_rows=existing_snapshot_pick_rows,
            projected_rows=len(projected_rows),
            picks_upserted=len(pick_rows),
            assets_upserted=len(asset_rows),
            rows_written=0,
            warnings=[],
            sample_rows=[row.model_dump(mode="json") for row in projected_rows[:20]],
        )

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        transactional_obligations = load_pick_inventory_obligations_from_database(connection, team_code=team_code)
        transactional_warnings = validate_loaded_obligations_for_snapshot_projection(transactional_obligations)
        if transactional_warnings:
            connection.rollback()
            return PickInventorySnapshotLoadResult(
                team_code=team_code.upper(),
                max_draft_year=max_draft_year,
                dry_run=False,
                snapshots=len(snapshots),
                obligations=len(transactional_obligations),
                blocked_obligations=len(transactional_warnings),
                existing_snapshot_pick_rows=existing_snapshot_pick_rows,
                projected_rows=0,
                picks_upserted=0,
                assets_upserted=0,
                rows_written=0,
                warnings=transactional_warnings,
                sample_rows=[],
            )
        transactional_projected_rows = project_pick_inventory_rows(
            snapshots=snapshots,
            obligations=transactional_obligations,
            team_code=team_code,
            max_draft_year=max_draft_year,
        )
        transactional_pick_rows, transactional_asset_rows = build_pick_and_asset_rows_from_projection(transactional_projected_rows)
        transactional_snapshot_pick_rows = build_roster_snapshot_pick_rows(transactional_projected_rows)
        upsert_picks(connection, transactional_pick_rows)
        upsert_assets(connection, transactional_asset_rows)
        replace_roster_snapshot_picks(
            connection,
            transactional_snapshot_pick_rows,
            snapshot_ids=[snapshot.snapshot_id for snapshot in snapshots],
        )
        connection.commit()

    return PickInventorySnapshotLoadResult(
        team_code=team_code.upper(),
        max_draft_year=max_draft_year,
        dry_run=False,
        snapshots=len(snapshots),
        obligations=len(obligations),
        blocked_obligations=0,
        existing_snapshot_pick_rows=existing_snapshot_pick_rows,
        projected_rows=len(projected_rows),
        picks_upserted=len(pick_rows),
        assets_upserted=len(asset_rows),
        rows_written=len(snapshot_pick_rows),
        warnings=[],
        sample_rows=[row.model_dump(mode="json") for row in projected_rows[:20]],
    )


def validate_loaded_obligations_for_snapshot_projection(obligations: list[PickInventoryObligation]) -> list[str]:
    warnings: list[str] = []
    for obligation in obligations:
        if not obligation.loadable:
            continue
        if obligation.confidence == "uncertain":
            warnings.append(f"{obligation.obligation_id}: uncertain obligations cannot be projected into snapshot rows")
    return warnings


def preview_pick_inventory_snapshots(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_FUTURE_PICK_OBLIGATION_PATH,
    max_draft_year: int = 2032,
) -> PickInventoryPreviewResult:
    snapshots = fetch_pick_inventory_snapshots(database_url, team_code=team_code)
    existing_snapshot_pick_rows = fetch_existing_snapshot_pick_count(database_url)
    obligations = load_projectable_future_pick_obligations(fixture_path)
    projected_rows = project_pick_inventory_rows(
        snapshots=snapshots,
        obligations=obligations,
        team_code=team_code,
        max_draft_year=max_draft_year,
    )
    return summarize_pick_inventory_projection(
        snapshots=snapshots,
        obligations=obligations,
        projected_rows=projected_rows,
        team_code=team_code,
        max_draft_year=max_draft_year,
        existing_snapshot_pick_rows=existing_snapshot_pick_rows,
    )


def fetch_pick_inventory_snapshots(database_url: str, *, team_code: str) -> list[PickInventorySnapshot]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        return fetch_pick_inventory_snapshots_from_connection(connection, team_code=team_code)


def fetch_pick_inventory_snapshots_from_connection(
    connection: psycopg.Connection,
    *,
    team_code: str,
) -> list[PickInventorySnapshot]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select snapshot_id, snapshot_date::text, snapshot_kind, season, team_code
            from foundation.roster_snapshot
            where team_code = %s
            order by snapshot_date, snapshot_kind, snapshot_id
            """,
            (team_code.upper(),),
        )
        rows = cursor.fetchall()
    return [
        PickInventorySnapshot(
            snapshot_id=str(row[0]),
            snapshot_date=str(row[1]),
            snapshot_kind=str(row[2]),
            season=str(row[3]),
            team_code=str(row[4]),
        )
        for row in rows
    ]


def fetch_existing_snapshot_pick_count(database_url: str) -> int:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        return fetch_existing_snapshot_pick_count_from_connection(connection)


def fetch_existing_snapshot_pick_count_from_connection(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('foundation.roster_snapshot_pick')")
        if cursor.fetchone()[0] is None:
            return 0
        cursor.execute("select count(*) from foundation.roster_snapshot_pick")
        return int(cursor.fetchone()[0])


def project_pick_inventory_rows(
    *,
    snapshots: list[PickInventorySnapshot],
    obligations: list[PickInventoryObligation],
    team_code: str,
    max_draft_year: int,
) -> list[ProjectedPickInventoryRow]:
    projected: list[ProjectedPickInventoryRow] = []
    team_code = team_code.upper()
    team_obligations = sorted(
        [
            obligation
            for obligation in obligations
            if obligation.perspective_team_code == team_code and is_projectable_pick_inventory_obligation(obligation)
        ],
        key=lambda obligation: (obligation.effective_date, obligation.obligation_id),
    )

    for snapshot in snapshots:
        row_by_pick_id = seed_own_pick_rows(snapshot, team_code=team_code, max_draft_year=max_draft_year)
        snapshot_date = date.fromisoformat(snapshot.snapshot_date)
        for obligation in team_obligations:
            if date.fromisoformat(obligation.effective_date) > snapshot_date:
                continue
            if not is_future_pick(snapshot.snapshot_date, obligation.draft_year, obligation.round_number):
                continue
            apply_obligation_to_snapshot(row_by_pick_id, snapshot, obligation, team_code=team_code)

        ordered_rows = sorted(
            row_by_pick_id.values(),
            key=lambda row: (
                row.draft_year,
                row.round_number,
                holding_status_order(row.holding_status),
                row.original_team,
                row.pick_id,
            ),
        )
        for display_order, row in enumerate(ordered_rows, start=1):
            projected.append(row.model_copy(update={"display_order": display_order}))
    return projected


def seed_own_pick_rows(
    snapshot: PickInventorySnapshot,
    *,
    team_code: str,
    max_draft_year: int,
) -> dict[str, ProjectedPickInventoryRow]:
    rows: dict[str, ProjectedPickInventoryRow] = {}
    for draft_year in range(date.fromisoformat(snapshot.snapshot_date).year, max_draft_year + 1):
        for round_number in (1, 2):
            if not is_future_pick(snapshot.snapshot_date, draft_year, round_number):
                continue
            pick_id = build_own_pick_id(team_code, draft_year, round_number)
            rows[pick_id] = ProjectedPickInventoryRow(
                snapshot_id=snapshot.snapshot_id,
                snapshot_date=snapshot.snapshot_date,
                pick_id=pick_id,
                asset_id=build_pick_asset_id(pick_id),
                draft_year=draft_year,
                round_number=round_number,
                original_team=team_code,
                holding_status="owned",
                display_order=0,
                source_obligation_id=None,
                confidence="derived",
                notes="Default own-pick baseline; should be modified by dated obligations when applicable.",
            )
    return rows


def apply_obligation_to_snapshot(
    row_by_pick_id: dict[str, ProjectedPickInventoryRow],
    snapshot: PickInventorySnapshot,
    obligation: PickInventoryObligation,
    *,
    team_code: str,
) -> None:
    if obligation.direction in ("incoming", "swap_right"):
        pick_id = build_obligation_pick_id(obligation)
        holding_status: PickInventoryHoldingStatus = (
            "swap_right" if obligation.direction == "swap_right" else obligation.holding_status
        )
        row_by_pick_id[pick_id] = build_projected_obligation_row(snapshot, obligation, pick_id, holding_status)
        return

    if obligation.direction in ("outgoing", "swap_obligation"):
        holding_status: PickInventoryHoldingStatus = (
            "encumbered" if obligation.direction == "swap_obligation" else obligation.holding_status
        )
        if obligation.original_team_code == team_code:
            pick_id = build_own_pick_id(team_code, obligation.draft_year, obligation.round_number)
        else:
            pick_id = build_obligation_pick_id(obligation)
        row_by_pick_id[pick_id] = build_projected_obligation_row(snapshot, obligation, pick_id, holding_status)


def build_projected_obligation_row(
    snapshot: PickInventorySnapshot,
    obligation: PickInventoryObligation,
    pick_id: str,
    holding_status: PickInventoryHoldingStatus,
) -> ProjectedPickInventoryRow:
    return ProjectedPickInventoryRow(
        snapshot_id=snapshot.snapshot_id,
        snapshot_date=snapshot.snapshot_date,
        pick_id=pick_id,
        asset_id=build_pick_asset_id(pick_id),
        draft_year=obligation.draft_year,
        round_number=obligation.round_number,
        original_team=obligation.original_team_code or "",
        holding_status=holding_status,
        display_order=0,
        source_obligation_id=obligation.obligation_id,
        confidence=obligation.confidence,
        notes=obligation.notes,
    )


def summarize_pick_inventory_projection(
    *,
    snapshots: list[PickInventorySnapshot],
    obligations: list[PickInventoryObligation],
    projected_rows: list[ProjectedPickInventoryRow],
    team_code: str,
    max_draft_year: int,
    existing_snapshot_pick_rows: int,
) -> PickInventoryPreviewResult:
    kind_counter = Counter()
    snapshot_kind_by_id = {snapshot.snapshot_id: snapshot.snapshot_kind for snapshot in snapshots}
    for row in projected_rows:
        kind_counter[snapshot_kind_by_id.get(row.snapshot_id, "unknown")] += 1
    status_counter = Counter(row.holding_status for row in projected_rows)
    latest_snapshot = build_latest_snapshot_summary(snapshots, projected_rows)
    return PickInventoryPreviewResult(
        team_code=team_code.upper(),
        max_draft_year=max_draft_year,
        snapshots=len(snapshots),
        obligations=len(obligations),
        existing_snapshot_pick_rows=existing_snapshot_pick_rows,
        projected_rows=len(projected_rows),
        proposed_pick_ids=len({row.pick_id for row in projected_rows}),
        proposed_asset_ids=len({row.asset_id for row in projected_rows}),
        by_snapshot_kind=dict(sorted(kind_counter.items())),
        by_holding_status=dict(sorted(status_counter.items())),
        latest_snapshot=latest_snapshot,
        sample_rows=[row.model_dump(mode="json") for row in projected_rows[:20]],
    )


def build_latest_snapshot_summary(
    snapshots: list[PickInventorySnapshot],
    projected_rows: list[ProjectedPickInventoryRow],
) -> dict[str, object] | None:
    if not snapshots:
        return None
    latest_snapshot = max(snapshots, key=lambda snapshot: (snapshot.snapshot_date, snapshot.snapshot_id))
    rows = [row for row in projected_rows if row.snapshot_id == latest_snapshot.snapshot_id]
    status_counter = Counter(row.holding_status for row in rows)
    return {
        "snapshot_id": latest_snapshot.snapshot_id,
        "snapshot_date": latest_snapshot.snapshot_date,
        "snapshot_kind": latest_snapshot.snapshot_kind,
        "rows": len(rows),
        "by_holding_status": dict(sorted(status_counter.items())),
        "sample_rows": [row.model_dump(mode="json") for row in rows[:15]],
    }


def build_pick_and_asset_rows_for_obligations(
    obligations: list[PickInventoryObligation],
) -> tuple[list[PickRow], list[AssetRow]]:
    pick_by_id: dict[str, PickRow] = {}
    asset_by_id: dict[str, AssetRow] = {}
    for obligation in obligations:
        if not is_projectable_pick_inventory_obligation(obligation):
            continue
        pick_id = build_pick_id_for_obligation(obligation)
        pick_by_id[pick_id] = PickRow(
            pick_id=pick_id,
            draft_year=obligation.draft_year,
            round_number=obligation.round_number,
            original_team=obligation.original_team_code,
            protection_text=obligation.protection_text,
            swap_text=obligation.swap_text,
            resolution_status=None,
            raw_text=build_inventory_pick_raw_text(
                draft_year=obligation.draft_year,
                round_number=obligation.round_number,
                original_team=obligation.original_team_code or "UNKNOWN",
                source_id=obligation.obligation_id,
            ),
        )
        asset_id = build_pick_asset_id(pick_id)
        asset_by_id[asset_id] = AssetRow(
            asset_id=asset_id,
            asset_kind="pick",
            pick_id=pick_id,
        )
    return (
        sorted(pick_by_id.values(), key=lambda row: row.pick_id),
        sorted(asset_by_id.values(), key=lambda row: row.asset_id),
    )


def build_pick_and_asset_rows_from_projection(
    projected_rows: list[ProjectedPickInventoryRow],
) -> tuple[list[PickRow], list[AssetRow]]:
    pick_by_id: dict[str, PickRow] = {}
    asset_by_id: dict[str, AssetRow] = {}
    for row in projected_rows:
        pick_by_id[row.pick_id] = PickRow(
            pick_id=row.pick_id,
            draft_year=row.draft_year,
            round_number=row.round_number,
            original_team=row.original_team,
            protection_text=None,
            swap_text=None,
            resolution_status=None,
            raw_text=build_inventory_pick_raw_text(
                draft_year=row.draft_year,
                round_number=row.round_number,
                original_team=row.original_team,
                source_id=row.source_obligation_id or "own-baseline",
            ),
        )
        asset_by_id[row.asset_id] = AssetRow(
            asset_id=row.asset_id,
            asset_kind="pick",
            pick_id=row.pick_id,
        )
    return (
        sorted(pick_by_id.values(), key=lambda item: item.pick_id),
        sorted(asset_by_id.values(), key=lambda item: item.asset_id),
    )


def build_roster_snapshot_pick_rows(projected_rows: list[ProjectedPickInventoryRow]) -> list[RosterSnapshotPickRow]:
    return [
        RosterSnapshotPickRow(
            snapshot_id=row.snapshot_id,
            pick_id=row.pick_id,
            asset_id=row.asset_id,
            holding_status=row.holding_status,
            display_order=row.display_order,
            source_obligation_id=row.source_obligation_id,
            confidence=row.confidence,
            notes=row.notes,
        )
        for row in projected_rows
    ]


def build_pick_id_for_obligation(obligation: PickInventoryObligation) -> str:
    perspective_team_code = obligation.perspective_team_code or obligation.team_code or ""
    if obligation.direction == "own":
        return build_own_pick_id(perspective_team_code, obligation.draft_year, obligation.round_number)
    if obligation.direction in ("outgoing", "swap_obligation") and obligation.original_team_code == perspective_team_code:
        return build_own_pick_id(perspective_team_code, obligation.draft_year, obligation.round_number)
    return build_obligation_pick_id(obligation)


def build_inventory_pick_raw_text(
    *,
    draft_year: int,
    round_number: int,
    original_team: str,
    source_id: str,
) -> str:
    return f"{draft_year} round {round_number} {original_team.upper()} pick inventory row ({source_id})"


def build_own_pick_id(team_code: str, draft_year: int, round_number: int) -> str:
    return f"pick:inventory:{team_code.lower()}:{draft_year}:r{round_number}:own"


def build_obligation_pick_id(obligation: PickInventoryObligation) -> str:
    return (
        f"pick:inventory:{(obligation.perspective_team_code or '').lower()}:{obligation.draft_year}:"
        f"r{obligation.round_number}:{(obligation.original_team_code or '').lower()}"
    )


def build_pick_asset_id(pick_id: str) -> str:
    return f"asset:pick:{pick_id}"


def is_future_pick(snapshot_date: str, draft_year: int, round_number: int) -> bool:
    return date.fromisoformat(snapshot_date) < date.fromisoformat(resolve_draft_date(draft_year, round_number))


def resolve_draft_date(draft_year: int, round_number: int) -> str:
    try:
        return draft_resolution_event_date(draft_year, round_number)
    except ValueError:
        return f"{draft_year}-06-30"


def holding_status_order(holding_status: PickInventoryHoldingStatus) -> int:
    return {
        "owned": 0,
        "swap_right": 1,
        "conditional": 2,
        "encumbered": 3,
        "owed_out": 4,
    }[holding_status]


def normalize_team_code(value: str | None) -> str:
    return value.strip().upper() if value and value.strip() else ""


def is_projectable_pick_inventory_obligation(obligation: PickInventoryObligation) -> bool:
    return obligation.loadable and obligation.confidence != "uncertain"


def infer_owner_team_code(
    *,
    perspective_team_code: str,
    direction: PickInventoryDirection,
) -> str:
    if direction in ("incoming", "own", "swap_right"):
        return perspective_team_code
    return "UNKNOWN"
