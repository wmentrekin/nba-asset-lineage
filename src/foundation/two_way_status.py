from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from foundation.ingest import normalize_player_alias_name


DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH = Path("configs/data/memphis_two_way_status_2017_2026.json")

TwoWayConfidence = Literal["high", "medium", "low"]
IdentityStatus = Literal["matched", "unresolved", "ambiguous", "mismatch"]


class TwoWayStatusSourceSetItem(BaseModel):
    label: str
    locator: str


class TwoWayStatusFixtureRow(BaseModel):
    status_id: str
    player_name: str
    team_code: str
    start_date: date
    end_date: date | None = None
    source_urls: list[str] = Field(default_factory=list)
    confidence: TwoWayConfidence
    loadable: bool
    player_id: str | None = None
    notes: str | None = None


class TwoWayStatusFixture(BaseModel):
    fixture_id: Literal["seed_v1"]
    team_code: str
    coverage_start: date
    coverage_end: date | None = None
    coverage_statement: str
    source_set: list[TwoWayStatusSourceSetItem]
    confidence_rubric: dict[str, list[str]]
    rows: list[TwoWayStatusFixtureRow]


class TwoWayPlayerIdentity(BaseModel):
    player_id: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)


class TwoWaySnapshotPlayer(BaseModel):
    snapshot_id: str
    snapshot_date: date
    team_code: str
    player_id: str


class TwoWayStatusPreviewRow(BaseModel):
    status_id: str
    player_name: str
    team_code: str
    start_date: date
    end_date: date | None
    confidence: TwoWayConfidence
    loadable: bool
    identity_status: IdentityStatus
    ready_for_load: bool
    resolved_player_id: str | None = None
    resolved_display_name: str | None = None
    matched_snapshot_rows: int = 0
    matched_snapshot_ids: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    notes: str | None = None


class TwoWayStatusPreview(BaseModel):
    status: Literal["ok"] = "ok"
    fixture_id: str
    fixture_path: str
    team_code: str
    coverage_start: date
    coverage_end: date | None
    fixture_rows: int
    loadable_rows: int
    ready_rows: int
    blocked_rows: int
    warning_rows: int
    reset_candidate_rows: int
    projected_two_way_rows: int
    rows: list[TwoWayStatusPreviewRow]
    warnings: list[str]
    known_limitations: list[str]


class TwoWayStatusLoadResult(BaseModel):
    status: Literal["ok"] = "ok"
    fixture_id: str
    fixture_path: str
    team_code: str
    dry_run: bool
    blocked_rows: int
    warning_rows: int
    reset_rows: int
    applied_rows: int
    rows: list[TwoWayStatusPreviewRow]
    warnings: list[str]


def load_two_way_status_fixture(path: Path = DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH) -> TwoWayStatusFixture:
    return TwoWayStatusFixture.model_validate(json.loads(path.read_text(encoding="utf-8")))


def validate_two_way_status_fixture(fixture: TwoWayStatusFixture, *, team_code: str) -> list[str]:
    issues: list[str] = []
    if fixture.team_code.upper() != team_code.upper():
        issues.append(f"fixture team_code {fixture.team_code} does not match expected team {team_code.upper()}")
    if fixture.coverage_end is not None and fixture.coverage_end <= fixture.coverage_start:
        issues.append("fixture coverage_end must be after coverage_start")

    seen_status_ids: set[str] = set()
    for row in fixture.rows:
        if row.status_id in seen_status_ids:
            issues.append(f"duplicate status_id in two-way fixture: {row.status_id}")
        seen_status_ids.add(row.status_id)
        if row.team_code.upper() != fixture.team_code.upper():
            issues.append(f"{row.status_id}: row team_code {row.team_code} does not match fixture team {fixture.team_code}")
        if row.start_date < fixture.coverage_start:
            issues.append(f"{row.status_id}: start_date is before fixture coverage_start")
        if fixture.coverage_end is not None and row.start_date >= fixture.coverage_end:
            issues.append(f"{row.status_id}: start_date is outside fixture coverage")
        if row.end_date is not None and row.end_date <= row.start_date:
            issues.append(f"{row.status_id}: end_date must be after start_date")
        if row.loadable and row.confidence != "high":
            issues.append(f"{row.status_id}: only high-confidence rows may be loadable")
        if row.loadable and not row.source_urls:
            issues.append(f"{row.status_id}: loadable rows require at least one source URL")
    return issues


