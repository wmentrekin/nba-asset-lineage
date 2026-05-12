from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, Field


ResolutionStatus = Literal["linked", "candidate", "ambiguous", "unmatched"]
ResolutionConfidence = Literal["high", "medium", "low", "none"]
CuratedWriteAction = Literal["link_existing_pick", "create_pick_and_link", "blocked"]
CuratedDbSelectionStatus = Literal["matched", "missing", "mismatch"]
DEFAULT_CURATED_DRAFT_PICK_RESOLUTION_PATH = Path("configs/data/memphis_draft_pick_resolution_2016_2025.json")


class DraftSelectionForResolution(BaseModel):
    draft_selection_id: str
    draft_year: int
    pick_overall: int
    round_number: int
    team_code: str
    player_id: str
    player_name: str | None = None
    pick_id: str | None = None
    source_event_id: str | None = None


class PickCandidateForResolution(BaseModel):
    pick_id: str
    asset_id: str | None = None
    draft_year: int
    round_number: int
    original_team: str | None = None
    protection_text: str | None = None
    swap_text: str | None = None
    raw_text: str


class DraftSelectionResolutionRow(BaseModel):
    draft_selection_id: str
    draft_year: int
    pick_overall: int
    round_number: int
    team_code: str
    player_id: str
    player_name: str | None
    status: ResolutionStatus
    confidence: ResolutionConfidence
    reason: str
    matched_pick_id: str | None = None
    matched_pick_asset_id: str | None = None
    candidate_pick_ids: list[str] = Field(default_factory=list)
    candidate_pick_asset_ids: list[str] = Field(default_factory=list)


class DraftSelectionResolutionPreview(BaseModel):
    status: Literal["ok"] = "ok"
    selections: int
    linked: int
    candidate: int
    ambiguous: int
    unmatched: int
    rows: list[DraftSelectionResolutionRow]
    known_limitations: list[str]


class CuratedDraftPickResolutionRow(BaseModel):
    draft_selection_id: str
    draft_year: int
    round_number: int
    pick_overall: int
    team_code: str
    player_name: str
    source_locator: str
    confidence: ResolutionConfidence
    notes: str | None = None


class CuratedDraftPickResolutionBundle(BaseModel):
    source_bundle_id: str
    description: str
    rows: list[CuratedDraftPickResolutionRow]


class CuratedDraftPickResolutionPreviewRow(BaseModel):
    draft_selection_id: str
    draft_year: int
    round_number: int
    pick_overall: int
    team_code: str
    player_name: str
    db_selection_status: CuratedDbSelectionStatus
    write_action: CuratedWriteAction
    ready_for_write: bool
    confidence: ResolutionConfidence
    proposed_pick_id: str
    proposed_pick_asset_id: str
    proposed_raw_text: str
    existing_pick_id: str | None = None
    existing_pick_asset_id: str | None = None
    current_resolver_status: ResolutionStatus | None = None
    current_resolver_reason: str | None = None
    source_locator: str
    notes: str | None = None
    issues: list[str] = Field(default_factory=list)


class CuratedDraftPickResolutionPreview(BaseModel):
    status: Literal["ok"] = "ok"
    source_bundle_id: str
    fixture_path: str
    fixture_rows: int
    matched_db_selections: int
    missing_db_selections: int
    mismatched_db_selections: int
    ready_for_write: int
    blocked: int
    existing_pick_matches: int
    proposed_new_picks: int
    rows: list[CuratedDraftPickResolutionPreviewRow]
    known_limitations: list[str]


def preview_draft_pick_resolution(database_url: str, *, team_code: str = "MEM") -> DraftSelectionResolutionPreview:
    selections = load_draft_selections_for_resolution(database_url, team_code=team_code)
    picks = load_pick_candidates_for_resolution(database_url)
    return build_draft_pick_resolution_preview(selections=selections, picks=picks)


def preview_curated_draft_pick_resolution(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_CURATED_DRAFT_PICK_RESOLUTION_PATH,
) -> CuratedDraftPickResolutionPreview:
    bundle = load_curated_draft_pick_resolution_bundle(fixture_path)
    selections = load_draft_selections_for_resolution(database_url, team_code=team_code)
    picks = load_pick_candidates_for_resolution(database_url)
    current_preview = build_draft_pick_resolution_preview(selections=selections, picks=picks)
    return build_curated_draft_pick_resolution_preview(
        bundle=bundle,
        fixture_path=fixture_path,
        selections=selections,
        picks=picks,
        current_preview=current_preview,
        team_code=team_code,
    )


