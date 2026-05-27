from __future__ import annotations

from collections import defaultdict
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from foundation.draft_resolution import PickCandidateForResolution
from foundation.pick_inventory import PickInventoryObligation
from foundation.pick_inventory import PickInventorySnapshot
from foundation.pick_inventory import build_inventory_pick_raw_text
from foundation.pick_inventory import build_own_pick_id
from foundation.pick_inventory import build_pick_asset_id
from foundation.pick_inventory import load_pick_inventory_obligations_from_database
from foundation.pick_inventory import project_pick_inventory_rows
from foundation.pick_inventory import resolve_draft_date


PriorOwnerResolutionKind = Literal[
    "resolved_pick_original_team",
    "inventory_exact_pick",
    "inventory_single_candidate",
    "team_default_fallback",
    "curated_override",
]
PriorOwnerRowStatus = Literal["resolved", "ambiguous", "unmatched"]
ResolutionConfidence = Literal["high", "medium", "low", "none"]
CONTROLLED_HOLDING_STATUSES = {"owned", "swap_right", "conditional"}
FOUNDATION_DRAFT_PRIOR_OWNER_BOOTSTRAP_SQL_PATH = Path("sql/0007_foundation_daily_roster_and_prior_owner_bootstrap.sql")
DEFAULT_DRAFT_PRIOR_OWNER_OVERRIDE_PATH = Path("configs/data/memphis_draft_prior_owner_overrides_2016_2025.json")


class DraftSelectionForPriorOwnerLineage(BaseModel):
    draft_selection_id: str
    draft_year: int
    pick_overall: int
    round_number: int
    team_code: str
    player_id: str
    player_name: str | None = None
    pick_id: str | None = None
    draft_pick_resolution_id: str | None = None
    player_asset_id: str | None = None


class DraftPriorOwnerOverrideRow(BaseModel):
    draft_selection_id: str
    draft_year: int
    round_number: int
    pick_overall: int
    team_code: str
    original_team_code: str
    source_locator: str
    confidence: ResolutionConfidence = "high"
    notes: str | None = None


class DraftPriorOwnerOverrideFixture(BaseModel):
    fixture_id: str
    team_code: str
    rows: list[DraftPriorOwnerOverrideRow]


class DraftPriorOwnerLineageRow(BaseModel):
    draft_prior_owner_lineage_id: str
    draft_selection_id: str
    draft_pick_resolution_id: str | None = None
    pick_id: str | None = None
    pick_asset_id: str | None = None
    player_id: str
    player_asset_id: str | None = None
    player_name: str | None = None
    draft_year: int
    round_number: int
    pick_overall: int
    team_code: str
    owner_team_code: str | None = None
    original_team_code: str | None = None
    source_obligation_id: str | None = None
    resolution_kind: PriorOwnerResolutionKind | None = None
    confidence: ResolutionConfidence = "none"
    status: PriorOwnerRowStatus
    reason: str
    candidate_pick_ids: list[str] = Field(default_factory=list)
    candidate_original_team_codes: list[str] = Field(default_factory=list)
    notes: str | None = None


class DraftPriorOwnerLineagePreviewResult(BaseModel):
    status: Literal["ok"] = "ok"
    team_code: str
    selections: int
    resolved: int
    ambiguous: int
    unmatched: int
    rows: list[DraftPriorOwnerLineageRow]
    known_limitations: list[str]


class DraftPriorOwnerLineageLoadResult(BaseModel):
    status: Literal["ok"] = "ok"
    team_code: str
    dry_run: bool
    ready_rows: int
    blocked_rows: int
    picks_inserted: int
    assets_inserted: int
    lineages_upserted: int
    rows: list[DraftPriorOwnerLineageRow]
    known_limitations: list[str]


def bootstrap_foundation_draft_prior_owner_schema(
    database_url: str,
    sql_path: Path = FOUNDATION_DRAFT_PRIOR_OWNER_BOOTSTRAP_SQL_PATH,
) -> None:
    sql_text = sql_path.read_text(encoding="utf-8")
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql_text)
        connection.commit()


