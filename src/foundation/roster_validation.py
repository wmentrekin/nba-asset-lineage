from __future__ import annotations

import json
import re
from collections import defaultdict

import psycopg

from foundation.ingest import (
    RosterSnapshotValidationRow,
    load_player_aliases_from_database,
    normalize_player_alias_name,
    upsert_roster_snapshot_validations,
)
from foundation.sources import is_official_roster_reference_source


def preview_roster_snapshot_validation(
    database_url: str,
    *,
    team_code: str = "MEM",
) -> dict[str, object]:
    rows = build_roster_snapshot_validation_rows_from_database(database_url, team_code=team_code)
    return {
        "status": "ok",
        "writes_to_database": False,
        "team_code": team_code.upper(),
        **summarize_roster_snapshot_validation_rows(rows),
        "first_validation": rows[0].model_dump(mode="json") if rows else None,
    }


def load_roster_snapshot_validation(
    database_url: str,
    *,
    team_code: str = "MEM",
) -> dict[str, object]:
    rows = build_roster_snapshot_validation_rows_from_database(database_url, team_code=team_code)
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        upsert_roster_snapshot_validations(connection, rows)
        connection.commit()
    return {
        "status": "ok",
        "writes_to_database": True,
        "team_code": team_code.upper(),
        **summarize_roster_snapshot_validation_rows(rows),
        "first_validation": rows[0].model_dump(mode="json") if rows else None,
    }


def build_roster_snapshot_validation_rows_from_database(
    database_url: str,
    *,
    team_code: str = "MEM",
) -> list[RosterSnapshotValidationRow]:
    aliases = load_player_aliases_from_database(database_url)
    alias_names_by_player_id: dict[str, set[str]] = defaultdict(set)
    for alias in aliases:
        alias_names_by_player_id[alias.player_id].add(alias.alias_name)

    with psycopg.connect(database_url, connect_timeout=20) as connection:
        snapshots = load_snapshot_validation_candidates(connection, team_code=team_code)
        references_by_season = load_roster_reference_by_season(connection, team_code=team_code)

    return build_roster_snapshot_validation_rows_from_inputs(
        snapshots=snapshots,
        references_by_season=references_by_season,
        alias_names_by_player_id=alias_names_by_player_id,
    )


def build_roster_snapshot_validation_rows_from_inputs(
    *,
    snapshots: list[dict[str, object]],
    references_by_season: dict[tuple[str, str], dict[str, object]],
    alias_names_by_player_id: dict[str, set[str]],
) -> list[RosterSnapshotValidationRow]:
    rows: list[RosterSnapshotValidationRow] = []
    for snapshot in sorted(snapshots, key=lambda item: (str(item.get("snapshot_date")), str(item.get("snapshot_id")))):
        snapshot_id = str(snapshot["snapshot_id"])
        season = str(snapshot["season"])
        team_code = str(snapshot["team_code"]).upper()
        players = list(snapshot.get("players", []))
        reference = references_by_season.get((team_code, season))
        if reference is None:
            rows.append(
                RosterSnapshotValidationRow(
                    snapshot_id=snapshot_id,
                    validation_status="source_missing",
                    reference_source_record_id=None,
                    snapshot_player_count=len(players),
                    reference_player_count=None,
                    matched_player_count=0,
                    notes=(
                        "No loaded official roster reference source record exists for "
                        f"{team_code} {season}."
                    ),
                )
            )
            continue

        reference_player_ids = set(str(value) for value in reference.get("player_ids", set()) if value)
        reference_name_keys = set(str(value) for value in reference.get("name_keys", set()) if value)
        unmatched_names: list[str] = []
        matched_player_count = 0

        for player in players:
            player_id = str(player.get("player_id") or "")
            display_name = str(player.get("display_name") or player_id)
            player_keys = build_identity_keys(display_name)
            for alias_name in sorted(alias_names_by_player_id.get(player_id, set())):
                player_keys.update(build_identity_keys(alias_name))
            if player_id and player_id in reference_player_ids:
                matched_player_count += 1
                continue
            if player_keys.intersection(reference_name_keys):
                matched_player_count += 1
                continue
            unmatched_names.append(display_name)

        snapshot_player_count = len(players)
        reference_player_count = int(reference.get("player_count", 0))
        validation_status = (
            "season_reference_backed"
            if matched_player_count == snapshot_player_count
            else "season_reference_incomplete"
        )
        notes = build_roster_snapshot_validation_note(
            matched_player_count=matched_player_count,
            snapshot_player_count=snapshot_player_count,
            reference_player_count=reference_player_count,
            unmatched_names=unmatched_names,
        )
        rows.append(
            RosterSnapshotValidationRow(
                snapshot_id=snapshot_id,
                validation_status=validation_status,
                reference_source_record_id=str(reference["source_record_id"]),
                snapshot_player_count=snapshot_player_count,
                reference_player_count=reference_player_count,
                matched_player_count=matched_player_count,
                notes=notes,
            )
        )

    return rows