def build_draft_pick_resolution_preview(
    *,
    selections: list[DraftSelectionForResolution],
    picks: list[PickCandidateForResolution],
) -> DraftSelectionResolutionPreview:
    selection_counts_by_year_round: dict[tuple[int, int], int] = {}
    for selection in selections:
        key = (selection.draft_year, selection.round_number)
        selection_counts_by_year_round[key] = selection_counts_by_year_round.get(key, 0) + 1
    rows = [
        resolve_draft_selection(
            selection,
            picks,
            same_year_round_selection_count=selection_counts_by_year_round[
                (selection.draft_year, selection.round_number)
            ],
        )
        for selection in selections
    ]
    return DraftSelectionResolutionPreview(
        selections=len(rows),
        linked=sum(1 for row in rows if row.status == "linked"),
        candidate=sum(1 for row in rows if row.status == "candidate"),
        ambiguous=sum(1 for row in rows if row.status == "ambiguous"),
        unmatched=sum(1 for row in rows if row.status == "unmatched"),
        rows=rows,
        known_limitations=[
            "This command is read-only and does not mutate draft_selection.pick_id.",
            "Basketball-Reference draft rows prove selected players, not prior pick ownership.",
            "Current pick assets are derived mostly from transaction text, so owned picks may be absent.",
            "Exact pick-overall matching is not possible until pick assets carry pick_overall or a resolution table exists.",
        ],
    )


def build_curated_draft_pick_resolution_preview(
    *,
    bundle: CuratedDraftPickResolutionBundle,
    fixture_path: Path,
    selections: list[DraftSelectionForResolution],
    picks: list[PickCandidateForResolution],
    current_preview: DraftSelectionResolutionPreview,
    team_code: str,
) -> CuratedDraftPickResolutionPreview:
    validate_curated_resolution_bundle(bundle)
    selection_by_id = {selection.draft_selection_id: selection for selection in selections}
    pick_by_id = {pick.pick_id: pick for pick in picks}
    current_by_id = {row.draft_selection_id: row for row in current_preview.rows}

    rows = [
        build_curated_preview_row(
            row,
            db_selection=selection_by_id.get(row.draft_selection_id),
            existing_pick=pick_by_id.get(build_slot_pick_id(row.draft_year, row.pick_overall)),
            current_resolution=current_by_id.get(row.draft_selection_id),
            expected_team_code=team_code,
        )
        for row in bundle.rows
        if row.team_code.upper() == team_code.upper()
    ]
    return CuratedDraftPickResolutionPreview(
        source_bundle_id=bundle.source_bundle_id,
        fixture_path=str(fixture_path),
        fixture_rows=len(rows),
        matched_db_selections=sum(1 for row in rows if row.db_selection_status == "matched"),
        missing_db_selections=sum(1 for row in rows if row.db_selection_status == "missing"),
        mismatched_db_selections=sum(1 for row in rows if row.db_selection_status == "mismatch"),
        ready_for_write=sum(1 for row in rows if row.ready_for_write),
        blocked=sum(1 for row in rows if not row.ready_for_write),
        existing_pick_matches=sum(1 for row in rows if row.existing_pick_id is not None),
        proposed_new_picks=sum(1 for row in rows if row.ready_for_write and row.existing_pick_id is None),
        rows=rows,
        known_limitations=[
            "This command is read-only and does not mutate pick, asset, or draft_selection rows.",
            "The curated fixture asserts draft slot selection truth, not full prior pick-ownership or protection truth.",
            "Rows marked create_pick_and_link still require a future SQL schema/write-path decision.",
            "Draft-night trades are intentionally noted but not modeled as pick-to-player-to-trade transitions by this preview.",
        ],
    )


def build_curated_preview_row(
    row: CuratedDraftPickResolutionRow,
    *,
    db_selection: DraftSelectionForResolution | None,
    existing_pick: PickCandidateForResolution | None,
    current_resolution: DraftSelectionResolutionRow | None,
    expected_team_code: str,
) -> CuratedDraftPickResolutionPreviewRow:
    issues = collect_curated_row_issues(row, db_selection=db_selection, expected_team_code=expected_team_code)
    db_selection_status: CuratedDbSelectionStatus
    if db_selection is None:
        db_selection_status = "missing"
    elif issues:
        db_selection_status = "mismatch"
    else:
        db_selection_status = "matched"

    proposed_pick_id = build_slot_pick_id(row.draft_year, row.pick_overall)
    proposed_pick_asset_id = build_slot_pick_asset_id(row.draft_year, row.pick_overall)
    ready_for_write = db_selection_status == "matched"
    if not ready_for_write:
        write_action: CuratedWriteAction = "blocked"
    elif existing_pick is not None:
        write_action = "link_existing_pick"
    else:
        write_action = "create_pick_and_link"

    return CuratedDraftPickResolutionPreviewRow(
        draft_selection_id=row.draft_selection_id,
        draft_year=row.draft_year,
        round_number=row.round_number,
        pick_overall=row.pick_overall,
        team_code=row.team_code,
        player_name=row.player_name,
        db_selection_status=db_selection_status,
        write_action=write_action,
        ready_for_write=ready_for_write,
        confidence=row.confidence,
        proposed_pick_id=proposed_pick_id,
        proposed_pick_asset_id=proposed_pick_asset_id,
        proposed_raw_text=build_slot_pick_raw_text(row),
        existing_pick_id=existing_pick.pick_id if existing_pick is not None else None,
        existing_pick_asset_id=existing_pick.asset_id if existing_pick is not None else None,
        current_resolver_status=current_resolution.status if current_resolution is not None else None,
        current_resolver_reason=current_resolution.reason if current_resolution is not None else None,
        source_locator=row.source_locator,
        notes=row.notes,
        issues=issues,
    )