def build_draft_prior_owner_lineage_rows(
    *,
    selections: list[DraftSelectionForPriorOwnerLineage],
    pick_candidates: list[PickCandidateForResolution],
    obligations: list[PickInventoryObligation],
    team_code: str = "MEM",
    overrides: list[DraftPriorOwnerOverrideRow] | None = None,
) -> list[DraftPriorOwnerLineageRow]:
    if not selections:
        return []

    normalized_team_code = team_code.upper()
    filtered_selections = sorted(
        [selection for selection in selections if selection.team_code.upper() == normalized_team_code],
        key=lambda selection: (selection.draft_year, selection.round_number, selection.pick_overall, selection.draft_selection_id),
    )
    if not filtered_selections:
        return []

    pick_by_id = {pick.pick_id: pick for pick in pick_candidates}
    override_by_selection_id = {
        row.draft_selection_id: row
        for row in (overrides or [])
        if row.team_code.upper() == normalized_team_code
    }
    projected_rows_by_snapshot_id = build_projected_rows_by_snapshot_id(
        selections=filtered_selections,
        obligations=obligations,
        team_code=normalized_team_code,
    )

    grouped_selections: dict[tuple[int, int], list[DraftSelectionForPriorOwnerLineage]] = defaultdict(list)
    for selection in filtered_selections:
        grouped_selections[(selection.draft_year, selection.round_number)].append(selection)

    rows_by_selection_id: dict[str, DraftPriorOwnerLineageRow] = {}
    for key in sorted(grouped_selections):
        group = grouped_selections[key]
        group_rows = resolve_selection_group(
            selections=group,
            pick_by_id=pick_by_id,
            projected_rows=projected_rows_by_snapshot_id.get(build_pre_draft_snapshot_id(group[0]), []),
            team_code=normalized_team_code,
            override_by_selection_id=override_by_selection_id,
        )
        rows_by_selection_id.update({row.draft_selection_id: row for row in group_rows})

    return [rows_by_selection_id[selection.draft_selection_id] for selection in filtered_selections]


def build_draft_prior_owner_lineage_rows_from_database(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_DRAFT_PRIOR_OWNER_OVERRIDE_PATH,
) -> list[DraftPriorOwnerLineageRow]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        selections = load_draft_selections_for_prior_owner_lineage(connection, team_code=team_code)
        pick_candidates = load_pick_candidates_for_prior_owner_lineage(connection)
        obligations = load_pick_inventory_obligations_from_database(connection, team_code=team_code)
    overrides = load_draft_prior_owner_override_fixture(fixture_path).rows
    return build_draft_prior_owner_lineage_rows(
        selections=selections,
        pick_candidates=pick_candidates,
        obligations=obligations,
        team_code=team_code,
        overrides=overrides,
    )


def preview_draft_prior_owner_lineage(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_DRAFT_PRIOR_OWNER_OVERRIDE_PATH,
) -> DraftPriorOwnerLineagePreviewResult:
    rows = build_draft_prior_owner_lineage_rows_from_database(
        database_url,
        team_code=team_code,
        fixture_path=fixture_path,
    )
    return build_draft_prior_owner_lineage_preview(rows=rows, team_code=team_code)


def load_draft_prior_owner_lineage(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_DRAFT_PRIOR_OWNER_OVERRIDE_PATH,
    dry_run: bool = False,
) -> DraftPriorOwnerLineageLoadResult:
    preview = preview_draft_prior_owner_lineage(
        database_url,
        team_code=team_code,
        fixture_path=fixture_path,
    )
    ready_rows = [row for row in preview.rows if row.status == "resolved"]
    if preview.ambiguous or preview.unmatched:
        return DraftPriorOwnerLineageLoadResult(
            team_code=preview.team_code,
            dry_run=dry_run,
            ready_rows=len(ready_rows),
            blocked_rows=preview.ambiguous + preview.unmatched,
            picks_inserted=0,
            assets_inserted=0,
            lineages_upserted=0,
            rows=preview.rows,
            known_limitations=preview.known_limitations,
        )

    unique_pick_ids = {row.pick_id for row in ready_rows if row.pick_id}
    unique_asset_ids = {row.pick_asset_id for row in ready_rows if row.pick_asset_id}
    if dry_run:
        return DraftPriorOwnerLineageLoadResult(
            team_code=preview.team_code,
            dry_run=True,
            ready_rows=len(ready_rows),
            blocked_rows=0,
            picks_inserted=len(unique_pick_ids),
            assets_inserted=len(unique_asset_ids),
            lineages_upserted=len(ready_rows),
            rows=preview.rows,
            known_limitations=preview.known_limitations,
        )

    bootstrap_foundation_draft_prior_owner_schema(database_url)
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        picks_inserted, assets_inserted = insert_missing_prior_owner_pick_rows(connection, ready_rows)
        lineages_upserted = upsert_draft_prior_owner_lineage_rows(connection, ready_rows)
        connection.commit()
    return DraftPriorOwnerLineageLoadResult(
        team_code=preview.team_code,
        dry_run=False,
        ready_rows=len(ready_rows),
        blocked_rows=0,
        picks_inserted=picks_inserted,
        assets_inserted=assets_inserted,
        lineages_upserted=lineages_upserted,
        rows=preview.rows,
        known_limitations=preview.known_limitations,
    )