def build_two_way_status_preview(
    *,
    fixture: TwoWayStatusFixture,
    fixture_path: Path,
    team_code: str,
    players: list[TwoWayPlayerIdentity],
    snapshot_players: list[TwoWaySnapshotPlayer],
) -> TwoWayStatusPreview:
    fixture_issues = validate_two_way_status_fixture(fixture, team_code=team_code)
    row_issue_by_status_id: dict[str, list[str]] = {}
    for issue in fixture_issues:
        if ": " in issue:
            status_id, detail = issue.split(": ", 1)
            row_issue_by_status_id.setdefault(status_id, []).append(detail)

    rows = [
        build_two_way_status_preview_row(
            row,
            players=players,
            snapshot_players=snapshot_players,
            expected_team_code=team_code,
            extra_issues=row_issue_by_status_id.get(row.status_id, []),
        )
        for row in fixture.rows
        if row.team_code.upper() == team_code.upper()
    ]
    global_blocking_issues = [issue for issue in fixture_issues if ": " not in issue]
    filtered_blocking_issues = [
        issue
        for status_id, issues in row_issue_by_status_id.items()
        if not any(row.status_id == status_id for row in rows)
        for issue in issues
    ]
    overlap_issues = collect_loadable_interval_overlap_issues(rows)
    global_blocking_issues.extend(filtered_blocking_issues)
    global_blocking_issues.extend(overlap_issues)
    global_warnings = [
        row.warnings[0]
        for row in rows
        if row.ready_for_load and row.warnings
    ]
    for issue in global_blocking_issues:
        global_warnings.append(f"blocking fixture issue: {issue}")

    return TwoWayStatusPreview(
        fixture_id=fixture.fixture_id,
        fixture_path=str(fixture_path),
        team_code=team_code.upper(),
        coverage_start=fixture.coverage_start,
        coverage_end=fixture.coverage_end,
        fixture_rows=len(rows),
        loadable_rows=sum(1 for row in rows if row.loadable and row.confidence == "high"),
        ready_rows=sum(1 for row in rows if row.ready_for_load),
        blocked_rows=sum(1 for row in rows if row.issues) + len(global_blocking_issues),
        warning_rows=sum(1 for row in rows if row.warnings),
        reset_candidate_rows=len(snapshot_players),
        projected_two_way_rows=len(build_unique_snapshot_player_pairs(rows)),
        rows=rows,
        warnings=global_warnings,
        known_limitations=[
            "seed_v1 is a curated high-confidence interval fixture, not complete historical two-way coverage.",
            "The loader never creates players, aliases, roster snapshots, or snapshot-player rows.",
            "Rows without matching snapshot-player records are warnings because roster checkpoints may be capped or absent.",
            "Run this enrichment after load-roster-snapshots-from-baselines because that command rebuilds snapshot-player rows as standard.",
        ],
    )


def collect_loadable_interval_overlap_issues(rows: list[TwoWayStatusPreviewRow]) -> list[str]:
    issues: list[str] = []
    by_player_id: dict[str, list[TwoWayStatusPreviewRow]] = {}
    for row in rows:
        if not row.ready_for_load or row.resolved_player_id is None:
            continue
        by_player_id.setdefault(row.resolved_player_id, []).append(row)

    for player_id, player_rows in by_player_id.items():
        for index, left in enumerate(player_rows):
            for right in player_rows[index + 1:]:
                if intervals_overlap(left.start_date, left.end_date, right.start_date, right.end_date):
                    issues.append(
                        f"overlapping loadable two-way intervals for {player_id}: "
                        f"{left.status_id} and {right.status_id}"
                    )
    return issues


