from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import re
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from foundation.ingest import (
    MAX_ROSTER_SNAPSHOT_PLAYERS,
    PlayerAliasRow,
    PlayerRow,
    RosterBaselinePlayerRow,
    SourceEventRow,
    build_player_asset_id_from_player_id,
    build_player_alias_lookup,
    build_players_from_source_events,
    filter_canonical_source_events,
    load_player_aliases_from_database,
    load_roster_baseline_players_from_database,
    load_source_events_from_database,
    normalize_player_alias_name,
    parse_season_years,
    resolve_player_id,
    roster_membership_change_names,
    slugify,
)
from foundation.two_way_status import (
    DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
    TwoWayPlayerIdentity,
    TwoWayStatusFixture,
    TwoWayStatusFixtureRow,
    intervals_overlap,
    load_two_way_status_fixture,
    resolve_two_way_player_identity,
    validate_two_way_status_fixture,
)


class DailyRosterStateRow(BaseModel):
    roster_state_id: str
    state_date: date
    season: str
    team_code: str
    source_record_id: str | None = None
    event_count: int = 0
    source_event_ids: list[str] = Field(default_factory=list)
    player_count: int
    standard_count: int
    two_way_count: int
    notes: str | None = None


class DailyRosterStatePlayerRow(BaseModel):
    roster_state_id: str
    state_date: date
    season: str
    team_code: str
    player_id: str
    display_name: str
    asset_id: str
    roster_status: Literal["standard", "two_way"] = "standard"
    roster_order: int | None = None
    is_two_way: bool = False
    is_standard_contract: bool = True


class DailyRosterStatePreviewResult(BaseModel):
    status: Literal["ok"] = "ok"
    team_code: str
    fixture_path: str | None = None
    season_count: int
    coverage_start: date | None = None
    coverage_end: date | None = None
    state_row_count: int
    player_row_count: int
    blocked_rows: int
    warning_rows: int
    rows: list[DailyRosterStateRow]
    player_rows: list[DailyRosterStatePlayerRow]
    warnings: list[str]
    known_limitations: list[str]


class DailyRosterStateLoadResult(BaseModel):
    status: Literal["ok"] = "ok"
    team_code: str
    fixture_path: str | None = None
    dry_run: bool
    blocked_rows: int
    warning_rows: int
    reset_state_rows: int
    reset_player_rows: int
    applied_state_rows: int
    applied_player_rows: int
    rows: list[DailyRosterStateRow]
    player_rows: list[DailyRosterStatePlayerRow]
    warnings: list[str]


class _ResolvedTwoWayInterval(BaseModel):
    status_id: str
    player_id: str
    start_date: date
    end_date: date | None = None


class _RosterMembershipChange(BaseModel):
    event_date: date
    source_event_id: str
    player_id: str
    display_name: str
    effect: Literal["in", "out"]


class _RosterSnapshotAnchorPlayer(BaseModel):
    player_id: str
    display_name: str
    depth_order: int | None = None


class _RosterSnapshotAnchor(BaseModel):
    snapshot_id: str
    snapshot_date: date
    snapshot_kind: str
    season: str
    team_code: str
    source_record_id: str | None = None
    players: list[_RosterSnapshotAnchorPlayer] = Field(default_factory=list)


def build_daily_roster_state_rows(
    baseline_players: list[RosterBaselinePlayerRow],
    *,
    source_events: list[SourceEventRow] | None = None,
    player_aliases: list[PlayerAliasRow] | None = None,
    snapshot_anchors: list[_RosterSnapshotAnchor] | None = None,
    team_code: str = "MEM",
    two_way_fixture: TwoWayStatusFixture | None = None,
    fixture_path: Path | None = DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
) -> tuple[list[DailyRosterStateRow], list[DailyRosterStatePlayerRow]]:
    preview = build_daily_roster_state_preview(
        baseline_players,
        source_events=source_events or [],
        player_aliases=player_aliases or [],
        snapshot_anchors=snapshot_anchors or [],
        team_code=team_code,
        two_way_fixture=two_way_fixture,
        fixture_path=fixture_path,
    )
    return preview.rows, preview.player_rows


def build_daily_roster_state_rows_from_database(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path | None = DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
) -> tuple[list[DailyRosterStateRow], list[DailyRosterStatePlayerRow]]:
    preview = preview_daily_roster_state(
        database_url,
        team_code=team_code,
        fixture_path=fixture_path,
    )
    return preview.rows, preview.player_rows