def build_draft_prior_owner_lineage_preview(
    *,
    rows: list[DraftPriorOwnerLineageRow],
    team_code: str,
) -> DraftPriorOwnerLineagePreviewResult:
    normalized_team_code = team_code.upper()
    return DraftPriorOwnerLineagePreviewResult(
        team_code=normalized_team_code,
        selections=len(rows),
        resolved=sum(1 for row in rows if row.status == "resolved"),
        ambiguous=sum(1 for row in rows if row.status == "ambiguous"),
        unmatched=sum(1 for row in rows if row.status == "unmatched"),
        rows=rows,
        known_limitations=[
            "This derivation uses pre-draft inventory projection plus existing non-slot pick links; it does not solve every conditional branch.",
            "Multiple Memphis selections in the same draft year and round remain ambiguous unless an exact non-slot pick link already exists.",
            "The loader writes a separate prior-owner lineage surface and does not mutate draft_selection or draft_pick_resolution semantics.",
        ],
    )


def build_projected_rows_by_snapshot_id(
    *,
    selections: list[DraftSelectionForPriorOwnerLineage],
    obligations: list[PickInventoryObligation],
    team_code: str,
) -> dict[str, list[object]]:
    projectable_obligations = [
        obligation
        for obligation in obligations
        if obligation.loadable and obligation.confidence != "uncertain"
    ]
    snapshots = build_pre_draft_snapshots(selections, team_code=team_code)
    if not snapshots:
        return {}
    projected_rows = project_pick_inventory_rows(
        snapshots=snapshots,
        obligations=projectable_obligations,
        team_code=team_code,
        max_draft_year=max(selection.draft_year for selection in selections),
    )
    rows_by_snapshot_id: dict[str, list[object]] = defaultdict(list)
    for row in projected_rows:
        rows_by_snapshot_id[row.snapshot_id].append(row)
    return dict(rows_by_snapshot_id)


def build_pre_draft_snapshots(
    selections: list[DraftSelectionForPriorOwnerLineage],
    *,
    team_code: str,
) -> list[PickInventorySnapshot]:
    snapshot_by_id: dict[str, PickInventorySnapshot] = {}
    for selection in selections:
        snapshot_id = build_pre_draft_snapshot_id(selection)
        snapshot_date = (
            date.fromisoformat(resolve_draft_date(selection.draft_year, selection.round_number)) - timedelta(days=1)
        ).isoformat()
        snapshot_by_id[snapshot_id] = PickInventorySnapshot(
            snapshot_id=snapshot_id,
            snapshot_date=snapshot_date,
            snapshot_kind="pre_draft",
            season=build_draft_season(selection.draft_year),
            team_code=team_code.upper(),
        )
    return [snapshot_by_id[key] for key in sorted(snapshot_by_id)]


def build_pre_draft_snapshot_id(selection: DraftSelectionForPriorOwnerLineage) -> str:
    return (
        f"snapshot:prior-owner:{selection.team_code.lower()}:{selection.draft_year}:"
        f"r{selection.round_number}:pre_draft"
    )


def build_draft_season(draft_year: int) -> str:
    return f"{draft_year - 1}-{str(draft_year)[2:]}"


