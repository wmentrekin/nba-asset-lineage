from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel

from foundation.workbench import WorkbenchSampleBundle, WorkbenchSourceEvent, load_sample_fixture, run_sample_workbench


SOURCE_EVENT_TYPES = (
    "trade",
    "draft",
    "waiver",
    "signing",
    "re_signing",
    "extension",
    "conversion",
    "release",
)
ASSET_KINDS = ("player", "pick")

FOUNDATION_BOOTSTRAP_SQL_PATH = Path("sql/0001_foundation_ingest_bootstrap.sql")
SAMPLE_FETCHED_AT = "2026-05-08T00:00:00Z"
DEFAULT_PLAYER_ALIAS_OVERRIDES = {
    "kenny lofton jr": "Kenneth Lofton Jr.",
}


class SourceRecordRow(BaseModel):
    source_record_id: str
    source_system: str
    source_type: str
    source_locator: str | None = None
    fetched_at: str
    raw_payload: dict[str, object]


class SourceEventRow(BaseModel):
    source_event_id: str
    source_record_id: str
    event_date: str
    event_type: str
    label: str
    team_scope: str
    source_group_hint: str | None = None
    normalized_payload: dict[str, object]


class PlayerRow(BaseModel):
    player_id: str
    display_name: str
    nba_player_ref: str | None = None
    birth_date: str | None = None
    position_text: str | None = None


class PlayerAliasRow(BaseModel):
    alias_id: str
    player_id: str
    source_system: str
    alias_name: str
    normalized_alias_name: str
    is_manual: bool = False
    notes: str | None = None


class RosterBaselinePlayerRow(BaseModel):
    season: str
    team_code: str
    player_id: str
    display_name: str
    source_record_id: str
    roster_order: int
    nba_player_ref: str | None = None
    birth_date: str | None = None
    position_text: str | None = None
    years_experience: int | None = None


class PickRow(BaseModel):
    pick_id: str
    draft_year: int
    round_number: int
    original_team: str | None = None
    protection_text: str | None = None
    swap_text: str | None = None
    resolution_status: str | None = None
    raw_text: str


class AssetRow(BaseModel):
    asset_id: str
    asset_kind: Literal["player", "pick"]
    player_id: str | None = None
    pick_id: str | None = None
    start_source_event_id: str | None = None
    end_source_event_id: str | None = None


class RosterSnapshotRow(BaseModel):
    snapshot_id: str
    snapshot_date: str
    snapshot_kind: Literal["season_opening", "season_closing", "post_draft", "post_deadline"]
    season: str
    team_code: str
    source_record_id: str | None = None
    notes: str | None = None


class RosterSnapshotPlayerRow(BaseModel):
    snapshot_id: str
    player_id: str
    asset_id: str | None = None
    roster_status: Literal["standard", "two_way", "non_roster"] = "standard"
    depth_order: int | None = None
    is_two_way: bool = False
    is_standard_contract: bool = True


class RosterSnapshotPickRow(BaseModel):
    snapshot_id: str
    pick_id: str
    asset_id: str | None = None
    holding_status: str = "owned"
    display_order: int | None = None


class DraftSelectionRow(BaseModel):
    draft_selection_id: str
    draft_year: int
    pick_overall: int
    round_number: int
    team_code: str
    player_id: str
    pick_id: str | None = None
    source_event_id: str | None = None
    notes: str | None = None


class DraftLotteryResultRow(BaseModel):
    lottery_result_id: str
    draft_year: int
    lottery_date: str | None = None
    team_code: str
    lottery_position: int | None = None
    result_pick_slot: int
    pre_lottery_odds: str | None = None
    notes: str | None = None


class FoundationIngestBundle(BaseModel):
    source_records: list[SourceRecordRow]
    source_events: list[SourceEventRow]
    players: list[PlayerRow]
    picks: list[PickRow]
    assets: list[AssetRow]