def intervals_overlap(
    left_start: date,
    left_end: date | None,
    right_start: date,
    right_end: date | None,
) -> bool:
    return left_start < (right_end or date.max) and right_start < (left_end or date.max)


def build_unique_snapshot_player_pairs(rows: list[TwoWayStatusPreviewRow]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not row.ready_for_load or row.resolved_player_id is None:
            continue
        for snapshot_id in row.matched_snapshot_ids:
            pair = (snapshot_id, row.resolved_player_id)
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append(pair)
    return pairs


def build_two_way_status_preview_row(
    row: TwoWayStatusFixtureRow,
    *,
    players: list[TwoWayPlayerIdentity],
    snapshot_players: list[TwoWaySnapshotPlayer],
    expected_team_code: str,
    extra_issues: list[str] | None = None,
) -> TwoWayStatusPreviewRow:
    identity_status, resolved_player, identity_issues = resolve_two_way_player_identity(row, players)
    issues = list(extra_issues or []) + identity_issues
    if row.team_code.upper() != expected_team_code.upper():
        issues.append(f"fixture team_code {row.team_code} does not match expected team {expected_team_code.upper()}")
    if row.confidence != "high" and row.loadable:
        issues.append("only high-confidence rows may be loadable")

    matched_snapshot_ids: list[str] = []
    if resolved_player is not None:
        matched_snapshot_ids = [
            snapshot.snapshot_id
            for snapshot in snapshot_players
            if interval_matches_snapshot(row, snapshot)
            and snapshot.team_code.upper() == expected_team_code.upper()
            and snapshot.player_id == resolved_player.player_id
        ]

    warnings: list[str] = []
    if row.loadable and row.confidence == "high" and not issues and not matched_snapshot_ids:
        warnings.append(f"{row.status_id}: no matching snapshot-player rows found for the interval")

    ready_for_load = row.loadable and row.confidence == "high" and not issues
    return TwoWayStatusPreviewRow(
        status_id=row.status_id,
        player_name=row.player_name,
        team_code=row.team_code,
        start_date=row.start_date,
        end_date=row.end_date,
        confidence=row.confidence,
        loadable=row.loadable,
        identity_status=identity_status,
        ready_for_load=ready_for_load,
        resolved_player_id=resolved_player.player_id if resolved_player is not None else None,
        resolved_display_name=resolved_player.display_name if resolved_player is not None else None,
        matched_snapshot_rows=len(matched_snapshot_ids),
        matched_snapshot_ids=matched_snapshot_ids,
        issues=issues,
        warnings=warnings,
        source_urls=row.source_urls,
        notes=row.notes,
    )


def resolve_two_way_player_identity(
    row: TwoWayStatusFixtureRow,
    players: list[TwoWayPlayerIdentity],
) -> tuple[IdentityStatus, TwoWayPlayerIdentity | None, list[str]]:
    by_player_id = {player.player_id: player for player in players}
    ids_by_normalized_name: dict[str, set[str]] = {}
    normalized_names_by_player_id: dict[str, set[str]] = {}
    for player in players:
        names = [player.display_name, *player.aliases]
        normalized_names_by_player_id[player.player_id] = {normalize_two_way_identity_name(name) for name in names}
        for name in names:
            ids_by_normalized_name.setdefault(normalize_two_way_identity_name(name), set()).add(player.player_id)

    normalized_fixture_name = normalize_two_way_identity_name(row.player_name)
    if row.player_id:
        player = by_player_id.get(row.player_id)
        if player is None:
            return "unresolved", None, [f"player_id {row.player_id} is missing from foundation.player"]
        if normalized_fixture_name not in normalized_names_by_player_id.get(row.player_id, set()):
            return (
                "mismatch",
                player,
                [f"fixture player_name {row.player_name} does not match player_id {row.player_id} ({player.display_name})"],
            )
        name_matches = ids_by_normalized_name.get(normalized_fixture_name, set())
        if name_matches and row.player_id not in name_matches:
            return "mismatch", player, [f"fixture player_name {row.player_name} resolves to a different player_id"]
        return "matched", player, []

    matches = ids_by_normalized_name.get(normalized_fixture_name, set())
    if not matches:
        return "unresolved", None, [f"player_name {row.player_name} did not resolve to a foundation.player or player_alias row"]
    if len(matches) > 1:
        return "ambiguous", None, [f"player_name {row.player_name} resolves to multiple player_ids: {sorted(matches)}"]
    player_id = next(iter(matches))
    return "matched", by_player_id[player_id], []


def normalize_two_way_identity_name(value: str) -> str:
    without_contract_suffix = re.sub(r"\s*\((tw|two-way|two way)\)\s*$", "", value, flags=re.IGNORECASE)
    return normalize_player_alias_name(without_contract_suffix)


def interval_matches_snapshot(row: TwoWayStatusFixtureRow, snapshot: TwoWaySnapshotPlayer) -> bool:
    return (
        snapshot.snapshot_date >= row.start_date
        and (row.end_date is None or snapshot.snapshot_date < row.end_date)
    )


def preview_two_way_status(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
) -> TwoWayStatusPreview:
    fixture = load_two_way_status_fixture(fixture_path)
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        players = load_two_way_player_identities(connection)
        snapshot_players = load_two_way_snapshot_players(
            connection,
            team_code=team_code,
            coverage_start=fixture.coverage_start,
            coverage_end=fixture.coverage_end,
        )
    return build_two_way_status_preview(
        fixture=fixture,
        fixture_path=fixture_path,
        team_code=team_code,
        players=players,
        snapshot_players=snapshot_players,
    )


def load_two_way_status(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path = DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
    dry_run: bool = False,
) -> TwoWayStatusLoadResult:
    preview = preview_two_way_status(database_url, team_code=team_code, fixture_path=fixture_path)
    if preview.blocked_rows:
        return TwoWayStatusLoadResult(
            fixture_id=preview.fixture_id,
            fixture_path=preview.fixture_path,
            team_code=preview.team_code,
            dry_run=dry_run,
            blocked_rows=preview.blocked_rows,
            warning_rows=preview.warning_rows,
            reset_rows=0,
            applied_rows=0,
            rows=preview.rows,
            warnings=preview.warnings,
        )
    if dry_run:
        return TwoWayStatusLoadResult(
            fixture_id=preview.fixture_id,
            fixture_path=preview.fixture_path,
            team_code=preview.team_code,
            dry_run=True,
            blocked_rows=0,
            warning_rows=preview.warning_rows,
            reset_rows=preview.reset_candidate_rows,
            applied_rows=preview.projected_two_way_rows,
            rows=preview.rows,
            warnings=preview.warnings,
        )

    fixture = load_two_way_status_fixture(fixture_path)
    pairs_to_apply = build_unique_snapshot_player_pairs(preview.rows)
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        reset_rows = reset_two_way_snapshot_players(
            connection,
            team_code=team_code,
            coverage_start=fixture.coverage_start,
            coverage_end=fixture.coverage_end,
        )
        applied_rows = apply_two_way_snapshot_players(connection, pairs_to_apply)
        connection.commit()

    return TwoWayStatusLoadResult(
        fixture_id=preview.fixture_id,
        fixture_path=preview.fixture_path,
        team_code=preview.team_code,
        dry_run=False,
        blocked_rows=0,
        warning_rows=preview.warning_rows,
        reset_rows=reset_rows,
        applied_rows=applied_rows,
        rows=preview.rows,
        warnings=preview.warnings,
    )


def load_two_way_player_identities(connection: psycopg.Connection) -> list[TwoWayPlayerIdentity]:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('foundation.player')")
        if cursor.fetchone()[0] is None:
            return []
        cursor.execute("select player_id, display_name from foundation.player order by player_id")
        players = {
            str(player_id): TwoWayPlayerIdentity(player_id=str(player_id), display_name=str(display_name))
            for player_id, display_name in cursor.fetchall()
        }
        cursor.execute("select to_regclass('foundation.player_alias')")
        if cursor.fetchone()[0] is not None:
            cursor.execute("select player_id, alias_name from foundation.player_alias order by player_id, alias_name")
            for player_id, alias_name in cursor.fetchall():
                player = players.get(str(player_id))
                if player is not None:
                    player.aliases.append(str(alias_name))
    return list(players.values())


def load_two_way_snapshot_players(
    connection: psycopg.Connection,
    *,
    team_code: str,
    coverage_start: date,
    coverage_end: date | None,
) -> list[TwoWaySnapshotPlayer]:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('foundation.roster_snapshot_player')")
        if cursor.fetchone()[0] is None:
            return []
        if coverage_end is None:
            cursor.execute(
                """
                select rs.snapshot_id, rs.snapshot_date::text, rs.team_code, rsp.player_id
                from foundation.roster_snapshot_player rsp
                join foundation.roster_snapshot rs on rs.snapshot_id = rsp.snapshot_id
                where upper(rs.team_code) = upper(%s)
                  and rs.snapshot_date >= %s
                order by rs.snapshot_date, rs.snapshot_id, rsp.player_id
                """,
                (team_code, coverage_start),
            )
        else:
            cursor.execute(
                """
                select rs.snapshot_id, rs.snapshot_date::text, rs.team_code, rsp.player_id
                from foundation.roster_snapshot_player rsp
                join foundation.roster_snapshot rs on rs.snapshot_id = rsp.snapshot_id
                where upper(rs.team_code) = upper(%s)
                  and rs.snapshot_date >= %s
                  and rs.snapshot_date < %s
                order by rs.snapshot_date, rs.snapshot_id, rsp.player_id
                """,
                (team_code, coverage_start, coverage_end),
            )
        return [
            TwoWaySnapshotPlayer(
                snapshot_id=str(row[0]),
                snapshot_date=date.fromisoformat(str(row[1])),
                team_code=str(row[2]),
                player_id=str(row[3]),
            )
            for row in cursor.fetchall()
        ]


def reset_two_way_snapshot_players(
    connection: psycopg.Connection,
    *,
    team_code: str,
    coverage_start: date,
    coverage_end: date | None,
) -> int:
    with connection.cursor() as cursor:
        if coverage_end is None:
            cursor.execute(
                """
                update foundation.roster_snapshot_player rsp
                set roster_status = 'standard',
                    is_two_way = false,
                    is_standard_contract = true
                from foundation.roster_snapshot rs
                where rs.snapshot_id = rsp.snapshot_id
                  and upper(rs.team_code) = upper(%s)
                  and rs.snapshot_date >= %s
                """,
                (team_code, coverage_start),
            )
        else:
            cursor.execute(
                """
                update foundation.roster_snapshot_player rsp
                set roster_status = 'standard',
                    is_two_way = false,
                    is_standard_contract = true
                from foundation.roster_snapshot rs
                where rs.snapshot_id = rsp.snapshot_id
                  and upper(rs.team_code) = upper(%s)
                  and rs.snapshot_date >= %s
                  and rs.snapshot_date < %s
                """,
                (team_code, coverage_start, coverage_end),
            )
        return int(cursor.rowcount)


def apply_two_way_snapshot_players(connection: psycopg.Connection, snapshot_player_pairs: list[tuple[str, str]]) -> int:
    applied_rows = 0
    with connection.cursor() as cursor:
        for snapshot_id, player_id in snapshot_player_pairs:
            cursor.execute(
                """
                update foundation.roster_snapshot_player
                set roster_status = 'two_way',
                    is_two_way = true,
                    is_standard_contract = false
                where snapshot_id = %s
                  and player_id = %s
                """,
                (snapshot_id, player_id),
            )
            applied_rows += int(cursor.rowcount)
    return applied_rows