def resolve_selection_group(
    *,
    selections: list[DraftSelectionForPriorOwnerLineage],
    pick_by_id: dict[str, PickCandidateForResolution],
    projected_rows: list[object],
    team_code: str,
    override_by_selection_id: dict[str, DraftPriorOwnerOverrideRow],
) -> list[DraftPriorOwnerLineageRow]:
    resolved_rows: list[DraftPriorOwnerLineageRow] = []
    consumed_pick_ids: set[str] = set()
    remaining: list[DraftSelectionForPriorOwnerLineage] = []

    for selection in selections:
        override = override_by_selection_id.get(selection.draft_selection_id)
        if override is not None:
            override_row = resolve_curated_override(selection, override=override, team_code=team_code)
            resolved_rows.append(override_row)
            if override_row.pick_id:
                consumed_pick_ids.add(override_row.pick_id)
            continue
        exact_row = resolve_existing_pick_link(selection, pick_by_id=pick_by_id, team_code=team_code)
        if exact_row is None:
            remaining.append(selection)
            continue
        resolved_rows.append(exact_row)
        if exact_row.pick_id:
            consumed_pick_ids.add(exact_row.pick_id)

    available_projected_rows = [
        row
        for row in projected_rows
        if getattr(row, "pick_id", None) not in consumed_pick_ids
        and getattr(row, "draft_year", None) == selections[0].draft_year
        and getattr(row, "round_number", None) == selections[0].round_number
    ]
    controlled_candidates = [
        row for row in available_projected_rows if getattr(row, "holding_status", None) in CONTROLLED_HOLDING_STATUSES
    ]
    if len(remaining) > 1:
        status = "ambiguous" if controlled_candidates else "unmatched"
        reason = (
            "multiple Memphis selections share this draft year and round, "
            "and pre-draft inventory does not carry pick_overall to map remaining picks safely"
        )
        resolved_rows.extend(
            [
                build_unresolved_lineage_row(
                    selection,
                    status=status,
                    reason=reason,
                    candidate_rows=controlled_candidates,
                )
                for selection in remaining
            ]
        )
        return sorted(resolved_rows, key=selection_row_sort_key)

    if not remaining:
        return sorted(resolved_rows, key=selection_row_sort_key)

    resolved_rows.append(
        resolve_single_inventory_selection(
            remaining[0],
            candidate_rows=controlled_candidates,
            all_same_round_rows=available_projected_rows,
            team_code=team_code,
        )
    )
    return sorted(resolved_rows, key=selection_row_sort_key)


def resolve_curated_override(
    selection: DraftSelectionForPriorOwnerLineage,
    *,
    override: DraftPriorOwnerOverrideRow,
    team_code: str,
) -> DraftPriorOwnerLineageRow:
    original_team_code = normalize_team_code(override.original_team_code) or team_code
    pick_id = build_prior_owner_pick_id(
        team_code=team_code,
        draft_year=selection.draft_year,
        round_number=selection.round_number,
        original_team_code=original_team_code,
    )
    return build_resolved_lineage_row(
        selection,
        pick_id=pick_id,
        pick_asset_id=build_pick_asset_id(pick_id),
        owner_team_code=team_code,
        original_team_code=original_team_code,
        source_obligation_id=None,
        resolution_kind="curated_override",
        confidence=override.confidence,
        reason=f"curated override from {override.source_locator}",
        candidate_pick_ids=[pick_id],
        candidate_original_team_codes=[original_team_code],
        notes=override.notes,
    )


def resolve_existing_pick_link(
    selection: DraftSelectionForPriorOwnerLineage,
    *,
    pick_by_id: dict[str, PickCandidateForResolution],
    team_code: str,
) -> DraftPriorOwnerLineageRow | None:
    if not selection.pick_id or is_slot_pick_id(selection.pick_id):
        return None
    pick = pick_by_id.get(selection.pick_id)
    if pick is None or pick.draft_year != selection.draft_year or pick.round_number != selection.round_number:
        return None
    original_team_code = normalize_team_code(pick.original_team)
    if not original_team_code:
        return None
    reason = "draft_selection already links to a non-slot pick row with original_team populated"
    return build_resolved_lineage_row(
        selection,
        pick_id=pick.pick_id,
        pick_asset_id=pick.asset_id or build_pick_asset_id(pick.pick_id),
        owner_team_code=team_code,
        original_team_code=original_team_code,
        source_obligation_id=None,
        resolution_kind="resolved_pick_original_team",
        confidence="high",
        reason=reason,
        candidate_pick_ids=[pick.pick_id],
        candidate_original_team_codes=[original_team_code],
    )