def build_daily_roster_state_preview(
    baseline_players: list[RosterBaselinePlayerRow],
    *,
    source_events: list[SourceEventRow],
    player_aliases: list[PlayerAliasRow],
    snapshot_anchors: list[_RosterSnapshotAnchor] | None = None,
    team_code: str = "MEM",
    two_way_fixture: TwoWayStatusFixture | None = None,
    fixture_path: Path | None = DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
) -> DailyRosterStatePreviewResult:
    filtered_baselines = [
        row
        for row in baseline_players
        if row.team_code.upper() == team_code.upper()
    ]
    warnings: list[str] = []
    blocking_issues: list[str] = []
    if not filtered_baselines:
        blocking_issues.append(f"no roster baseline players found for team {team_code.upper()}")

    derived_players = build_players_from_source_events(
        filter_canonical_source_events(source_events),
        baseline_players=filtered_baselines,
        player_aliases=player_aliases,
    )
    identities = build_two_way_player_identities(derived_players, player_aliases)
    two_way_intervals, two_way_issues = resolve_two_way_intervals(
        team_code=team_code,
        fixture=two_way_fixture,
        fixture_path=fixture_path,
        players=identities,
    )
    warnings.extend(two_way_issues)

    filtered_snapshot_anchors = [
        anchor
        for anchor in (snapshot_anchors or [])
        if anchor.team_code.upper() == team_code.upper()
    ]
    if filtered_snapshot_anchors:
        rows, player_rows = _build_daily_roster_state_rows_from_snapshot_anchors(
            filtered_baselines,
            source_events=source_events,
            player_aliases=player_aliases,
            snapshot_anchors=filtered_snapshot_anchors,
            team_code=team_code,
            two_way_intervals=two_way_intervals,
        )
    else:
        rows, player_rows = _build_daily_roster_state_rows_internal(
            filtered_baselines,
            source_events=source_events,
            player_aliases=player_aliases,
            team_code=team_code,
            two_way_intervals=two_way_intervals,
        )
    coverage_start = rows[0].state_date if rows else None
    coverage_end = rows[-1].state_date if rows else None

    for issue in blocking_issues:
        warnings.append(f"blocking issue: {issue}")

    return DailyRosterStatePreviewResult(
        team_code=team_code.upper(),
        fixture_path=str(fixture_path) if fixture_path is not None else None,
        season_count=len({row.season for row in rows}),
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        state_row_count=len(rows),
        player_row_count=len(player_rows),
        blocked_rows=len(blocking_issues),
        warning_rows=len(warnings),
        rows=rows,
        player_rows=player_rows,
        warnings=warnings,
        known_limitations=[
            "Daily roster truth is snapshot-anchored end-of-day occupancy after loaded same-day events; quiet days carry forward between checkpoints.",
            "Two-way status is additive contract labeling only and depends on the curated interval fixture when supplied.",
            f"Daily output is bounded to the graph-facing {MAX_ROSTER_SNAPSHOT_PLAYERS}-player slot surface when interval residue would otherwise exceed roster capacity.",
            "This module derives rows from baseline players plus canonical source events and does not infer missing off-ledger transactions.",
        ],
    )


def preview_daily_roster_state(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path | None = DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
) -> DailyRosterStatePreviewResult:
    baseline_players = load_roster_baseline_players_from_database(database_url)
    source_events = load_source_events_from_database(database_url)
    player_aliases = load_player_aliases_from_database(database_url)
    snapshot_anchors = load_roster_snapshot_anchors_from_database(database_url, team_code=team_code)
    fixture = load_two_way_status_fixture(fixture_path) if fixture_path is not None else None
    return build_daily_roster_state_preview(
        baseline_players,
        source_events=source_events,
        player_aliases=player_aliases,
        snapshot_anchors=snapshot_anchors,
        team_code=team_code,
        two_way_fixture=fixture,
        fixture_path=fixture_path,
    )