class FoundationDerivedEntities(BaseModel):
    players: list[PlayerRow]
    picks: list[PickRow]
    assets: list[AssetRow]
    player_aliases: list[PlayerAliasRow] = []


def bootstrap_foundation_ingest_schema(database_url: str, sql_path: Path = FOUNDATION_BOOTSTRAP_SQL_PATH) -> None:
    sql_text = sql_path.read_text(encoding="utf-8")
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql_text)
        connection.commit()


def build_foundation_ingest_sample_bundle() -> FoundationIngestBundle:
    sample_fixture = load_sample_fixture()
    workbench = run_sample_workbench()

    source_records = build_sample_source_records(sample_fixture)
    source_events = build_source_events(workbench)
    players = build_players(workbench)
    picks = build_picks(workbench)
    assets = build_assets(source_events=source_events, players=players, picks=picks)

    return FoundationIngestBundle(
        source_records=source_records,
        source_events=source_events,
        players=players,
        picks=picks,
        assets=assets,
    )


def serialize_foundation_ingest_sample_bundle() -> dict[str, object]:
    bundle = build_foundation_ingest_sample_bundle()
    return bundle.model_dump(mode="json")


def derive_foundation_entities_from_source_events(
    source_events: list[SourceEventRow],
    baseline_players: list[RosterBaselinePlayerRow] | None = None,
    player_aliases: list[PlayerAliasRow] | None = None,
    reference_players: list[PlayerRow] | None = None,
) -> FoundationDerivedEntities:
    players = build_players_from_source_events(
        source_events,
        baseline_players=baseline_players or [],
        player_aliases=player_aliases or [],
        reference_players=reference_players or [],
    )
    picks = build_picks_from_source_events(source_events)
    assets = build_assets(source_events=source_events, players=players, picks=picks)
    derived_aliases = build_default_player_aliases(players)
    return FoundationDerivedEntities(players=players, picks=picks, assets=assets, player_aliases=derived_aliases)