def resolve_single_inventory_selection(
    selection: DraftSelectionForPriorOwnerLineage,
    *,
    candidate_rows: list[object],
    all_same_round_rows: list[object],
    team_code: str,
) -> DraftPriorOwnerLineageRow:
    if not candidate_rows:
        return build_unresolved_lineage_row(
            selection,
            status="unmatched",
            reason="pre-draft inventory does not show a controlled Memphis pick-right candidate for this draft year and round",
            candidate_rows=[],
        )
    if len(candidate_rows) > 1:
        return build_unresolved_lineage_row(
            selection,
            status="ambiguous",
            reason="pre-draft inventory shows multiple controlled Memphis pick-right candidates for this draft year and round",
            candidate_rows=candidate_rows,
        )

    candidate = candidate_rows[0]
    original_team_code = normalize_team_code(getattr(candidate, "original_team", None))
    source_obligation_id = getattr(candidate, "source_obligation_id", None)
    if source_obligation_id is None and original_team_code == team_code:
        resolution_kind: PriorOwnerResolutionKind = "team_default_fallback"
        confidence: ResolutionConfidence = "low"
        reason = "pre-draft inventory falls back to Memphis own-pick baseline for this draft year and round"
    elif len(all_same_round_rows) == 1:
        resolution_kind = "inventory_exact_pick"
        confidence = "high"
        reason = "pre-draft inventory projects exactly one controlled pick-right for this draft year and round"
    else:
        resolution_kind = "inventory_single_candidate"
        confidence = "medium"
        reason = "pre-draft inventory leaves one controlled Memphis pick-right candidate after non-controlled rows are excluded"

    return build_resolved_lineage_row(
        selection,
        pick_id=str(getattr(candidate, "pick_id")),
        pick_asset_id=str(getattr(candidate, "asset_id")),
        owner_team_code=team_code,
        original_team_code=original_team_code or team_code,
        source_obligation_id=str(source_obligation_id) if source_obligation_id is not None else None,
        resolution_kind=resolution_kind,
        confidence=confidence,
        reason=reason,
        candidate_pick_ids=[str(getattr(row, "pick_id")) for row in candidate_rows],
        candidate_original_team_codes=[normalize_team_code(getattr(row, "original_team", None)) for row in candidate_rows],
    )


def build_resolved_lineage_row(
    selection: DraftSelectionForPriorOwnerLineage,
    *,
    pick_id: str,
    pick_asset_id: str,
    owner_team_code: str,
    original_team_code: str,
    source_obligation_id: str | None,
    resolution_kind: PriorOwnerResolutionKind,
    confidence: ResolutionConfidence,
    reason: str,
    candidate_pick_ids: list[str],
    candidate_original_team_codes: list[str],
    notes: str | None = None,
) -> DraftPriorOwnerLineageRow:
    return DraftPriorOwnerLineageRow(
        draft_prior_owner_lineage_id=build_draft_prior_owner_lineage_id(selection.draft_selection_id),
        draft_selection_id=selection.draft_selection_id,
        draft_pick_resolution_id=selection.draft_pick_resolution_id,
        pick_id=pick_id,
        pick_asset_id=pick_asset_id,
        player_id=selection.player_id,
        player_asset_id=selection.player_asset_id,
        player_name=selection.player_name,
        draft_year=selection.draft_year,
        round_number=selection.round_number,
        pick_overall=selection.pick_overall,
        team_code=selection.team_code.upper(),
        owner_team_code=owner_team_code.upper(),
        original_team_code=original_team_code.upper(),
        source_obligation_id=source_obligation_id,
        resolution_kind=resolution_kind,
        confidence=confidence,
        status="resolved",
        reason=reason,
        candidate_pick_ids=[pick_id for pick_id in candidate_pick_ids if pick_id],
        candidate_original_team_codes=[code for code in candidate_original_team_codes if code],
        notes=notes or reason,
    )


