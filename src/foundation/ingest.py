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


class FoundationIngestBundle(BaseModel):
    source_records: list[SourceRecordRow]
    source_events: list[SourceEventRow]
    players: list[PlayerRow]
    picks: list[PickRow]
    assets: list[AssetRow]


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
