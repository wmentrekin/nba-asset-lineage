from __future__ import annotations

import json
from collections import Counter
from datetime import date
from hashlib import sha1
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from foundation.export import draft_resolution_event_date


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
    team_code: str
    draft_year: int
    round_number: int
    original_team: str
    direction: PickInventoryDirection
    holding_status: PickInventoryHoldingStatus
    obligation_type: PickInventoryObligationType
    protection_text: str | None = None
    swap_text: str | None = None
    source_event_id: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    confidence: PickInventoryConfidence = "curated"
    notes: str | None = None


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
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [PickInventoryObligation.model_validate(row) for row in payload]


def preview_pick_inventory_snapshots(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_FUTURE_PICK_OBLIGATION_PATH,
    max_draft_year: int = 2032,
) -> PickInventoryPreviewResult:
    snapshots = fetch_pick_inventory_snapshots(database_url, team_code=team_code)
    existing_snapshot_pick_rows = fetch_existing_snapshot_pick_count(database_url)
    obligations = load_future_pick_obligations(fixture_path)
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
        with connection.cursor() as cursor:
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
        [obligation for obligation in obligations if obligation.team_code.upper() == team_code],
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
        if obligation.original_team.upper() == team_code:
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
        original_team=obligation.original_team.upper(),
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


def build_own_pick_id(team_code: str, draft_year: int, round_number: int) -> str:
    return f"pick:inventory:{team_code.lower()}:{draft_year}:r{round_number}:own"


def build_obligation_pick_id(obligation: PickInventoryObligation) -> str:
    token = sha1(obligation.obligation_id.encode("utf-8")).hexdigest()[:10]
    return (
        f"pick:inventory:{obligation.team_code.lower()}:{obligation.draft_year}:"
        f"r{obligation.round_number}:{obligation.original_team.lower()}:{token}"
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