def build_unresolved_lineage_row(
    selection: DraftSelectionForPriorOwnerLineage,
    *,
    status: PriorOwnerRowStatus,
    reason: str,
    candidate_rows: list[object],
) -> DraftPriorOwnerLineageRow:
    return DraftPriorOwnerLineageRow(
        draft_prior_owner_lineage_id=build_draft_prior_owner_lineage_id(selection.draft_selection_id),
        draft_selection_id=selection.draft_selection_id,
        draft_pick_resolution_id=selection.draft_pick_resolution_id,
        player_id=selection.player_id,
        player_asset_id=selection.player_asset_id,
        player_name=selection.player_name,
        draft_year=selection.draft_year,
        round_number=selection.round_number,
        pick_overall=selection.pick_overall,
        team_code=selection.team_code.upper(),
        status=status,
        reason=reason,
        candidate_pick_ids=[str(getattr(row, "pick_id")) for row in candidate_rows],
        candidate_original_team_codes=[
            normalize_team_code(getattr(row, "original_team", None))
            for row in candidate_rows
            if normalize_team_code(getattr(row, "original_team", None))
        ],
        notes=reason,
    )


def build_draft_prior_owner_lineage_id(draft_selection_id: str) -> str:
    return f"draft-prior-owner-lineage:{draft_selection_id}"


def selection_row_sort_key(row: DraftPriorOwnerLineageRow) -> tuple[int, int, int, str]:
    return (row.draft_year, row.round_number, row.pick_overall, row.draft_selection_id)


def is_slot_pick_id(pick_id: str) -> bool:
    return pick_id.startswith("pick:slot:")


def load_draft_prior_owner_override_fixture(
    path: Path = DEFAULT_DRAFT_PRIOR_OWNER_OVERRIDE_PATH,
) -> DraftPriorOwnerOverrideFixture:
    return DraftPriorOwnerOverrideFixture.model_validate(json.loads(path.read_text(encoding="utf-8")))


def build_prior_owner_pick_id(
    *,
    team_code: str,
    draft_year: int,
    round_number: int,
    original_team_code: str,
) -> str:
    normalized_team_code = team_code.upper()
    normalized_original_team_code = original_team_code.upper()
    if normalized_original_team_code == normalized_team_code:
        return build_own_pick_id(normalized_team_code, draft_year, round_number)
    return (
        f"pick:inventory:{normalized_team_code.lower()}:{draft_year}:"
        f"r{round_number}:{normalized_original_team_code.lower()}"
    )


def normalize_team_code(value: str | None) -> str:
    return value.strip().upper() if value and value.strip() else ""