def load_daily_roster_state(
    database_url: str,
    *,
    team_code: str = "MEM",
    fixture_path: Path | None = DEFAULT_TWO_WAY_STATUS_FIXTURE_PATH,
    state_table: str = "foundation.daily_roster_state",
    player_table: str = "foundation.daily_roster_state_player",
    dry_run: bool = False,
) -> DailyRosterStateLoadResult:
    preview = preview_daily_roster_state(
        database_url,
        team_code=team_code,
        fixture_path=fixture_path,
    )
    if preview.blocked_rows:
        return DailyRosterStateLoadResult(
            team_code=preview.team_code,
            fixture_path=preview.fixture_path,
            dry_run=dry_run,
            blocked_rows=preview.blocked_rows,
            warning_rows=preview.warning_rows,
            reset_state_rows=0,
            reset_player_rows=0,
            applied_state_rows=0,
            applied_player_rows=0,
            rows=preview.rows,
            player_rows=preview.player_rows,
            warnings=preview.warnings,
        )
    if dry_run:
        return DailyRosterStateLoadResult(
            team_code=preview.team_code,
            fixture_path=preview.fixture_path,
            dry_run=True,
            blocked_rows=0,
            warning_rows=preview.warning_rows,
            reset_state_rows=len(preview.rows),
            reset_player_rows=len(preview.player_rows),
            applied_state_rows=len(preview.rows),
            applied_player_rows=len(preview.player_rows),
            rows=preview.rows,
            player_rows=preview.player_rows,
            warnings=preview.warnings,
        )

    validated_state_table = _validated_table_name(state_table)
    validated_player_table = _validated_table_name(player_table)
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        missing_tables = [
            table_name
            for table_name in (validated_state_table, validated_player_table)
            if not _table_exists(connection, table_name)
        ]
        if missing_tables:
            warnings = list(preview.warnings)
            for table_name in missing_tables:
                warnings.append(f"blocking issue: target table {table_name} does not exist")
            return DailyRosterStateLoadResult(
                team_code=preview.team_code,
                fixture_path=preview.fixture_path,
                dry_run=False,
                blocked_rows=len(missing_tables),
                warning_rows=len(warnings),
                reset_state_rows=0,
                reset_player_rows=0,
                applied_state_rows=0,
                applied_player_rows=0,
                rows=preview.rows,
                player_rows=preview.player_rows,
                warnings=warnings,
            )

        roster_state_ids = [row.roster_state_id for row in preview.rows]
        reset_player_rows = _delete_daily_roster_state_player_rows(connection, validated_player_table, roster_state_ids)
        reset_state_rows = _delete_daily_roster_state_rows(connection, validated_state_table, roster_state_ids)
        applied_state_rows = _insert_daily_roster_state_rows(connection, validated_state_table, preview.rows)
        applied_player_rows = _insert_daily_roster_state_player_rows(connection, validated_player_table, preview.player_rows)
        connection.commit()

    return DailyRosterStateLoadResult(
        team_code=preview.team_code,
        fixture_path=preview.fixture_path,
        dry_run=False,
        blocked_rows=0,
        warning_rows=preview.warning_rows,
        reset_state_rows=reset_state_rows,
        reset_player_rows=reset_player_rows,
        applied_state_rows=applied_state_rows,
        applied_player_rows=applied_player_rows,
        rows=preview.rows,
        player_rows=preview.player_rows,
        warnings=preview.warnings,
    )


def build_two_way_player_identities(
    players: list[PlayerRow],
    aliases: list[PlayerAliasRow],
) -> list[TwoWayPlayerIdentity]:
    by_player_id = {
        player.player_id: TwoWayPlayerIdentity(player_id=player.player_id, display_name=player.display_name)
        for player in players
    }
    for alias in aliases:
        player = by_player_id.get(alias.player_id)
        if player is None:
            continue
        if alias.alias_name not in player.aliases:
            player.aliases.append(alias.alias_name)
    return list(by_player_id.values())


def resolve_two_way_intervals(
    *,
    team_code: str,
    fixture: TwoWayStatusFixture | None,
    fixture_path: Path | None,
    players: list[TwoWayPlayerIdentity],
) -> tuple[list[_ResolvedTwoWayInterval], list[str]]:
    if fixture is None or fixture_path is None:
        return [], []

    issues = validate_two_way_status_fixture(fixture, team_code=team_code)
    resolved_intervals: list[_ResolvedTwoWayInterval] = []
    ready_rows: list[TwoWayStatusFixtureRow] = []
    ready_player_ids: dict[str, str] = {}

    for row in fixture.rows:
        if row.team_code.upper() != team_code.upper():
            continue
        identity_status, resolved_player, row_issues = resolve_two_way_player_identity(row, players)
        del identity_status
        row_issue_list = list(row_issues)
        if row.confidence != "high" and row.loadable:
            row_issue_list.append("only high-confidence rows may be loadable")
        if not row.loadable:
            continue
        if row_issue_list or resolved_player is None:
            issues.extend(f"{row.status_id}: {issue}" for issue in row_issue_list)
            continue
        ready_rows.append(row)
        ready_player_ids[row.status_id] = resolved_player.player_id
        resolved_intervals.append(
            _ResolvedTwoWayInterval(
                status_id=row.status_id,
                player_id=resolved_player.player_id,
                start_date=row.start_date,
                end_date=row.end_date,
            )
        )

    for index, left in enumerate(ready_rows):
        for right in ready_rows[index + 1:]:
            left_player_id = ready_player_ids[left.status_id]
            right_player_id = ready_player_ids[right.status_id]
            if left_player_id != right_player_id:
                continue
            if intervals_overlap(left.start_date, left.end_date, right.start_date, right.end_date):
                issues.append(
                    "overlapping loadable two-way intervals for "
                    f"{left_player_id}: {left.status_id} and {right.status_id}"
                )
    return resolved_intervals, issues