def load_snapshot_validation_candidates(
    connection: psycopg.Connection,
    *,
    team_code: str,
) -> list[dict[str, object]]:
    if not table_exists(connection, "roster_snapshot") or not table_exists(connection, "roster_snapshot_player"):
        return []

    has_player_table = table_exists(connection, "player")
    has_baseline_table = table_exists(connection, "roster_baseline_player")
    player_join = (
        "left join foundation.player p on p.player_id = rsp.player_id"
        if has_player_table
        else ""
    )
    baseline_join = (
        """
        left join lateral (
            select rb.display_name
            from foundation.roster_baseline_player rb
            where rb.player_id = rsp.player_id
              and rb.team_code = rs.team_code
            order by (rb.season = rs.season) desc, rb.season desc
            limit 1
        ) rb on true
        """
        if has_baseline_table
        else ""
    )
    display_name_expr_parts = []
    if has_player_table:
        display_name_expr_parts.append("p.display_name")
    if has_baseline_table:
        display_name_expr_parts.append("rb.display_name")
    display_name_expr_parts.append("rsp.player_id")
    display_name_expr = f"coalesce({', '.join(display_name_expr_parts)})"

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            select rs.snapshot_id,
                   rs.snapshot_date::text,
                   rs.snapshot_kind,
                   rs.season,
                   rs.team_code,
                   rsp.player_id,
                   {display_name_expr} as display_name
            from foundation.roster_snapshot rs
            join foundation.roster_snapshot_player rsp
              on rsp.snapshot_id = rs.snapshot_id
            {player_join}
            {baseline_join}
            where rs.team_code = %s
            order by rs.snapshot_date, rs.snapshot_id, coalesce(rsp.depth_order, 999), {display_name_expr}
            """,
            (team_code.upper(),),
        )
        rows = cursor.fetchall()

    grouped: dict[str, dict[str, object]] = {}
    ordered_ids: list[str] = []
    for row in rows:
        snapshot_id = str(row[0])
        candidate = grouped.get(snapshot_id)
        if candidate is None:
            candidate = {
                "snapshot_id": snapshot_id,
                "snapshot_date": str(row[1]),
                "snapshot_kind": str(row[2]),
                "season": str(row[3]),
                "team_code": str(row[4]).upper(),
                "players": [],
            }
            grouped[snapshot_id] = candidate
            ordered_ids.append(snapshot_id)
        candidate["players"].append(
            {
                "player_id": str(row[5]),
                "display_name": str(row[6]),
            }
        )

    return [grouped[snapshot_id] for snapshot_id in ordered_ids]


def load_roster_reference_by_season(
    connection: psycopg.Connection,
    *,
    team_code: str,
) -> dict[tuple[str, str], dict[str, object]]:
    if not table_exists(connection, "source_record"):
        return {}

    with connection.cursor() as cursor:
        cursor.execute(
            """
            select source_record_id, source_system, source_type, raw_payload
            from foundation.source_record
            order by source_record_id
            """
        )
        rows = cursor.fetchall()

    references: dict[tuple[str, str], dict[str, object]] = {}
    for source_record_id, source_system, source_type, raw_payload in rows:
        payload = coerce_payload(raw_payload)
        if not is_official_roster_reference_source(
            source_system=source_system,
            source_type=source_type,
            raw_payload=payload,
        ):
            continue
        payload_team_code = str(payload.get("team_code") or "").upper()
        season = str(payload.get("season") or "")
        if payload_team_code != team_code.upper() or not season:
            continue
        roster_rows = payload.get("roster_rows", [])
        if not isinstance(roster_rows, list):
            roster_rows = []
        player_ids: set[str] = set()
        name_keys: set[str] = set()
        for roster_row in roster_rows:
            if not isinstance(roster_row, dict):
                continue
            resolved_player_id = roster_row.get("resolved_player_id")
            if isinstance(resolved_player_id, str) and resolved_player_id:
                player_ids.add(resolved_player_id)
            display_name = roster_row.get("PLAYER") or roster_row.get("player") or roster_row.get("display_name")
            if isinstance(display_name, str) and display_name.strip():
                name_keys.update(build_identity_keys(display_name))
        references[(payload_team_code, season)] = {
            "source_record_id": str(source_record_id),
            "player_count": len(roster_rows),
            "player_ids": player_ids,
            "name_keys": name_keys,
        }

    return references


def build_identity_keys(display_name: str) -> set[str]:
    base_key = normalize_player_alias_name(display_name)
    no_apostrophes = re.sub(r"[’']", "", base_key)
    compact = re.sub(r"[^a-z0-9]+", "", no_apostrophes)
    return {key for key in (base_key, no_apostrophes, compact) if key}


def build_roster_snapshot_validation_note(
    *,
    matched_player_count: int,
    snapshot_player_count: int,
    reference_player_count: int,
    unmatched_names: list[str],
) -> str:
    base_note = (
        "Season-scoped official roster reference matched "
        f"{matched_player_count} of {snapshot_player_count} snapshot players "
        f"against {reference_player_count} official roster rows."
    )
    if unmatched_names:
        sample = ", ".join(unmatched_names[:5])
        remainder = len(unmatched_names) - min(len(unmatched_names), 5)
        if remainder > 0:
            sample = f"{sample}, and {remainder} more"
        return (
            f"{base_note} Unmatched snapshot players: {sample}. "
            "This validates season membership only and does not prove exact day-of-checkpoint official occupancy."
        )
    return (
        f"{base_note} "
        "This validates season membership only and does not prove exact day-of-checkpoint official occupancy."
    )


def summarize_roster_snapshot_validation_rows(
    rows: list[RosterSnapshotValidationRow],
) -> dict[str, object]:
    by_status: dict[str, int] = {}
    reference_source_record_ids: set[str] = set()
    for row in rows:
        by_status[row.validation_status] = by_status.get(row.validation_status, 0) + 1
        if row.reference_source_record_id:
            reference_source_record_ids.add(row.reference_source_record_id)
    return {
        "snapshot_validations": len(rows),
        "by_status": dict(sorted(by_status.items())),
        "reference_source_records": len(reference_source_record_ids),
    }


def table_exists(connection: psycopg.Connection, table_name: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass(%s)", (f"foundation.{table_name}",))
        return cursor.fetchone()[0] is not None


def coerce_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return {}