def load_source_events_from_database(database_url: str) -> list[SourceEventRow]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select source_event_id,
                       source_record_id,
                       event_date::text,
                       event_type,
                       label,
                       team_scope,
                       source_group_hint,
                       normalized_payload
                from foundation.source_event
                order by event_date, source_event_id
                """
            )
            rows = cursor.fetchall()
    return [
        SourceEventRow(
            source_event_id=str(row[0]),
            source_record_id=str(row[1]),
            event_date=str(row[2]),
            event_type=str(row[3]),
            label=str(row[4]),
            team_scope=str(row[5]),
            source_group_hint=str(row[6]) if row[6] is not None else None,
            normalized_payload=dict(row[7]),
        )
        for row in rows
    ]


def derive_foundation_entities_from_database(database_url: str) -> FoundationDerivedEntities:
    source_events = load_source_events_from_database(database_url)
    baseline_players = load_roster_baseline_players_from_database(database_url)
    player_aliases = load_player_aliases_from_database(database_url)
    reference_players = load_players_from_database(database_url)
    return derive_foundation_entities_from_source_events(
        source_events,
        baseline_players=baseline_players,
        player_aliases=player_aliases,
        reference_players=reference_players,
    )


def load_derived_foundation_entities(database_url: str) -> dict[str, int]:
    derived = derive_foundation_entities_from_database(database_url)
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        upsert_players(connection, derived.players)
        upsert_player_aliases(connection, derived.player_aliases)
        upsert_picks(connection, derived.picks)
        upsert_assets(connection, derived.assets)
        connection.commit()
    return {
        "players": len(derived.players),
        "player_aliases": len(derived.player_aliases),
        "picks": len(derived.picks),
        "assets": len(derived.assets),
    }


def build_roster_snapshots_from_baselines(
    baseline_players: list[RosterBaselinePlayerRow],
) -> tuple[list[RosterSnapshotRow], list[RosterSnapshotPlayerRow]]:
    grouped: dict[tuple[str, str, str], list[RosterBaselinePlayerRow]] = {}
    for row in baseline_players:
        grouped.setdefault((row.season, row.team_code, row.source_record_id), []).append(row)

    snapshots: list[RosterSnapshotRow] = []
    snapshot_players: list[RosterSnapshotPlayerRow] = []
    for (season, team_code, source_record_id), rows in sorted(grouped.items()):
        start_year, end_year = parse_season_years(season)
        checkpoint_dates = {
            "post_draft": f"{start_year}-07-01",
            "season_opening": f"{start_year}-10-01",
            "post_deadline": f"{end_year}-02-15",
            "season_closing": f"{end_year}-06-30",
        }
        for snapshot_kind, snapshot_date in checkpoint_dates.items():
            snapshot_id = f"snapshot:{team_code.lower()}:{season}:{snapshot_kind}"
            snapshots.append(
                RosterSnapshotRow(
                    snapshot_id=snapshot_id,
                    snapshot_date=snapshot_date,
                    snapshot_kind=snapshot_kind,  # type: ignore[arg-type]
                    season=season,
                    team_code=team_code,
                    source_record_id=source_record_id,
                    notes="Derived from Basketball-Reference season roster page; not a date-exact transaction-state snapshot.",
                )
            )
            for player in sorted(rows, key=lambda item: item.roster_order):
                snapshot_players.append(
                    RosterSnapshotPlayerRow(
                        snapshot_id=snapshot_id,
                        player_id=player.player_id,
                        asset_id=f"asset:player:{slugify(player.display_name)}",
                        roster_status="standard",
                        depth_order=player.roster_order,
                        is_two_way=False,
                        is_standard_contract=True,
                    )
                )
    return snapshots, snapshot_players


def load_roster_snapshots_from_baselines(database_url: str) -> dict[str, int]:
    baseline_players = load_roster_baseline_players_from_database(database_url)
    snapshots, snapshot_players = build_roster_snapshots_from_baselines(baseline_players)
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        upsert_roster_snapshots(connection, snapshots)
        upsert_roster_snapshot_players(connection, snapshot_players)
        connection.commit()
    return {
        "roster_snapshots": len(snapshots),
        "roster_snapshot_players": len(snapshot_players),
    }


def parse_season_years(season: str) -> tuple[int, int]:
    start_text, end_suffix = season.split("-", 1)
    start_year = int(start_text)
    end_year = int(f"{str(start_year)[:2]}{end_suffix}")
    if end_year < start_year:
        end_year += 100
    return start_year, end_year


def build_sample_source_records(sample_fixture: dict[str, object]) -> list[SourceRecordRow]:
    rows: list[SourceRecordRow] = []
    for entry in sample_fixture["basketball_reference_examples"]:
        rows.append(
            SourceRecordRow(
                source_record_id=str(entry["source_record_id"]),
                source_system="basketball_reference",
                source_type="team_transactions_page",
                source_locator=f"fixture:{entry['source_record_id']}",
                fetched_at=SAMPLE_FETCHED_AT,
                raw_payload={"event_date": entry["event_date"], "note_text": entry["note_text"]},
            )
        )

    rows.append(
        SourceRecordRow(
            source_record_id="nba_stats:common_all_players:sample",
            source_system="nba_stats",
            source_type="common_all_players",
            source_locator="fixture:common_all_players_example",
            fetched_at=SAMPLE_FETCHED_AT,
            raw_payload=dict(sample_fixture["common_all_players_example"]),
        )
    )
    rows.append(
        SourceRecordRow(
            source_record_id="nba_stats:common_team_roster:sample",
            source_system="nba_stats",
            source_type="common_team_roster",
            source_locator="fixture:common_team_roster_example",
            fetched_at=SAMPLE_FETCHED_AT,
            raw_payload=dict(sample_fixture["common_team_roster_example"]),
        )
    )
    return rows


def build_source_events(workbench: WorkbenchSampleBundle) -> list[SourceEventRow]:
    rows: list[SourceEventRow] = []
    for row in workbench.basketball_reference_examples:
        for event in row.normalized_events:
            rows.append(
                SourceEventRow(
                    source_event_id=event.source_event_id,
                    source_record_id=event.source_record_id,
                    event_date=event.event_date,
                    event_type=event.event_type,
                    label=event.label,
                    team_scope=event.team_scope,
                    source_group_hint=event.source_group_hint,
                    normalized_payload=serialize_workbench_event(event),
                )
            )
    return rows


def build_players(workbench: WorkbenchSampleBundle) -> list[PlayerRow]:
    by_name: dict[str, PlayerRow] = {}
    reference = workbench.common_all_players_example
    by_name[reference.display_name] = PlayerRow(
        player_id=reference.player_id,
        display_name=reference.display_name,
        nba_player_ref=reference.nba_player_ref,
        birth_date=reference.birth_date,
        position_text=reference.position_text,
    )

    roster_reference = workbench.common_team_roster_example
    if roster_reference.display_name not in by_name:
        by_name[roster_reference.display_name] = PlayerRow(
            player_id=roster_reference.player_id,
            display_name=roster_reference.display_name,
            birth_date=roster_reference.birth_date,
            position_text=roster_reference.position_text,
        )

    for row in workbench.basketball_reference_examples:
        for event in row.normalized_events:
            for player_name in [*event.player_names_in, *event.player_names_out]:
                if player_name not in by_name:
                    by_name[player_name] = PlayerRow(
                        player_id=f"player:{slugify(player_name)}",
                        display_name=player_name,
                    )
    return sorted(by_name.values(), key=lambda item: item.player_id)


def build_players_from_source_events(
    source_events: list[SourceEventRow],
    *,
    baseline_players: list[RosterBaselinePlayerRow],
    player_aliases: list[PlayerAliasRow] | None = None,
    reference_players: list[PlayerRow] | None = None,
) -> list[PlayerRow]:
    by_player_id: dict[str, PlayerRow] = {}
    player_id_by_display_key: dict[str, str] = {}
    for player in reference_players or []:
        by_player_id[player.player_id] = player
        player_id_by_display_key[normalize_player_alias_name(player.display_name)] = player.player_id
    for baseline in baseline_players:
        row = PlayerRow(
            player_id=baseline.player_id,
            display_name=baseline.display_name,
            nba_player_ref=baseline.nba_player_ref,
            birth_date=baseline.birth_date,
            position_text=baseline.position_text,
        )
        by_player_id[row.player_id] = row
        player_id_by_display_key[normalize_player_alias_name(row.display_name)] = row.player_id

    alias_lookup = build_player_alias_lookup(player_aliases or [], player_id_by_display_key)
    for event in source_events:
        payload = event.normalized_payload
        for player_name in [*payload.get("player_names_in", []), *payload.get("player_names_out", [])]:
            if not isinstance(player_name, str) or not player_name.strip():
                continue
            player_id = resolve_player_id(player_name, player_id_by_display_key, alias_lookup)
            if player_id is None:
                player_id = f"player:{slugify(player_name)}"
                player_id_by_display_key[normalize_player_alias_name(player_name)] = player_id
            if player_id not in by_player_id:
                by_player_id[player_id] = PlayerRow(
                    player_id=player_id,
                    display_name=player_name,
                )
    return sorted(by_player_id.values(), key=lambda item: item.player_id)


def build_default_player_aliases(players: list[PlayerRow]) -> list[PlayerAliasRow]:
    player_by_display_key = {normalize_player_alias_name(player.display_name): player for player in players}
    aliases: list[PlayerAliasRow] = []
    for alias_name, canonical_name in DEFAULT_PLAYER_ALIAS_OVERRIDES.items():
        canonical = player_by_display_key.get(normalize_player_alias_name(canonical_name))
        if canonical is None:
            continue
        aliases.append(
            PlayerAliasRow(
                alias_id=f"alias:manual:{slugify(alias_name)}",
                player_id=canonical.player_id,
                source_system="manual",
                alias_name=alias_name,
                normalized_alias_name=normalize_player_alias_name(alias_name),
                is_manual=True,
                notes=f"Manual alias for {canonical.display_name}",
            )
        )
    return aliases


def build_player_alias_lookup(
    aliases: list[PlayerAliasRow],
    player_id_by_display_key: dict[str, str],
) -> dict[str, str]:
    lookup = dict(player_id_by_display_key)
    for alias in aliases:
        lookup[alias.normalized_alias_name] = alias.player_id
    for alias_name, canonical_name in DEFAULT_PLAYER_ALIAS_OVERRIDES.items():
        canonical_id = player_id_by_display_key.get(normalize_player_alias_name(canonical_name))
        if canonical_id is not None:
            lookup[normalize_player_alias_name(alias_name)] = canonical_id
    return lookup


def resolve_player_id(
    display_name: str,
    player_id_by_display_key: dict[str, str],
    alias_lookup: dict[str, str],
) -> str | None:
    key = normalize_player_alias_name(display_name)
    return alias_lookup.get(key) or player_id_by_display_key.get(key)


def normalize_player_alias_name(value: str) -> str:
    normalized = value.lower().replace(".", "")
    normalized = re_sub(r"\b(junior)\b", "jr", normalized)
    normalized = re_sub(r"\s+", " ", normalized).strip()
    return normalized


def load_roster_baseline_players_from_database(database_url: str) -> list[RosterBaselinePlayerRow]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select to_regclass('foundation.roster_baseline_player')")
            if cursor.fetchone()[0] is None:
                return []
            cursor.execute(
                """
                select season,
                       team_code,
                       player_id,
                       display_name,
                       source_record_id,
                       roster_order,
                       nba_player_ref,
                       birth_date,
                       position_text,
                       years_experience
                from foundation.roster_baseline_player
                order by season, roster_order, display_name
                """
            )
            rows = cursor.fetchall()
    return [
        RosterBaselinePlayerRow(
            season=str(row[0]),
            team_code=str(row[1]),
            player_id=str(row[2]),
            display_name=str(row[3]),
            source_record_id=str(row[4]),
            roster_order=int(row[5]),
            nba_player_ref=str(row[6]) if row[6] is not None else None,
            birth_date=str(row[7]) if row[7] is not None else None,
            position_text=str(row[8]) if row[8] is not None else None,
            years_experience=int(row[9]) if row[9] is not None else None,
        )
        for row in rows
    ]


def load_players_from_database(database_url: str) -> list[PlayerRow]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select to_regclass('foundation.player')")
            if cursor.fetchone()[0] is None:
                return []
            cursor.execute(
                """
                select player_id, display_name, nba_player_ref, birth_date, position_text
                from foundation.player
                order by player_id
                """
            )
            rows = cursor.fetchall()
    return [
        PlayerRow(
            player_id=str(row[0]),
            display_name=str(row[1]),
            nba_player_ref=str(row[2]) if row[2] is not None else None,
            birth_date=str(row[3]) if row[3] is not None else None,
            position_text=str(row[4]) if row[4] is not None else None,
        )
        for row in rows
    ]


def load_player_aliases_from_database(database_url: str) -> list[PlayerAliasRow]:
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select to_regclass('foundation.player_alias')")
            if cursor.fetchone()[0] is None:
                return []
            cursor.execute(
                """
                select alias_id,
                       player_id,
                       source_system,
                       alias_name,
                       normalized_alias_name,
                       is_manual,
                       notes
                from foundation.player_alias
                order by source_system, normalized_alias_name
                """
            )
            rows = cursor.fetchall()
    return [
        PlayerAliasRow(
            alias_id=str(row[0]),
            player_id=str(row[1]),
            source_system=str(row[2]),
            alias_name=str(row[3]),
            normalized_alias_name=str(row[4]),
            is_manual=bool(row[5]),
            notes=str(row[6]) if row[6] is not None else None,
        )
        for row in rows
    ]


def build_picks(workbench: WorkbenchSampleBundle) -> list[PickRow]:
    by_pick_id: dict[str, PickRow] = {}
    for row in workbench.basketball_reference_examples:
        for event in row.normalized_events:
            for detail in [*event.pick_details_in, *event.pick_details_out]:
                if detail.draft_year is None or detail.round_number is None:
                    continue
                pick_id = build_pick_id(detail.raw_text)
                by_pick_id[pick_id] = PickRow(
                    pick_id=pick_id,
                    draft_year=detail.draft_year,
                    round_number=detail.round_number,
                    original_team=detail.original_team,
                    protection_text=detail.protection_text,
                    swap_text=detail.swap_text,
                    resolution_status=None,
                    raw_text=detail.raw_text,
                )
    return sorted(by_pick_id.values(), key=lambda item: item.pick_id)


def build_picks_from_source_events(source_events: list[SourceEventRow]) -> list[PickRow]:
    by_pick_id: dict[str, PickRow] = {}
    for event in source_events:
        payload = event.normalized_payload
        for detail in [*payload.get("pick_details_in", []), *payload.get("pick_details_out", [])]:
            if not isinstance(detail, dict):
                continue
            draft_year = detail.get("draft_year")
            round_number = detail.get("round_number")
            raw_text = detail.get("raw_text")
            if not isinstance(draft_year, int) or not isinstance(round_number, int) or not isinstance(raw_text, str):
                continue
            pick_id = build_pick_id(raw_text)
            by_pick_id[pick_id] = PickRow(
                pick_id=pick_id,
                draft_year=draft_year,
                round_number=round_number,
                original_team=detail.get("original_team") if isinstance(detail.get("original_team"), str) else None,
                protection_text=detail.get("protection_text") if isinstance(detail.get("protection_text"), str) else None,
                swap_text=detail.get("swap_text") if isinstance(detail.get("swap_text"), str) else None,
                resolution_status=None,
                raw_text=raw_text,
            )
    return sorted(by_pick_id.values(), key=lambda item: item.pick_id)


def build_assets(
    *,
    source_events: list[SourceEventRow],
    players: list[PlayerRow],
    picks: list[PickRow],
) -> list[AssetRow]:
    assets: list[AssetRow] = []
    player_names_by_event = {
        event.source_event_id: event.normalized_payload
        for event in source_events
    }
    for player in players:
        first_event_id = find_first_event_for_player(player.display_name, source_events)
        assets.append(
            AssetRow(
                asset_id=f"asset:player:{slugify(player.display_name)}",
                asset_kind="player",
                player_id=player.player_id,
                start_source_event_id=first_event_id,
            )
        )
    for pick in picks:
        first_event_id = find_first_event_for_pick(pick.raw_text, source_events)
        assets.append(
            AssetRow(
                asset_id=f"asset:pick:{pick.pick_id}",
                asset_kind="pick",
                pick_id=pick.pick_id,
                start_source_event_id=first_event_id,
            )
        )
    return assets


def serialize_workbench_event(event: WorkbenchSourceEvent) -> dict[str, object]:
    payload = asdict(event)
    payload["pick_details_in"] = [asdict(detail) for detail in event.pick_details_in]
    payload["pick_details_out"] = [asdict(detail) for detail in event.pick_details_out]
    return payload


def find_first_event_for_player(display_name: str, source_events: list[SourceEventRow]) -> str | None:
    for event in source_events:
        payload = event.normalized_payload
        if display_name in payload.get("player_names_in", []) or display_name in payload.get("player_names_out", []):
            return event.source_event_id
    return None


def find_first_event_for_pick(raw_text: str, source_events: list[SourceEventRow]) -> str | None:
    for event in source_events:
        payload = event.normalized_payload
        if raw_text in payload.get("pick_text_in", []) or raw_text in payload.get("pick_text_out", []):
            return event.source_event_id
    return None


def build_pick_id(raw_text: str) -> str:
    digest = hashlib.sha1(raw_text.encode("utf-8")).hexdigest()[:10]
    return f"pick:{digest}"


def slugify(value: str) -> str:
    normalized = value.lower()
    normalized = re_sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return normalized


def re_sub(pattern: str, replacement: str, value: str) -> str:
    import re

    return re.sub(pattern, replacement, value)


def upsert_players(connection: psycopg.Connection, rows: list[PlayerRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.player (
                    player_id, display_name, nba_player_ref, birth_date, position_text
                ) values (%s, %s, %s, %s, %s)
                on conflict (player_id) do update
                set display_name = excluded.display_name,
                    nba_player_ref = excluded.nba_player_ref,
                    birth_date = excluded.birth_date,
                    position_text = excluded.position_text
                """,
                (
                    row.player_id,
                    row.display_name,
                    row.nba_player_ref,
                    row.birth_date,
                    row.position_text,
                ),
            )