def collect_curated_row_issues(
    row: CuratedDraftPickResolutionRow,
    *,
    db_selection: DraftSelectionForResolution | None,
    expected_team_code: str,
) -> list[str]:
    issues: list[str] = []
    if row.team_code.upper() != expected_team_code.upper():
        issues.append(f"fixture team_code {row.team_code} does not match expected team {expected_team_code.upper()}")
    if db_selection is None:
        issues.append("draft_selection row is missing from the database")
        return issues
    if db_selection.draft_year != row.draft_year:
        issues.append(f"database draft_year {db_selection.draft_year} does not match fixture {row.draft_year}")
    if db_selection.round_number != row.round_number:
        issues.append(f"database round_number {db_selection.round_number} does not match fixture {row.round_number}")
    if db_selection.pick_overall != row.pick_overall:
        issues.append(f"database pick_overall {db_selection.pick_overall} does not match fixture {row.pick_overall}")
    if db_selection.team_code.upper() != row.team_code.upper():
        issues.append(f"database team_code {db_selection.team_code} does not match fixture {row.team_code}")
    if db_selection.player_name and normalize_name_for_compare(db_selection.player_name) != normalize_name_for_compare(row.player_name):
        issues.append(f"database player_name {db_selection.player_name} does not match fixture {row.player_name}")
    return issues


def validate_curated_resolution_bundle(bundle: CuratedDraftPickResolutionBundle) -> None:
    seen_selection_ids: set[str] = set()
    seen_slots: set[tuple[int, int]] = set()
    for row in bundle.rows:
        if row.draft_selection_id in seen_selection_ids:
            raise ValueError(f"Duplicate draft_selection_id in curated fixture: {row.draft_selection_id}")
        seen_selection_ids.add(row.draft_selection_id)
        slot = (row.draft_year, row.pick_overall)
        if slot in seen_slots:
            raise ValueError(f"Duplicate draft slot in curated fixture: {row.draft_year} pick {row.pick_overall}")
        seen_slots.add(slot)


def load_curated_draft_pick_resolution_bundle(path: Path) -> CuratedDraftPickResolutionBundle:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CuratedDraftPickResolutionBundle.model_validate(payload)


def build_slot_pick_id(draft_year: int, pick_overall: int) -> str:
    return f"pick:slot:{draft_year}:{pick_overall}"


def build_slot_pick_asset_id(draft_year: int, pick_overall: int) -> str:
    return f"asset:pick:{build_slot_pick_id(draft_year, pick_overall)}"


def build_slot_pick_raw_text(row: CuratedDraftPickResolutionRow) -> str:
    return f"{row.draft_year} NBA draft pick No. {row.pick_overall} selected by {row.team_code.upper()}"


