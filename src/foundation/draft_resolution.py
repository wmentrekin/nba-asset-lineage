from __future__ import annotations

from typing import Literal

import psycopg
from pydantic import BaseModel, Field


ResolutionStatus = Literal["linked", "candidate", "ambiguous", "unmatched"]
ResolutionConfidence = Literal["high", "medium", "low", "none"]


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


def preview_draft_pick_resolution(database_url: str, *, team_code: str = "MEM") -> DraftSelectionResolutionPreview:
    selections = load_draft_selections_for_resolution(database_url, team_code=team_code)
    picks = load_pick_candidates_for_resolution(database_url)
    return build_draft_pick_resolution_preview(selections=selections, picks=picks)


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