def upsert_player_aliases(connection: psycopg.Connection, rows: list[PlayerAliasRow]) -> None:
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass('foundation.player_alias')")
        if cursor.fetchone()[0] is None:
            return
        for row in rows:
            cursor.execute(
                """
                insert into foundation.player_alias (
                    alias_id, player_id, source_system, alias_name, normalized_alias_name, is_manual, notes
                ) values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (alias_id) do update
                set player_id = excluded.player_id,
                    source_system = excluded.source_system,
                    alias_name = excluded.alias_name,
                    normalized_alias_name = excluded.normalized_alias_name,
                    is_manual = excluded.is_manual,
                    notes = excluded.notes
                """,
                (
                    row.alias_id,
                    row.player_id,
                    row.source_system,
                    row.alias_name,
                    row.normalized_alias_name,
                    row.is_manual,
                    row.notes,
                ),
            )


def upsert_roster_baseline_players(connection: psycopg.Connection, rows: list[RosterBaselinePlayerRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.roster_baseline_player (
                    season, team_code, player_id, display_name, source_record_id, roster_order,
                    nba_player_ref, birth_date, position_text, years_experience
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (season, team_code, player_id) do update
                set display_name = excluded.display_name,
                    source_record_id = excluded.source_record_id,
                    roster_order = excluded.roster_order,
                    nba_player_ref = excluded.nba_player_ref,
                    birth_date = excluded.birth_date,
                    position_text = excluded.position_text,
                    years_experience = excluded.years_experience
                """,
                (
                    row.season,
                    row.team_code,
                    row.player_id,
                    row.display_name,
                    row.source_record_id,
                    row.roster_order,
                    row.nba_player_ref,
                    row.birth_date,
                    row.position_text,
                    row.years_experience,
                ),
            )


def upsert_picks(connection: psycopg.Connection, rows: list[PickRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.pick (
                    pick_id, draft_year, round_number, original_team, protection_text, swap_text, resolution_status, raw_text
                ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (pick_id) do update
                set draft_year = excluded.draft_year,
                    round_number = excluded.round_number,
                    original_team = excluded.original_team,
                    protection_text = excluded.protection_text,
                    swap_text = excluded.swap_text,
                    resolution_status = excluded.resolution_status,
                    raw_text = excluded.raw_text
                """,
                (
                    row.pick_id,
                    row.draft_year,
                    row.round_number,
                    row.original_team,
                    row.protection_text,
                    row.swap_text,
                    row.resolution_status,
                    row.raw_text,
                ),
            )


def upsert_assets(connection: psycopg.Connection, rows: list[AssetRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.asset (
                    asset_id, asset_kind, player_id, pick_id, start_source_event_id, end_source_event_id
                ) values (%s, %s, %s, %s, %s, %s)
                on conflict (asset_id) do update
                set asset_kind = excluded.asset_kind,
                    player_id = excluded.player_id,
                    pick_id = excluded.pick_id,
                    start_source_event_id = excluded.start_source_event_id,
                    end_source_event_id = excluded.end_source_event_id
                """,
                (
                    row.asset_id,
                    row.asset_kind,
                    row.player_id,
                    row.pick_id,
                    row.start_source_event_id,
                    row.end_source_event_id,
                ),
            )


def upsert_roster_snapshots(connection: psycopg.Connection, rows: list[RosterSnapshotRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.roster_snapshot (
                    snapshot_id, snapshot_date, snapshot_kind, season, team_code, source_record_id, notes
                ) values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (snapshot_id) do update
                set snapshot_date = excluded.snapshot_date,
                    snapshot_kind = excluded.snapshot_kind,
                    season = excluded.season,
                    team_code = excluded.team_code,
                    source_record_id = excluded.source_record_id,
                    notes = excluded.notes
                """,
                (
                    row.snapshot_id,
                    row.snapshot_date,
                    row.snapshot_kind,
                    row.season,
                    row.team_code,
                    row.source_record_id,
                    row.notes,
                ),
            )


def upsert_roster_snapshot_players(connection: psycopg.Connection, rows: list[RosterSnapshotPlayerRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.roster_snapshot_player (
                    snapshot_id, player_id, asset_id, roster_status, depth_order, is_two_way, is_standard_contract
                ) values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (snapshot_id, player_id) do update
                set asset_id = excluded.asset_id,
                    roster_status = excluded.roster_status,
                    depth_order = excluded.depth_order,
                    is_two_way = excluded.is_two_way,
                    is_standard_contract = excluded.is_standard_contract
                """,
                (
                    row.snapshot_id,
                    row.player_id,
                    row.asset_id,
                    row.roster_status,
                    row.depth_order,
                    row.is_two_way,
                    row.is_standard_contract,
                ),
            )


def upsert_roster_snapshot_picks(connection: psycopg.Connection, rows: list[RosterSnapshotPickRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.roster_snapshot_pick (
                    snapshot_id, pick_id, asset_id, holding_status, display_order
                ) values (%s, %s, %s, %s, %s)
                on conflict (snapshot_id, pick_id) do update
                set asset_id = excluded.asset_id,
                    holding_status = excluded.holding_status,
                    display_order = excluded.display_order
                """,
                (
                    row.snapshot_id,
                    row.pick_id,
                    row.asset_id,
                    row.holding_status,
                    row.display_order,
                ),
            )


def upsert_draft_selections(connection: psycopg.Connection, rows: list[DraftSelectionRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.draft_selection (
                    draft_selection_id, draft_year, pick_overall, round_number, team_code,
                    player_id, pick_id, source_event_id, notes
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (draft_selection_id) do update
                set draft_year = excluded.draft_year,
                    pick_overall = excluded.pick_overall,
                    round_number = excluded.round_number,
                    team_code = excluded.team_code,
                    player_id = excluded.player_id,
                    pick_id = excluded.pick_id,
                    source_event_id = excluded.source_event_id,
                    notes = excluded.notes
                """,
                (
                    row.draft_selection_id,
                    row.draft_year,
                    row.pick_overall,
                    row.round_number,
                    row.team_code,
                    row.player_id,
                    row.pick_id,
                    row.source_event_id,
                    row.notes,
                ),
            )


def upsert_draft_lottery_results(connection: psycopg.Connection, rows: list[DraftLotteryResultRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.draft_lottery_result (
                    lottery_result_id, draft_year, lottery_date, team_code, lottery_position,
                    result_pick_slot, pre_lottery_odds, notes
                ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (lottery_result_id) do update
                set draft_year = excluded.draft_year,
                    lottery_date = excluded.lottery_date,
                    team_code = excluded.team_code,
                    lottery_position = excluded.lottery_position,
                    result_pick_slot = excluded.result_pick_slot,
                    pre_lottery_odds = excluded.pre_lottery_odds,
                    notes = excluded.notes
                """,
                (
                    row.lottery_result_id,
                    row.draft_year,
                    row.lottery_date,
                    row.team_code,
                    row.lottery_position,
                    row.result_pick_slot,
                    row.pre_lottery_odds,
                    row.notes,
                ),
            )