def load_roster_snapshot_anchors_from_database(
    database_url: str,
    *,
    team_code: str = "MEM",
) -> list[_RosterSnapshotAnchor]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        if not _table_exists(connection, "foundation.roster_snapshot") or not _table_exists(
            connection,
            "foundation.roster_snapshot_player",
        ):
            return []
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select rs.snapshot_id,
                       rs.snapshot_date::text,
                       rs.snapshot_kind,
                       rs.season,
                       rs.team_code,
                       rs.source_record_id,
                       rsp.player_id,
                       coalesce(p.display_name, rb.display_name, rsp.player_id) as display_name,
                       rsp.depth_order
                from foundation.roster_snapshot rs
                join foundation.roster_snapshot_player rsp
                  on rsp.snapshot_id = rs.snapshot_id
                left join foundation.player p
                  on p.player_id = rsp.player_id
                left join lateral (
                    select baseline.display_name
                    from foundation.roster_baseline_player baseline
                    where baseline.player_id = rsp.player_id
                      and baseline.team_code = rs.team_code
                    order by (baseline.season = rs.season) desc, baseline.season desc
                    limit 1
                ) rb on true
                where rs.team_code = %s
                order by rs.snapshot_date, rs.snapshot_id, coalesce(rsp.depth_order, 999), coalesce(p.display_name, rb.display_name, rsp.player_id)
                """,
                (team_code.upper(),),
            )
            rows = cursor.fetchall()

    anchors_by_id: dict[str, _RosterSnapshotAnchor] = {}
    ordered_snapshot_ids: list[str] = []
    for row in rows:
        snapshot_id = str(row[0])
        anchor = anchors_by_id.get(snapshot_id)
        if anchor is None:
            anchor = _RosterSnapshotAnchor(
                snapshot_id=snapshot_id,
                snapshot_date=date.fromisoformat(str(row[1])),
                snapshot_kind=str(row[2]),
                season=str(row[3]),
                team_code=str(row[4]).upper(),
                source_record_id=str(row[5]) if row[5] is not None else None,
            )
            anchors_by_id[snapshot_id] = anchor
            ordered_snapshot_ids.append(snapshot_id)
        anchor.players.append(
            _RosterSnapshotAnchorPlayer(
                player_id=str(row[6]),
                display_name=str(row[7]),
                depth_order=int(row[8]) if row[8] is not None else None,
            )
        )

    return [anchors_by_id[snapshot_id] for snapshot_id in ordered_snapshot_ids]


def _build_daily_roster_state_rows_internal(
    baseline_players: list[RosterBaselinePlayerRow],
    *,
    source_events: list[SourceEventRow],
    player_aliases: list[PlayerAliasRow],
    team_code: str,
    two_way_intervals: list[_ResolvedTwoWayInterval],
) -> tuple[list[DailyRosterStateRow], list[DailyRosterStatePlayerRow]]:
    if not baseline_players:
        return [], []

    grouped: dict[tuple[str, str, str], list[RosterBaselinePlayerRow]] = {}
    for row in baseline_players:
        grouped.setdefault((row.season, row.team_code, row.source_record_id), []).append(row)

    canonical_source_events = filter_canonical_source_events(source_events)
    rows: list[DailyRosterStateRow] = []
    player_rows: list[DailyRosterStatePlayerRow] = []
    intervals_by_player_id: dict[str, list[_ResolvedTwoWayInterval]] = defaultdict(list)
    for interval in two_way_intervals:
        intervals_by_player_id[interval.player_id].append(interval)

    for (season, group_team_code, source_record_id), season_baselines in sorted(grouped.items()):
        if group_team_code.upper() != team_code.upper():
            continue
        start_year, end_year = parse_season_years(season)
        season_start = date(start_year, 7, 1)
        season_end = date(end_year, 6, 30)
        season_events = [
            source_event
            for source_event in canonical_source_events
            if season_start.isoformat() <= source_event.event_date <= season_end.isoformat()
        ]
        membership_changes = build_daily_roster_membership_changes(
            season_events,
            baseline_players=season_baselines,
            player_aliases=player_aliases,
        )
        rows_for_season, player_rows_for_season = build_daily_roster_state_for_season(
            season=season,
            team_code=group_team_code,
            source_record_id=source_record_id,
            baseline_players=season_baselines,
            membership_changes=membership_changes,
            season_start=season_start,
            season_end=season_end,
            two_way_intervals_by_player_id=intervals_by_player_id,
        )
        rows.extend(rows_for_season)
        player_rows.extend(player_rows_for_season)

    return rows, player_rows


def _build_daily_roster_state_rows_from_snapshot_anchors(
    baseline_players: list[RosterBaselinePlayerRow],
    *,
    source_events: list[SourceEventRow],
    player_aliases: list[PlayerAliasRow],
    snapshot_anchors: list[_RosterSnapshotAnchor],
    team_code: str,
    two_way_intervals: list[_ResolvedTwoWayInterval],
) -> tuple[list[DailyRosterStateRow], list[DailyRosterStatePlayerRow]]:
    if not snapshot_anchors:
        return [], []

    baseline_rows_by_season: dict[str, list[RosterBaselinePlayerRow]] = defaultdict(list)
    for row in baseline_players:
        baseline_rows_by_season[row.season].append(row)

    canonical_source_events = filter_canonical_source_events(source_events)
    intervals_by_player_id: dict[str, list[_ResolvedTwoWayInterval]] = defaultdict(list)
    for interval in two_way_intervals:
        intervals_by_player_id[interval.player_id].append(interval)

    grouped_anchors: dict[tuple[str, str], list[_RosterSnapshotAnchor]] = defaultdict(list)
    for anchor in snapshot_anchors:
        grouped_anchors[(anchor.season, anchor.team_code.upper())].append(anchor)

    rows: list[DailyRosterStateRow] = []
    player_rows: list[DailyRosterStatePlayerRow] = []
    for (season, group_team_code), anchors in sorted(grouped_anchors.items()):
        if group_team_code.upper() != team_code.upper():
            continue
        start_year, end_year = parse_season_years(season)
        season_start = date(start_year, 7, 1)
        season_end = date(end_year, 6, 30)
        season_baselines = baseline_rows_by_season.get(season, [])
        season_events = [
            source_event
            for source_event in canonical_source_events
            if season_start.isoformat() <= source_event.event_date <= season_end.isoformat()
        ]
        membership_changes = build_daily_roster_membership_changes(
            season_events,
            baseline_players=season_baselines,
            player_aliases=player_aliases,
        )
        season_rows, season_player_rows = build_daily_roster_state_for_season_from_snapshot_anchors(
            season=season,
            team_code=group_team_code,
            season_start=season_start,
            season_end=season_end,
            baseline_players=season_baselines,
            membership_changes=membership_changes,
            snapshot_anchors=sorted(anchors, key=lambda item: (item.snapshot_date, item.snapshot_id)),
            two_way_intervals_by_player_id=intervals_by_player_id,
        )
        rows.extend(season_rows)
        player_rows.extend(season_player_rows)

    return rows, player_rows


def build_daily_roster_membership_changes(
    source_events: list[SourceEventRow],
    *,
    baseline_players: list[RosterBaselinePlayerRow],
    player_aliases: list[PlayerAliasRow],
) -> list[_RosterMembershipChange]:
    player_id_by_display_key = {
        normalize_player_alias_name(player.display_name): player.player_id
        for player in baseline_players
    }
    alias_lookup = build_player_alias_lookup(player_aliases, player_id_by_display_key)
    changes: list[_RosterMembershipChange] = []

    for source_event in sorted(source_events, key=lambda item: (item.event_date, item.source_event_id)):
        inbound_names, outbound_names = roster_membership_change_names(source_event)
        event_date = date.fromisoformat(source_event.event_date)
        for player_name in inbound_names:
            player_id = (
                resolve_player_id(player_name, player_id_by_display_key, alias_lookup)
                or player_id_by_display_key.get(normalize_player_alias_name(player_name))
                or f"player:{slugify(player_name)}"
            )
            changes.append(
                _RosterMembershipChange(
                    event_date=event_date,
                    source_event_id=source_event.source_event_id,
                    player_id=player_id,
                    display_name=player_name,
                    effect="in",
                )
            )
        for player_name in outbound_names:
            player_id = (
                resolve_player_id(player_name, player_id_by_display_key, alias_lookup)
                or player_id_by_display_key.get(normalize_player_alias_name(player_name))
                or f"player:{slugify(player_name)}"
            )
            changes.append(
                _RosterMembershipChange(
                    event_date=event_date,
                    source_event_id=source_event.source_event_id,
                    player_id=player_id,
                    display_name=player_name,
                    effect="out",
                )
            )
    return changes


def build_daily_roster_state_for_season(
    *,
    season: str,
    team_code: str,
    source_record_id: str,
    baseline_players: list[RosterBaselinePlayerRow],
    membership_changes: list[_RosterMembershipChange],
    season_start: date,
    season_end: date,
    two_way_intervals_by_player_id: dict[str, list[_ResolvedTwoWayInterval]],
) -> tuple[list[DailyRosterStateRow], list[DailyRosterStatePlayerRow]]:
    baseline_by_player_id = {player.player_id: player for player in baseline_players}
    order_by_player_id = {player.player_id: player.roster_order for player in baseline_players}
    display_name_by_player_id = {player.player_id: player.display_name for player in baseline_players}
    derived_order_start = max(order_by_player_id.values(), default=0) + 1000
    derived_order_by_player_id: dict[str, int] = {}

    changes_by_date: dict[date, list[_RosterMembershipChange]] = defaultdict(list)
    history_by_player_id: dict[str, list[_RosterMembershipChange]] = defaultdict(list)
    for change in membership_changes:
        changes_by_date[change.event_date].append(change)
        history_by_player_id[change.player_id].append(change)
        display_name_by_player_id.setdefault(change.player_id, change.display_name)
        if change.player_id not in order_by_player_id and change.player_id not in derived_order_by_player_id:
            derived_order_by_player_id[change.player_id] = derived_order_start + len(derived_order_by_player_id)

    active_by_player_id: dict[str, bool] = {}
    all_player_ids = set(baseline_by_player_id) | set(history_by_player_id)
    for player_id in all_player_ids:
        history = sorted(history_by_player_id.get(player_id, []), key=lambda item: (item.event_date, item.source_event_id))
        if player_id in baseline_by_player_id:
            active_by_player_id[player_id] = not (history and history[0].effect == "in")
        else:
            active_by_player_id[player_id] = False

    rows: list[DailyRosterStateRow] = []
    player_rows: list[DailyRosterStatePlayerRow] = []
    current_date = season_start
    while current_date <= season_end:
        day_changes = sorted(changes_by_date.get(current_date, []), key=lambda item: item.source_event_id)
        day_source_event_ids = list(dict.fromkeys(change.source_event_id for change in day_changes))
        for change in day_changes:
            active_by_player_id[change.player_id] = change.effect == "in"
            display_name_by_player_id[change.player_id] = change.display_name

        active_player_ids = [player_id for player_id, is_active in active_by_player_id.items() if is_active]
        sorted_player_ids = sorted(
            active_player_ids,
            key=lambda player_id: (
                order_by_player_id.get(player_id, derived_order_by_player_id.get(player_id, 999999)),
                display_name_by_player_id.get(player_id, player_id),
                player_id,
            ),
        )[:MAX_ROSTER_SNAPSHOT_PLAYERS]

        roster_state_id = build_daily_roster_state_id(
            team_code=team_code,
            season=season,
            state_date=current_date,
            source_record_id=source_record_id,
        )
        standard_count = 0
        two_way_count = 0
        for player_id in sorted_player_ids:
            is_two_way = any(
                interval.start_date <= current_date and (interval.end_date is None or current_date < interval.end_date)
                for interval in two_way_intervals_by_player_id.get(player_id, [])
            )
            if is_two_way:
                two_way_count += 1
            else:
                standard_count += 1
            player_rows.append(
                DailyRosterStatePlayerRow(
                    roster_state_id=roster_state_id,
                    state_date=current_date,
                    season=season,
                    team_code=team_code,
                    player_id=player_id,
                    display_name=display_name_by_player_id[player_id],
                    asset_id=build_player_asset_id_from_player_id(player_id),
                    roster_status="two_way" if is_two_way else "standard",
                    roster_order=order_by_player_id.get(player_id, derived_order_by_player_id.get(player_id)),
                    is_two_way=is_two_way,
                    is_standard_contract=not is_two_way,
                )
            )

        rows.append(
            DailyRosterStateRow(
                roster_state_id=roster_state_id,
                state_date=current_date,
                season=season,
                team_code=team_code,
                source_record_id=source_record_id,
                event_count=len(day_source_event_ids),
                source_event_ids=day_source_event_ids,
                player_count=len(sorted_player_ids),
                standard_count=standard_count,
                two_way_count=two_way_count,
                notes="End-of-day Memphis roster occupancy after loaded same-day events; quiet days carry forward.",
            )
        )
        current_date += timedelta(days=1)

    return rows, player_rows


def build_daily_roster_state_for_season_from_snapshot_anchors(
    *,
    season: str,
    team_code: str,
    season_start: date,
    season_end: date,
    baseline_players: list[RosterBaselinePlayerRow],
    membership_changes: list[_RosterMembershipChange],
    snapshot_anchors: list[_RosterSnapshotAnchor],
    two_way_intervals_by_player_id: dict[str, list[_ResolvedTwoWayInterval]],
) -> tuple[list[DailyRosterStateRow], list[DailyRosterStatePlayerRow]]:
    if not snapshot_anchors:
        return [], []

    display_name_by_player_id = {player.player_id: player.display_name for player in baseline_players}
    changes_by_date: dict[date, list[_RosterMembershipChange]] = defaultdict(list)
    for change in membership_changes:
        changes_by_date[change.event_date].append(change)
        display_name_by_player_id.setdefault(change.player_id, change.display_name)

    for anchor in snapshot_anchors:
        for player in anchor.players:
            display_name_by_player_id[player.player_id] = player.display_name

    rows: list[DailyRosterStateRow] = []
    player_rows: list[DailyRosterStatePlayerRow] = []
    for index, anchor in enumerate(snapshot_anchors):
        next_anchor_date = snapshot_anchors[index + 1].snapshot_date if index + 1 < len(snapshot_anchors) else None
        current_anchor_player_ids = {player.player_id for player in anchor.players}
        next_anchor_player_ids = (
            {player.player_id for player in snapshot_anchors[index + 1].players}
            if index + 1 < len(snapshot_anchors)
            else set()
        )
        segment_start = max(season_start, anchor.snapshot_date)
        segment_end = (
            min(season_end, next_anchor_date - timedelta(days=1))
            if next_anchor_date is not None
            else season_end
        )
        if segment_end < segment_start:
            continue

        order_by_player_id: dict[str, int] = {}
        for depth_index, player in enumerate(anchor.players, start=1):
            order_by_player_id[player.player_id] = player.depth_order or depth_index
        derived_order_start = max(order_by_player_id.values(), default=0) + 1000
        derived_order_by_player_id: dict[str, int] = {}
        active_by_player_id = {player.player_id: True for player in anchor.players}

        current_date = segment_start
        while current_date <= segment_end:
            day_changes = sorted(changes_by_date.get(current_date, []), key=lambda item: item.source_event_id)
            day_source_event_ids = list(dict.fromkeys(change.source_event_id for change in day_changes))
            if current_date != anchor.snapshot_date:
                for change in day_changes:
                    active_by_player_id[change.player_id] = change.effect == "in"
                    display_name_by_player_id[change.player_id] = change.display_name
                    if (
                        change.effect == "in"
                        and change.player_id not in order_by_player_id
                        and change.player_id not in derived_order_by_player_id
                    ):
                        derived_order_by_player_id[change.player_id] = (
                            derived_order_start + len(derived_order_by_player_id)
                        )

            active_player_ids = [player_id for player_id, is_active in active_by_player_id.items() if is_active]
            sorted_player_ids = sorted(
                active_player_ids,
                key=lambda player_id: (
                    _snapshot_anchor_membership_priority(
                        player_id,
                        current_anchor_player_ids=current_anchor_player_ids,
                        next_anchor_player_ids=next_anchor_player_ids,
                    ),
                    order_by_player_id.get(player_id, derived_order_by_player_id.get(player_id, 999999)),
                    display_name_by_player_id.get(player_id, player_id),
                    player_id,
                ),
            )[:MAX_ROSTER_SNAPSHOT_PLAYERS]
            roster_state_id = build_daily_roster_state_id(
                team_code=team_code,
                season=season,
                state_date=current_date,
                source_record_id=anchor.source_record_id,
            )
            standard_count = 0
            two_way_count = 0
            for player_id in sorted_player_ids:
                is_two_way = any(
                    interval.start_date <= current_date and (interval.end_date is None or current_date < interval.end_date)
                    for interval in two_way_intervals_by_player_id.get(player_id, [])
                )
                if is_two_way:
                    two_way_count += 1
                else:
                    standard_count += 1
                player_rows.append(
                    DailyRosterStatePlayerRow(
                        roster_state_id=roster_state_id,
                        state_date=current_date,
                        season=season,
                        team_code=team_code,
                        player_id=player_id,
                        display_name=display_name_by_player_id.get(player_id, player_id),
                        asset_id=build_player_asset_id_from_player_id(player_id),
                        roster_status="two_way" if is_two_way else "standard",
                        roster_order=order_by_player_id.get(player_id, derived_order_by_player_id.get(player_id)),
                        is_two_way=is_two_way,
                        is_standard_contract=not is_two_way,
                    )
                )

            rows.append(
                DailyRosterStateRow(
                    roster_state_id=roster_state_id,
                    state_date=current_date,
                    season=season,
                    team_code=team_code,
                    source_record_id=anchor.source_record_id,
                    event_count=len(day_source_event_ids),
                    source_event_ids=day_source_event_ids,
                    player_count=len(sorted_player_ids),
                    standard_count=standard_count,
                    two_way_count=two_way_count,
                    notes=(
                        "Snapshot-anchored Memphis roster occupancy after loaded same-day events; "
                        "quiet days carry forward until the next checkpoint anchor within the graph-facing "
                        f"{MAX_ROSTER_SNAPSHOT_PLAYERS}-player slot surface."
                    ),
                )
            )
            current_date += timedelta(days=1)

    return rows, player_rows


def _snapshot_anchor_membership_priority(
    player_id: str,
    *,
    current_anchor_player_ids: set[str],
    next_anchor_player_ids: set[str],
) -> int:
    if player_id in current_anchor_player_ids and player_id in next_anchor_player_ids:
        return 0
    if player_id in next_anchor_player_ids:
        return 1
    if player_id in current_anchor_player_ids:
        return 2
    return 3


def build_daily_roster_state_id(
    *,
    team_code: str,
    season: str,
    state_date: date,
    source_record_id: str | None,
) -> str:
    source_token = slugify(source_record_id or "source")
    return f"roster-state:{team_code.lower()}:{season}:{state_date.isoformat()}:{source_token}"


def _table_exists(connection: psycopg.Connection, table_name: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass(%s)", (table_name,))
        return cursor.fetchone()[0] is not None


def _validated_table_name(table_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", table_name):
        raise ValueError(f"invalid target table name: {table_name}")
    return table_name


def _delete_daily_roster_state_player_rows(
    connection: psycopg.Connection,
    table_name: str,
    roster_state_ids: list[str],
) -> int:
    if not roster_state_ids:
        return 0
    with connection.cursor() as cursor:
        cursor.execute(
            f"delete from {table_name} where roster_state_id = any(%s)",
            (roster_state_ids,),
        )
        return cursor.rowcount


def _delete_daily_roster_state_rows(
    connection: psycopg.Connection,
    table_name: str,
    roster_state_ids: list[str],
) -> int:
    if not roster_state_ids:
        return 0
    with connection.cursor() as cursor:
        cursor.execute(
            f"delete from {table_name} where roster_state_id = any(%s)",
            (roster_state_ids,),
        )
        return cursor.rowcount


def _insert_daily_roster_state_rows(
    connection: psycopg.Connection,
    table_name: str,
    rows: list[DailyRosterStateRow],
) -> int:
    if not rows:
        return 0
    with connection.cursor() as cursor:
        cursor.executemany(
            f"""
            insert into {table_name} (
                roster_state_id,
                state_date,
                season,
                team_code,
                source_record_id,
                event_count,
                source_event_ids,
                player_count,
                standard_count,
                two_way_count,
                derivation_mode,
                notes
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    row.roster_state_id,
                    row.state_date,
                    row.season,
                    row.team_code,
                    row.source_record_id,
                    row.event_count,
                    row.source_event_ids,
                    row.player_count,
                    row.standard_count,
                    row.two_way_count,
                    "end_of_day_carry_forward",
                    row.notes,
                )
                for row in rows
            ],
        )
    return len(rows)


def _insert_daily_roster_state_player_rows(
    connection: psycopg.Connection,
    table_name: str,
    rows: list[DailyRosterStatePlayerRow],
) -> int:
    if not rows:
        return 0
    with connection.cursor() as cursor:
        cursor.executemany(
            f"""
            insert into {table_name} (
                roster_state_id,
                state_date,
                season,
                team_code,
                player_id,
                display_name,
                asset_id,
                roster_status,
                roster_order,
                is_two_way,
                is_standard_contract
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    row.roster_state_id,
                    row.state_date,
                    row.season,
                    row.team_code,
                    row.player_id,
                    row.display_name,
                    row.asset_id,
                    row.roster_status,
                    row.roster_order,
                    row.is_two_way,
                    row.is_standard_contract,
                )
                for row in rows
            ],
        )
    return len(rows)