def normalize_name_for_compare(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def resolve_draft_selection(
    selection: DraftSelectionForResolution,
    picks: list[PickCandidateForResolution],
    *,
    same_year_round_selection_count: int = 1,
) -> DraftSelectionResolutionRow:
    if selection.pick_id:
        linked_pick = next((pick for pick in picks if pick.pick_id == selection.pick_id), None)
        if linked_pick is not None:
            return build_resolution_row(
                selection,
                status="linked",
                confidence="high",
                reason="draft_selection already has a pick_id that exists in foundation.pick",
                matched_pick=linked_pick,
            )
        return build_resolution_row(
            selection,
            status="linked",
            confidence="medium",
            reason="draft_selection already has a pick_id, but no matching foundation.pick row was found",
            matched_pick_id=selection.pick_id,
        )

    year_round_candidates = [
        pick
        for pick in picks
        if pick.draft_year == selection.draft_year and pick.round_number == selection.round_number
    ]
    if not year_round_candidates:
        return build_resolution_row(
            selection,
            status="unmatched",
            confidence="none",
            reason="no pick asset exists for this draft year and round; this is likely an owned pick or missing pick-inventory row",
        )
    if same_year_round_selection_count > 1:
        return build_resolution_row(
            selection,
            status="ambiguous",
            confidence="none",
            reason="multiple Memphis selections share this draft year and round, but pick assets do not carry pick_overall",
            candidate_picks=year_round_candidates,
        )

    team_candidates = [
        pick
        for pick in year_round_candidates
        if pick_matches_selection_team(pick, selection.team_code)
    ]
    if len(team_candidates) == 1:
        return build_resolution_row(
            selection,
            status="candidate",
            confidence="medium",
            reason="one same-year same-round pick asset appears to match the selecting team, but pick_overall is not represented on pick assets",
            matched_pick=team_candidates[0],
            candidate_picks=year_round_candidates,
        )
    if len(year_round_candidates) == 1:
        return build_resolution_row(
            selection,
            status="candidate",
            confidence="low",
            reason="one same-year same-round pick asset exists, but original-team ownership does not clearly match the selecting team",
            matched_pick=year_round_candidates[0],
            candidate_picks=year_round_candidates,
        )

    return build_resolution_row(
        selection,
        status="ambiguous",
        confidence="none",
        reason="multiple same-year same-round pick assets exist and no unique team-matching candidate can be selected safely",
        candidate_picks=team_candidates or year_round_candidates,
    )


def build_resolution_row(
    selection: DraftSelectionForResolution,
    *,
    status: ResolutionStatus,
    confidence: ResolutionConfidence,
    reason: str,
    matched_pick: PickCandidateForResolution | None = None,
    matched_pick_id: str | None = None,
    candidate_picks: list[PickCandidateForResolution] | None = None,
) -> DraftSelectionResolutionRow:
    candidates = candidate_picks or ([] if matched_pick is None else [matched_pick])
    return DraftSelectionResolutionRow(
        draft_selection_id=selection.draft_selection_id,
        draft_year=selection.draft_year,
        pick_overall=selection.pick_overall,
        round_number=selection.round_number,
        team_code=selection.team_code,
        player_id=selection.player_id,
        player_name=selection.player_name,
        status=status,
        confidence=confidence,
        reason=reason,
        matched_pick_id=matched_pick.pick_id if matched_pick else matched_pick_id,
        matched_pick_asset_id=matched_pick.asset_id if matched_pick else None,
        candidate_pick_ids=[pick.pick_id for pick in candidates],
        candidate_pick_asset_ids=[pick.asset_id for pick in candidates if pick.asset_id],
    )


def pick_matches_selection_team(pick: PickCandidateForResolution, team_code: str) -> bool:
    normalized_team = team_code.upper()
    if pick.original_team and pick.original_team.upper() == normalized_team:
        return True
    raw_text = pick.raw_text.upper()
    return f"{normalized_team} OWN" in raw_text or normalized_team == "MEM" and "MEMPHIS" in raw_text


def load_draft_selections_for_resolution(
    database_url: str,
    *,
    team_code: str,
) -> list[DraftSelectionForResolution]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select ds.draft_selection_id,
                       ds.draft_year,
                       ds.pick_overall,
                       ds.round_number,
                       ds.team_code,
                       ds.player_id,
                       p.display_name,
                       ds.pick_id,
                       ds.source_event_id
                from foundation.draft_selection ds
                left join foundation.player p on p.player_id = ds.player_id
                where ds.team_code = %s
                order by ds.draft_year, ds.pick_overall, ds.draft_selection_id
                """,
                (team_code.upper(),),
            )
            rows = cursor.fetchall()
    return [
        DraftSelectionForResolution(
            draft_selection_id=str(row[0]),
            draft_year=int(row[1]),
            pick_overall=int(row[2]),
            round_number=int(row[3]),
            team_code=str(row[4]),
            player_id=str(row[5]),
            player_name=str(row[6]) if row[6] is not None else None,
            pick_id=str(row[7]) if row[7] is not None else None,
            source_event_id=str(row[8]) if row[8] is not None else None,
        )
        for row in rows
    ]


def load_pick_candidates_for_resolution(database_url: str) -> list[PickCandidateForResolution]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select pk.pick_id,
                       a.asset_id,
                       pk.draft_year,
                       pk.round_number,
                       pk.original_team,
                       pk.protection_text,
                       pk.swap_text,
                       pk.raw_text
                from foundation.pick pk
                left join foundation.asset a on a.pick_id = pk.pick_id and a.asset_kind = 'pick'
                order by pk.draft_year, pk.round_number, pk.pick_id
                """
            )
            rows = cursor.fetchall()
    return [
        PickCandidateForResolution(
            pick_id=str(row[0]),
            asset_id=str(row[1]) if row[1] is not None else None,
            draft_year=int(row[2]),
            round_number=int(row[3]),
            original_team=str(row[4]) if row[4] is not None else None,
            protection_text=str(row[5]) if row[5] is not None else None,
            swap_text=str(row[6]) if row[6] is not None else None,
            raw_text=str(row[7]),
        )
        for row in rows
    ]