def load_draft_selections_for_prior_owner_lineage(
    connection: psycopg.Connection,
    *,
    team_code: str,
) -> list[DraftSelectionForPriorOwnerLineage]:
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
                   coalesce(dpr.pick_id, ds.pick_id) as effective_pick_id,
                   dpr.draft_pick_resolution_id,
                   pa.asset_id
            from foundation.draft_selection ds
            left join foundation.draft_pick_resolution dpr
              on dpr.draft_selection_id = ds.draft_selection_id
            left join foundation.player p on p.player_id = ds.player_id
            left join foundation.asset pa on pa.player_id = ds.player_id and pa.asset_kind = 'player'
            where ds.team_code = %s
            order by ds.draft_year, ds.round_number, ds.pick_overall, ds.draft_selection_id
            """,
            (team_code.upper(),),
        )
        return [
            DraftSelectionForPriorOwnerLineage(
                draft_selection_id=str(row[0]),
                draft_year=int(row[1]),
                pick_overall=int(row[2]),
                round_number=int(row[3]),
                team_code=str(row[4]),
                player_id=str(row[5]),
                player_name=str(row[6]) if row[6] is not None else None,
                pick_id=str(row[7]) if row[7] is not None else None,
                draft_pick_resolution_id=str(row[8]) if row[8] is not None else None,
                player_asset_id=str(row[9]) if row[9] is not None else None,
            )
            for row in cursor.fetchall()
        ]


def load_pick_candidates_for_prior_owner_lineage(connection: psycopg.Connection) -> list[PickCandidateForResolution]:
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
            for row in cursor.fetchall()
        ]


def insert_missing_prior_owner_pick_rows(
    connection: psycopg.Connection,
    rows: list[DraftPriorOwnerLineageRow],
) -> tuple[int, int]:
    pick_values: dict[str, tuple[int, int, str, str]] = {}
    asset_values: dict[str, str] = {}
    for row in rows:
        if row.pick_id is None or row.pick_asset_id is None or row.original_team_code is None:
            continue
        pick_values[row.pick_id] = (
            row.draft_year,
            row.round_number,
            row.original_team_code,
            build_prior_owner_pick_raw_text(row),
        )
        asset_values[row.pick_asset_id] = row.pick_id

    picks_inserted = 0
    assets_inserted = 0
    with connection.cursor() as cursor:
        for pick_id, value in pick_values.items():
            cursor.execute(
                """
                insert into foundation.pick (
                    pick_id, draft_year, round_number, original_team, protection_text, swap_text, resolution_status, raw_text
                ) values (%s, %s, %s, %s, null, null, null, %s)
                on conflict (pick_id) do nothing
                """,
                (pick_id, value[0], value[1], value[2], value[3]),
            )
            picks_inserted += cursor.rowcount
        for asset_id, pick_id in asset_values.items():
            cursor.execute(
                """
                insert into foundation.asset (
                    asset_id, asset_kind, player_id, pick_id, start_source_event_id, end_source_event_id
                ) values (%s, 'pick', null, %s, null, null)
                on conflict (asset_id) do nothing
                """,
                (asset_id, pick_id),
            )
            assets_inserted += cursor.rowcount
    return picks_inserted, assets_inserted


def build_prior_owner_pick_raw_text(row: DraftPriorOwnerLineageRow) -> str:
    source_id = row.source_obligation_id or "team-default-fallback"
    return build_inventory_pick_raw_text(
        draft_year=row.draft_year,
        round_number=row.round_number,
        original_team=row.original_team_code or row.team_code,
        source_id=source_id,
    )


def upsert_draft_prior_owner_lineage_rows(
    connection: psycopg.Connection,
    rows: list[DraftPriorOwnerLineageRow],
) -> int:
    written = 0
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.draft_prior_owner_lineage (
                    draft_prior_owner_lineage_id,
                    draft_selection_id,
                    draft_pick_resolution_id,
                    pick_id,
                    pick_asset_id,
                    player_id,
                    player_asset_id,
                    draft_year,
                    round_number,
                    pick_overall,
                    team_code,
                    owner_team_code,
                    original_team_code,
                    source_obligation_id,
                    resolution_kind,
                    confidence,
                    notes,
                    updated_at
                ) values (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()
                )
                on conflict (draft_prior_owner_lineage_id) do update
                set draft_selection_id = excluded.draft_selection_id,
                    draft_pick_resolution_id = excluded.draft_pick_resolution_id,
                    pick_id = excluded.pick_id,
                    pick_asset_id = excluded.pick_asset_id,
                    player_id = excluded.player_id,
                    player_asset_id = excluded.player_asset_id,
                    draft_year = excluded.draft_year,
                    round_number = excluded.round_number,
                    pick_overall = excluded.pick_overall,
                    team_code = excluded.team_code,
                    owner_team_code = excluded.owner_team_code,
                    original_team_code = excluded.original_team_code,
                    source_obligation_id = excluded.source_obligation_id,
                    resolution_kind = excluded.resolution_kind,
                    confidence = excluded.confidence,
                    notes = excluded.notes,
                    updated_at = now()
                """,
                (
                    row.draft_prior_owner_lineage_id,
                    row.draft_selection_id,
                    row.draft_pick_resolution_id,
                    row.pick_id,
                    row.pick_asset_id,
                    row.player_id,
                    row.player_asset_id,
                    row.draft_year,
                    row.round_number,
                    row.pick_overall,
                    row.team_code,
                    row.owner_team_code,
                    row.original_team_code,
                    row.source_obligation_id,
                    row.resolution_kind,
                    row.confidence,
                    row.notes,
                ),
            )
            written += 1
    return written
