from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from socket import timeout as socket_timeout
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg

from foundation.ingest import (
    DraftSelectionRow,
    PlayerRow,
    RosterBaselinePlayerRow,
    SourceEventRow,
    SourceRecordRow,
    upsert_draft_selections,
    upsert_roster_baseline_players,
)
from foundation.models import draft_event_date
from foundation.prototypes import normalize_common_all_players_row, normalize_common_team_roster_row
from foundation.workbench import normalize_bref_transaction_block


BREF_USER_AGENT = "Mozilla/5.0"
NBA_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}
DEFAULT_TEAM_CODE = "MEM"
DEFAULT_SEASON_START_YEAR = 2017
DEFAULT_SEASON_END_YEAR = 2026
NBA_PLAYER_MOVEMENT_SOURCE_SYSTEM = "nba_player_movement"
NBA_PLAYER_MOVEMENT_ENDPOINT_URL = "https://stats.nba.com/js/data/playermovement/NBA_Player_Movement.json"
NBA_PLAYER_MOVEMENT_MEMPHIS_TEAM_ID = "1610612763"
NBA_PLAYER_MOVEMENT_MEMPHIS_TEAM_SLUG = "grizzlies"
NBA_PLAYER_MOVEMENT_SOURCE_TYPE = "transactions_json"
NBA_PLAYER_MOVEMENT_CANONICAL_EXCLUSION_REASON = "nba_player_movement_requires_reconciliation"
NBA_PLAYER_MOVEMENT_NORMALIZATION_NOTE = (
    "Normalized event type is loader compatibility only; canonical reconciliation is deferred."
)
OFFICIAL_ARTICLE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}
OFFICIAL_RELEASE_SOURCE_SYSTEMS = frozenset({"nba_official", "team_official"})
OFFICIAL_RELEASE_SOURCE_TYPES = frozenset(
    {"news_release_article", "press_release_article", "transaction_page"}
)
OFFICIAL_RELEASE_CANONICAL_EXCLUSION_REASON = "official_release_requires_reconciliation"
BREF_SIGN_AND_TRADE_CANONICAL_EXCLUSION_REASON = "bref_same_day_sign_and_trade_contract"
OFFICIAL_RELEASE_NORMALIZATION_NOTE = (
    "Official article evidence is curated/manual and excluded from canonical derivation by default."
)
NBA_PLAYER_MOVEMENT_TRANSACTION_TYPE_MAP = {
    "AwardOnWaivers": "signing",
    "ContractConverted": "conversion",
    "Signing": "signing",
    "Trade": "trade",
    "Waive": "waiver",
}
DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH = Path("tests/foundation/fixtures/nba_player_movement_sample.json")
DEFAULT_OFFICIAL_RELEASE_FIXTURE_PATH = Path("configs/data/memphis_official_release_sources_seed_v1.json")
DEFAULT_OFFICIAL_RELEASE_FRAGMENT_DIR = Path("configs/data/memphis_official_release_fragments")


def build_bref_transactions_url(team_code: str, season_end_year: int) -> str:
    return f"https://www.basketball-reference.com/teams/{team_code.upper()}/{season_end_year}_transactions.html"


def build_bref_team_season_url(team_code: str, season_end_year: int) -> str:
    return f"https://www.basketball-reference.com/teams/{team_code.upper()}/{season_end_year}.html"


def build_bref_draft_url(draft_year: int) -> str:
    return f"https://www.basketball-reference.com/draft/NBA_{draft_year}.html"


def build_bref_draft_source_event_id(draft_year: int, pick_overall: int) -> str:
    return f"bref:draft:{draft_year}:pick:{pick_overall:03d}"


def fetch_bref_transactions_html(team_code: str, season_end_year: int) -> str:
    return fetch_text(
        build_bref_transactions_url(team_code=team_code, season_end_year=season_end_year),
        headers={"User-Agent": BREF_USER_AGENT},
    )


def fetch_bref_team_season_html(team_code: str, season_end_year: int) -> str:
    return fetch_text(
        build_bref_team_season_url(team_code=team_code, season_end_year=season_end_year),
        headers={"User-Agent": BREF_USER_AGENT},
    )


def fetch_bref_draft_html(draft_year: int) -> str:
    return fetch_text(
        build_bref_draft_url(draft_year=draft_year),
        headers={"User-Agent": BREF_USER_AGENT},
    )


def extract_bref_transaction_blocks(html: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    pattern = re.compile(r"<li>\s*<span><span>(?P<date>[^<]+)</span></span>(?P<body>.*?)</li>", re.S | re.I)
    transaction_pattern = re.compile(r'<p[^>]*class="transaction[^"]*"[^>]*>(.*?)</p>', re.S | re.I)

    for match in pattern.finditer(html):
        body = match.group("body")
        if 'class="transaction' not in body:
            continue
        date_text = clean_html(match.group("date"))
        transactions = [clean_html(chunk) for chunk in transaction_pattern.findall(body)]
        for transaction_index, note_text in enumerate(transactions, start=1):
            if not note_text:
                continue
            items.append(
                {
                    "event_date": normalize_month_day_year(date_text),
                    "note_text": note_text,
                    "transaction_index": str(transaction_index),
                }
            )
    return items


def build_bref_source_rows(
    *,
    team_code: str,
    season_end_year: int,
    html: str,
) -> tuple[list[SourceRecordRow], list[SourceEventRow]]:
    blocks = extract_bref_transaction_blocks(html)
    source_records: list[SourceRecordRow] = []
    source_events: list[SourceEventRow] = []
    page_url = build_bref_transactions_url(team_code=team_code, season_end_year=season_end_year)
    fetched_at = utc_now_iso()

    for block in blocks:
        source_record_id = (
            f"bref:{team_code.lower()}:{season_end_year}:{block['event_date']}:{block['transaction_index']}"
        )
        source_records.append(
            SourceRecordRow(
                source_record_id=source_record_id,
                source_system="basketball_reference",
                source_type="team_transactions_page",
                source_locator=page_url,
                fetched_at=fetched_at,
                raw_payload={
                    "event_date": block["event_date"],
                    "note_text": block["note_text"],
                    "season_end_year": season_end_year,
                    "team_code": team_code.upper(),
                },
            )
        )
        row_result = normalize_bref_transaction_block(
            source_record_id=source_record_id,
            event_date=block["event_date"],
            note_text=block["note_text"],
        )
        for event in row_result.normalized_events:
            source_events.append(
                SourceEventRow(
                    source_event_id=event.source_event_id,
                    source_record_id=event.source_record_id,
                    event_date=event.event_date,
                    event_type=event.event_type,
                    label=event.label,
                    team_scope=event.team_scope,
                    source_group_hint=event.source_group_hint,
                    normalized_payload={
                        "player_names_in": event.player_names_in,
                        "player_names_out": event.player_names_out,
                        "pick_text_in": event.pick_text_in,
                        "pick_text_out": event.pick_text_out,
                        "pick_details_in": [detail.__dict__ for detail in event.pick_details_in],
                        "pick_details_out": [detail.__dict__ for detail in event.pick_details_out],
                        "extraction_notes": event.extraction_notes,
                        "raw_note": event.raw_note,
                    },
                )
            )
    apply_bref_canonical_repairs(source_events)
    return source_records, source_events


def apply_bref_canonical_repairs(source_events: list[SourceEventRow]) -> None:
    outbound_trade_players_by_date: dict[str, set[str]] = {}
    for source_event in source_events:
        if source_event.event_type != "trade":
            continue
        outbound_trade_players_by_date.setdefault(source_event.event_date, set()).update(
            str(name)
            for name in source_event.normalized_payload.get("player_names_out", [])
            if isinstance(name, str) and name.strip()
        )

    for source_event in source_events:
        if source_event.event_type != "signing":
            continue
        inbound_players = {
            str(name)
            for name in source_event.normalized_payload.get("player_names_in", [])
            if isinstance(name, str) and name.strip()
        }
        if not inbound_players:
            continue
        if not inbound_players.intersection(outbound_trade_players_by_date.get(source_event.event_date, set())):
            continue
        notes = [
            str(note)
            for note in source_event.normalized_payload.get("extraction_notes", [])
            if isinstance(note, str) and note.strip()
        ]
        if "same_day_sign_and_trade_contract_excluded" not in notes:
            notes.append("same_day_sign_and_trade_contract_excluded")
        source_event.normalized_payload["extraction_notes"] = notes
        source_event.normalized_payload["canonical_exclusion_reason"] = (
            BREF_SIGN_AND_TRADE_CANONICAL_EXCLUSION_REASON
        )


def load_bref_source_events(database_url: str, *, team_code: str, season_end_year: int) -> dict[str, object]:
    html = fetch_bref_transactions_html(team_code=team_code, season_end_year=season_end_year)
    source_records, source_events = build_bref_source_rows(
        team_code=team_code,
        season_end_year=season_end_year,
        html=html,
    )
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        insert_source_records(connection, source_records)
        replace_source_events_for_records(
            connection,
            source_record_ids=[row.source_record_id for row in source_records],
            rows=source_events,
        )
        insert_source_events(connection, source_events)
        connection.commit()
    return {
        "status": "ok",
        "source_records": len(source_records),
        "source_events": len(source_events),
        "season_end_year": season_end_year,
        "team_code": team_code.upper(),
    }


def load_bref_source_events_span(
    database_url: str,
    *,
    team_code: str = DEFAULT_TEAM_CODE,
    start_season_end_year: int = DEFAULT_SEASON_START_YEAR,
    end_season_end_year: int = DEFAULT_SEASON_END_YEAR,
    request_delay: float = 0.8,
) -> dict[str, object]:
    seasons: list[dict[str, object]] = []
    total_source_records = 0
    total_source_events = 0
    for season_end_year in range(start_season_end_year, end_season_end_year + 1):
        result = load_bref_source_events(
            database_url,
            team_code=team_code,
            season_end_year=season_end_year,
        )
        seasons.append(result)
        total_source_records += int(result["source_records"])
        total_source_events += int(result["source_events"])
        time.sleep(request_delay)
    return {
        "status": "ok",
        "team_code": team_code.upper(),
        "start_season_end_year": start_season_end_year,
        "end_season_end_year": end_season_end_year,
        "source_records": total_source_records,
        "source_events": total_source_events,
        "seasons": seasons,
    }


def preview_bref_source_events(*, team_code: str, season_end_year: int) -> dict[str, object]:
    html = fetch_bref_transactions_html(team_code=team_code, season_end_year=season_end_year)
    source_records, source_events = build_bref_source_rows(
        team_code=team_code,
        season_end_year=season_end_year,
        html=html,
    )
    return {
        "status": "ok",
        "source_records": len(source_records),
        "source_events": len(source_events),
        "first_source_record": source_records[0].model_dump(mode="json") if source_records else None,
        "first_source_event": source_events[0].model_dump(mode="json") if source_events else None,
        "season_end_year": season_end_year,
        "team_code": team_code.upper(),
    }


def extract_bref_roster_rows(html: str) -> list[dict[str, object]]:
    roster_match = re.search(r'<table[^>]*id="roster"[^>]*>(?P<body>.*?)</table>', html, re.S | re.I)
    if not roster_match:
        return []
    body = roster_match.group("body")
    row_pattern = re.compile(r"<tr[^>]*>(?P<row>.*?)</tr>", re.S | re.I)
    cell_pattern = re.compile(r'<(?:th|td)(?P<attrs>[^>]*)>(?P<value>.*?)</(?:th|td)>', re.S | re.I)

    rows: list[dict[str, object]] = []
    for row_match in row_pattern.finditer(body):
        row_html = row_match.group("row")
        row: dict[str, object] = {}
        for cell_match in cell_pattern.finditer(row_html):
            attrs = cell_match.group("attrs")
            key_match = re.search(r'data-stat="(?P<key>[^"]+)"', attrs)
            if not key_match:
                continue
            key = key_match.group("key")
            value = clean_html(cell_match.group("value"))
            row[key] = value
            csv_match = re.search(r'data-append-csv="(?P<csv>[^"]+)"', attrs)
            csv_value = csv_match.group("csv") if csv_match else None
            if csv_value:
                row[f"{key}_ref"] = csv_value
        if (
            "player" in row
            and isinstance(row["player"], str)
            and row["player"]
            and row["player"] != "Player"
        ):
            rows.append(row)
    return rows


def extract_bref_draft_rows(html: str) -> list[dict[str, object]]:
    draft_match = re.search(r'<table[^>]*id="stats"[^>]*>(?P<body>.*?)</table>', html, re.S | re.I)
    if not draft_match:
        return []
    body = draft_match.group("body")
    row_pattern = re.compile(r"<tr[^>]*>(?P<row>.*?)</tr>", re.S | re.I)
    cell_pattern = re.compile(r'<(?:th|td)(?P<attrs>[^>]*)>(?P<value>.*?)</(?:th|td)>', re.S | re.I)

    rows: list[dict[str, object]] = []
    for row_match in row_pattern.finditer(body):
        row_html = row_match.group("row")
        row: dict[str, object] = {}
        for cell_match in cell_pattern.finditer(row_html):
            attrs = cell_match.group("attrs")
            key_match = re.search(r'data-stat="(?P<key>[^"]+)"', attrs)
            if not key_match:
                continue
            key = key_match.group("key")
            value = clean_html(cell_match.group("value"))
            row[key] = value
            csv_match = re.search(r'data-append-csv="(?P<csv>[^"]+)"', attrs)
            if csv_match:
                row[f"{key}_ref"] = csv_match.group("csv")
        if row.get("player") and row.get("team_id"):
            rows.append(row)
    return rows


def build_bref_draft_rows(
    *,
    draft_year: int,
    team_code: str,
    html: str,
) -> tuple[list[SourceRecordRow], list[SourceEventRow], list[PlayerRow], list[DraftSelectionRow]]:
    draft_rows = extract_bref_draft_rows(html)
    team_code = team_code.upper()
    source_record_id = f"bref:draft:{draft_year}"
    source_record = SourceRecordRow(
        source_record_id=source_record_id,
        source_system="basketball_reference",
        source_type="draft_page",
        source_locator=build_bref_draft_url(draft_year),
        fetched_at=utc_now_iso(),
        raw_payload={
            "draft_year": draft_year,
            "rows": draft_rows,
        },
    )

    source_events: list[SourceEventRow] = []
    players: list[PlayerRow] = []
    selections: list[DraftSelectionRow] = []
    for row in draft_rows:
        if str(row.get("team_id", "")).upper() != team_code:
            continue
        player_name = str(row.get("player", "")).strip()
        if not player_name or player_name == "Player":
            continue
        player_id = f"player:{slugify_name(player_name)}"
        player_ref = str(row.get("player_ref")) if row.get("player_ref") else None
        overall = parse_int(row.get("pick_overall"))
        if overall is None:
            continue
        round_number = parse_int(row.get("round_number")) or infer_draft_round(overall)
        source_event_id = build_bref_draft_source_event_id(draft_year, overall)
        selection_id = f"draft:{draft_year}:{overall}"
        players.append(
            PlayerRow(
                player_id=player_id,
                display_name=player_name,
                nba_player_ref=player_ref,
            )
        )
        source_events.append(
            SourceEventRow(
                source_event_id=source_event_id,
                source_record_id=source_record_id,
                event_date=draft_event_date(draft_year, round_number),
                event_type="draft",
                label=f"Memphis drafts {player_name} at No. {overall}",
                team_scope=team_code,
                source_group_hint=f"draft:{draft_year}",
                normalized_payload={
                    "player_names_in": [player_name],
                    "player_names_out": [],
                    "pick_text_in": [],
                    "pick_text_out": [],
                    "pick_details_in": [],
                    "pick_details_out": [],
                    "draft_selection_id": selection_id,
                    "draft_year": draft_year,
                    "pick_overall": overall,
                    "round_number": round_number,
                    "team_code": team_code,
                    "player_id": player_id,
                    "player_ref": player_ref,
                    "raw_row": row,
                },
            )
        )
        selections.append(
            DraftSelectionRow(
                draft_selection_id=selection_id,
                draft_year=draft_year,
                pick_overall=overall,
                round_number=round_number,
                team_code=team_code,
                player_id=player_id,
                source_event_id=source_event_id,
                notes=f"Basketball-Reference draft row for pick {overall}",
            )
        )
    return [source_record], source_events, players, selections


def build_bref_roster_rows(
    *,
    team_code: str,
    season_end_year: int,
    html: str,
) -> tuple[list[SourceRecordRow], list[PlayerRow], list[RosterBaselinePlayerRow]]:
    roster_rows = extract_bref_roster_rows(html)
    source_record_id = f"bref:{team_code.lower()}:{season_end_year}:roster"
    source_record = SourceRecordRow(
        source_record_id=source_record_id,
        source_system="basketball_reference",
        source_type="team_roster_page",
        source_locator=build_bref_team_season_url(team_code=team_code, season_end_year=season_end_year),
        fetched_at=utc_now_iso(),
        raw_payload={
            "team_code": team_code.upper(),
            "season_end_year": season_end_year,
            "roster_rows": roster_rows,
        },
    )

    players: list[PlayerRow] = []
    baseline_rows: list[RosterBaselinePlayerRow] = []
    season = f"{season_end_year - 1}-{str(season_end_year)[-2:]}"
    for roster_order, row in enumerate(roster_rows, start=1):
        display_name = str(row["player"])
        bbr_ref = str(row.get("player_ref")) if row.get("player_ref") else None
        player_id = f"player:{slugify_name(display_name)}"
        players.append(
            PlayerRow(
                player_id=player_id,
                display_name=display_name,
                nba_player_ref=bbr_ref,
                birth_date=str(row.get("birth_date")) if row.get("birth_date") else None,
                position_text=str(row.get("pos")) if row.get("pos") else None,
            )
        )
        experience_raw = row.get("years_experience")
        years_experience = int(experience_raw) if isinstance(experience_raw, str) and experience_raw.isdigit() else None
        baseline_rows.append(
            RosterBaselinePlayerRow(
                season=season,
                team_code=team_code.upper(),
                player_id=player_id,
                display_name=display_name,
                source_record_id=source_record_id,
                roster_order=roster_order,
                nba_player_ref=bbr_ref,
                birth_date=str(row.get("birth_date")) if row.get("birth_date") else None,
                position_text=str(row.get("pos")) if row.get("pos") else None,
                years_experience=years_experience,
            )
        )

    return [source_record], players, baseline_rows


def preview_bref_roster_baseline(*, team_code: str, season_end_year: int) -> dict[str, object]:
    html = fetch_bref_team_season_html(team_code=team_code, season_end_year=season_end_year)
    source_records, players, baseline_rows = build_bref_roster_rows(
        team_code=team_code,
        season_end_year=season_end_year,
        html=html,
    )
    return {
        "status": "ok",
        "source_records": len(source_records),
        "players": len(players),
        "baseline_rows": len(baseline_rows),
        "first_player": players[0].model_dump(mode="json") if players else None,
        "season_end_year": season_end_year,
        "team_code": team_code.upper(),
    }


def load_bref_roster_baseline(database_url: str, *, team_code: str, season_end_year: int) -> dict[str, object]:
    html = fetch_bref_team_season_html(team_code=team_code, season_end_year=season_end_year)
    source_records, players, baseline_rows = build_bref_roster_rows(
        team_code=team_code,
        season_end_year=season_end_year,
        html=html,
    )
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        insert_source_records(connection, source_records)
        upsert_players(connection, players)
        upsert_roster_baseline_players(connection, baseline_rows)
        connection.commit()
    return {
        "status": "ok",
        "source_records": len(source_records),
        "players": len(players),
        "baseline_rows": len(baseline_rows),
        "season_end_year": season_end_year,
        "team_code": team_code.upper(),
    }


def load_bref_roster_baseline_span(
    database_url: str,
    *,
    team_code: str = DEFAULT_TEAM_CODE,
    start_season_end_year: int = DEFAULT_SEASON_START_YEAR,
    end_season_end_year: int = DEFAULT_SEASON_END_YEAR,
    request_delay: float = 0.8,
) -> dict[str, object]:
    seasons: list[dict[str, object]] = []
    total_source_records = 0
    total_players = 0
    total_baseline_rows = 0
    for season_end_year in range(start_season_end_year, end_season_end_year + 1):
        result = load_bref_roster_baseline(
            database_url,
            team_code=team_code,
            season_end_year=season_end_year,
        )
        seasons.append(result)
        total_source_records += int(result["source_records"])
        total_players += int(result["players"])
        total_baseline_rows += int(result["baseline_rows"])
        time.sleep(request_delay)
    return {
        "status": "ok",
        "team_code": team_code.upper(),
        "start_season_end_year": start_season_end_year,
        "end_season_end_year": end_season_end_year,
        "source_records": total_source_records,
        "players": total_players,
        "baseline_rows": total_baseline_rows,
        "seasons": seasons,
    }


def preview_bref_draft_results(*, draft_year: int, team_code: str) -> dict[str, object]:
    html = fetch_bref_draft_html(draft_year)
    source_records, source_events, players, selections = build_bref_draft_rows(
        draft_year=draft_year,
        team_code=team_code,
        html=html,
    )
    return {
        "status": "ok",
        "source_records": len(source_records),
        "source_events": len(source_events),
        "players": len(players),
        "draft_selections": len(selections),
        "first_selection": selections[0].model_dump(mode="json") if selections else None,
        "first_source_event": source_events[0].model_dump(mode="json") if source_events else None,
        "draft_year": draft_year,
        "team_code": team_code.upper(),
    }


def load_bref_draft_results(database_url: str, *, draft_year: int, team_code: str) -> dict[str, object]:
    html = fetch_bref_draft_html(draft_year)
    source_records, source_events, players, selections = build_bref_draft_rows(
        draft_year=draft_year,
        team_code=team_code,
        html=html,
    )
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        insert_source_records(connection, source_records)
        upsert_players(connection, players)
        replace_source_events_for_records(
            connection,
            source_record_ids=[row.source_record_id for row in source_records],
            rows=source_events,
        )
        insert_source_events(connection, source_events)
        upsert_draft_selections(connection, selections)
        connection.commit()
    return {
        "status": "ok",
        "source_records": len(source_records),
        "source_events": len(source_events),
        "players": len(players),
        "draft_selections": len(selections),
        "draft_year": draft_year,
        "team_code": team_code.upper(),
    }


def load_bref_draft_results_span(
    database_url: str,
    *,
    team_code: str = DEFAULT_TEAM_CODE,
    start_draft_year: int = 2016,
    end_draft_year: int = 2025,
    request_delay: float = 0.8,
) -> dict[str, object]:
    years: list[dict[str, object]] = []
    total_source_records = 0
    total_source_events = 0
    total_players = 0
    total_selections = 0
    for draft_year in range(start_draft_year, end_draft_year + 1):
        result = load_bref_draft_results(database_url, draft_year=draft_year, team_code=team_code)
        years.append(result)
        total_source_records += int(result["source_records"])
        total_source_events += int(result["source_events"])
        total_players += int(result["players"])
        total_selections += int(result["draft_selections"])
        time.sleep(request_delay)
    return {
        "status": "ok",
        "team_code": team_code.upper(),
        "start_draft_year": start_draft_year,
        "end_draft_year": end_draft_year,
        "source_records": total_source_records,
        "source_events": total_source_events,
        "players": total_players,
        "draft_selections": total_selections,
        "years": years,
    }


def read_nba_player_movement_fixture(path: Path = DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_nba_player_movement_json(*, endpoint_url: str = NBA_PLAYER_MOVEMENT_ENDPOINT_URL) -> tuple[object, dict[str, str | None]]:
    request = Request(endpoint_url, headers=NBA_HEADERS)
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
        metadata = {
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }
    return payload, metadata


def extract_nba_player_movement_rows(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, dict) and ("resultSets" in payload or "resultSet" in payload):
        return extract_nba_dataset_rows(payload)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        raise ValueError("Unrecognized NBA.com player movement payload shape")

    for key in (
        "NBA_Player_Movement",
        "rows",
        "transactions",
        "playerMovements",
        "playerMovement",
        "items",
        "data",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            try:
                return extract_nba_player_movement_rows(value)
            except ValueError:
                continue

    raise ValueError("Unrecognized NBA.com player movement payload shape")


def extract_nba_player_movement_row_fields(row: dict[str, object]) -> dict[str, object]:
    event_date = normalize_nba_player_movement_date(
        first_present(
            row,
            (
                "TRANSACTION_DATE",
                "Transaction_Date",
                "TRANSACTION_DATE_EST",
                "TRANSACTION_DT",
                "date",
                "transactionDate",
                "transaction_date",
            ),
        )
    )
    transaction_type = string_or_none(
        first_present(
            row,
            (
                "TRANSACTION_TYPE",
                "Transaction_Type",
                "TRANSACTION_TYPE_DESCRIPTION",
                "TRANSACTION_TYPE_NAME",
                "type",
                "transactionType",
                "transaction_type",
            ),
        )
    )
    transaction_description = string_or_none(
        first_present(
            row,
            (
                "TRANSACTION_DESCRIPTION",
                "Transaction_Description",
                "TRANSACTION_DESC",
                "DESCRIPTION",
                "description",
                "transactionDescription",
                "transaction_description",
            ),
        )
    )
    player_name, player_name_source = resolve_nba_player_movement_player_name(
        description=transaction_description,
        raw_player_name=string_or_none(first_present(row, ("PLAYER_NAME", "PLAYER", "personName", "playerName", "player_name"))),
        player_slug=normalize_identifier_text(first_present(row, ("PLAYER_SLUG", "Player_Slug", "playerSlug", "player_slug"))),
    )
    team_identifiers = compact_mapping(
        {
            "team_id": normalize_identifier_text(first_present(row, ("TEAM_ID", "TeamID", "teamId", "team_id"))),
            "team_slug": string_or_none(first_present(row, ("TEAM_SLUG", "Team_Slug", "teamSlug", "team_slug"))),
            "team_abbreviation": string_or_none(
                first_present(row, ("TEAM_ABBREVIATION", "TEAM_ABBREVIATION_NICKNAME", "teamAbbreviation", "team_abbreviation"))
            ),
            "team_name": string_or_none(first_present(row, ("TEAM_NAME", "Team_Name", "teamName", "team_name"))),
            "from_team_id": normalize_identifier_text(first_present(row, ("FROM_TEAM_ID", "fromTeamId", "from_team_id"))),
            "from_team_abbreviation": string_or_none(
                first_present(row, ("FROM_TEAM_ABBREVIATION", "fromTeamAbbreviation", "from_team_abbreviation"))
            ),
            "to_team_id": normalize_identifier_text(first_present(row, ("TO_TEAM_ID", "toTeamId", "to_team_id"))),
            "to_team_abbreviation": string_or_none(
                first_present(row, ("TO_TEAM_ABBREVIATION", "toTeamAbbreviation", "to_team_abbreviation"))
            ),
        }
    )
    player_identifiers = compact_mapping(
        {
            "player_id": normalize_identifier_text(
                first_present(row, ("PLAYER_ID", "PersonID", "PERSON_ID", "playerId", "player_id")),
                zero_is_none=True,
            ),
            "player_slug": normalize_identifier_text(first_present(row, ("PLAYER_SLUG", "Player_Slug", "playerSlug", "player_slug"))),
            "player_name": player_name,
            "player_name_source": player_name_source,
        }
    )
    return {
        "event_date": event_date,
        "transaction_type": transaction_type,
        "normalized_event_type": normalize_nba_player_movement_transaction_type(transaction_type),
        "transaction_description": transaction_description,
        "team_identifiers": team_identifiers,
        "player_identifiers": player_identifiers,
        "group_sort": normalize_identifier_text(first_present(row, ("GroupSort", "GROUP_SORT", "groupSort", "group_sort"))),
        "additional_sort": normalize_identifier_text(first_present(row, ("Additional_Sort", "ADDITIONAL_SORT", "additionalSort", "additional_sort"))),
    }


def normalize_nba_player_movement_transaction_type(transaction_type: str | None) -> str:
    if not transaction_type:
        return "signing"
    return NBA_PLAYER_MOVEMENT_TRANSACTION_TYPE_MAP.get(transaction_type, "signing")


def is_memphis_nba_player_movement_row(row: dict[str, object]) -> bool:
    fields = extract_nba_player_movement_row_fields(row)
    team_identifiers = fields["team_identifiers"]
    if isinstance(team_identifiers, dict):
        team_id = str(team_identifiers.get("team_id", "")).strip()
        if team_id == NBA_PLAYER_MOVEMENT_MEMPHIS_TEAM_ID:
            return True
        team_slug = str(team_identifiers.get("team_slug", "")).strip().lower()
        if team_slug == NBA_PLAYER_MOVEMENT_MEMPHIS_TEAM_SLUG:
            return True
    description = str(fields.get("transaction_description") or "").lower()
    return "memphis" in description or "grizzlies" in description


def resolve_nba_player_movement_player_name(
    *,
    description: str | None,
    raw_player_name: str | None,
    player_slug: str | None,
) -> tuple[str | None, str | None]:
    if raw_player_name:
        return raw_player_name, "payload"
    description_name = extract_nba_player_movement_player_name_from_description(description)
    if description_name:
        return description_name, "description"
    if player_slug:
        return humanize_nba_player_movement_slug(player_slug), "slug"
    return None, None


def extract_nba_player_movement_player_name_from_description(description: str | None) -> str | None:
    if not description:
        return None
    text = collapse_spaces(description)
    patterns = (
        r"\bconverted the contract of\s+(?P<subject>.+?)\s+to\b",
        r"\b(?:received|acquired)\s+(?P<subject>.+?)\s+from\b",
        r"\b(?:signed|re-signed|waived)\s+(?P<subject>.+?)\s+to\b",
        r"\b(?:claimed|awarded)\s+(?P<subject>.+?)\s+off waivers\b",
        r"\b(?:signed|re-signed|waived)\s+(?P<subject>.+?)\.?$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        name = clean_nba_player_movement_subject_phrase(match.group("subject"))
        if name:
            return name
    return None


def clean_nba_player_movement_subject_phrase(value: str) -> str | None:
    subject = collapse_spaces(value).strip()
    if not subject:
        return None
    if subject.endswith(".") and not re.search(r"\b(?:Jr|Sr)\.$", subject):
        subject = subject[:-1].rstrip()
    subject = re.sub(r"^(?:the\s+)?contract of\s+", "", subject, flags=re.IGNORECASE)
    subject = re.sub(r"^(?:the\s+)?draft rights to\s+", "", subject, flags=re.IGNORECASE)
    subject = re.sub(r"^(?:the\s+)?rights to\s+", "", subject, flags=re.IGNORECASE)
    position_prefix = (
        r"^(?:two-way\s+|rest-of-season\s+)?"
        r"(?:point guard|shooting guard|small forward|power forward|"
        r"guard/forward|forward/guard|forward/center|center/forward|"
        r"guard/center|center/guard|guard-forward|forward-guard|"
        r"forward-center|center-forward|guard-center|center-guard|"
        r"guard|forward|center|wing)\s+"
    )
    while True:
        stripped = re.sub(position_prefix, "", subject, flags=re.IGNORECASE)
        if stripped == subject:
            break
        subject = stripped.strip()
    lowered = subject.lower()
    if lowered.startswith(("to ", "for ")):
        return None
    if lowered.startswith(
        (
            "draft consideration",
            "cash consideration",
            "cash considerations",
            "future considerations",
            "trade exception",
            "future first round draft pick",
            "future second round draft pick",
            "first round draft pick",
            "second round draft pick",
            "pick swap",
        )
    ):
        return None
    return subject or None


def humanize_nba_player_movement_slug(value: str) -> str:
    pieces = [piece for piece in value.split("-") if piece]
    rendered: list[str] = []
    suffix_map = {
        "jr": "Jr.",
        "sr": "Sr.",
        "ii": "II",
        "iii": "III",
        "iv": "IV",
        "v": "V",
    }
    for piece in pieces:
        lowered = piece.lower()
        if lowered in suffix_map:
            rendered.append(suffix_map[lowered])
        elif piece.isalpha() and len(piece) <= 2:
            rendered.append(piece.upper())
        else:
            rendered.append(piece.capitalize())
    return " ".join(rendered)


def infer_nba_player_movement_player_direction(
    *,
    normalized_event_type: str,
    description: str | None,
    team_identifiers: dict[str, str],
) -> str | None:
    if normalized_event_type in {"signing", "conversion"}:
        return "in"
    if normalized_event_type == "waiver":
        return "out"
    if normalized_event_type != "trade":
        return None

    text = collapse_spaces(description or "")
    if re.search(r"\bfrom\s+(?:the\s+)?memphis grizzlies\b", text, re.IGNORECASE):
        return "out"
    if re.search(r"\bto\s+(?:the\s+)?memphis grizzlies\b", text, re.IGNORECASE):
        return "in"
    if re.search(r"^(?:the\s+)?memphis grizzlies\s+(?:received|acquired)\b", text, re.IGNORECASE):
        return "in"
    if re.search(r"^(?:the\s+)?memphis grizzlies\s+(?:traded|sent)\b", text, re.IGNORECASE):
        return "out"

    if team_identifiers.get("from_team_id") == NBA_PLAYER_MOVEMENT_MEMPHIS_TEAM_ID:
        return "out"
    if team_identifiers.get("to_team_id") == NBA_PLAYER_MOVEMENT_MEMPHIS_TEAM_ID:
        return "in"
    if team_identifiers.get("team_id") == NBA_PLAYER_MOVEMENT_MEMPHIS_TEAM_ID:
        return "in"
    if team_identifiers.get("team_slug", "").lower() == NBA_PLAYER_MOVEMENT_MEMPHIS_TEAM_SLUG:
        return "in"
    return None


def build_nba_player_movement_preview_rows(
    payload: object,
    *,
    source_locator: str,
) -> list[dict[str, object]]:
    rows = extract_nba_player_movement_rows(payload)
    preview_rows: list[dict[str, object]] = []
    for row_index, row in enumerate(rows, start=1):
        if not is_memphis_nba_player_movement_row(row):
            continue
        fields = extract_nba_player_movement_row_fields(row)
        event_date = fields["event_date"]
        transaction_type = fields["transaction_type"]
        transaction_description = fields["transaction_description"]
        team_identifiers = fields["team_identifiers"]
        player_identifiers = fields["player_identifiers"]
        player_direction = infer_nba_player_movement_player_direction(
            normalized_event_type=str(fields["normalized_event_type"]),
            description=transaction_description,
            team_identifiers=team_identifiers,
        )
        normalized_payload = {
            "event_date": event_date,
            "transaction_type": transaction_type,
            "normalized_event_type": fields["normalized_event_type"],
            "transaction_description": transaction_description,
            "team_identifiers": team_identifiers,
            "player_identifiers": player_identifiers,
            "player_direction": player_direction,
            "group_sort": fields["group_sort"],
            "additional_sort": fields["additional_sort"],
            "raw_row": row,
        }
        preview_rows.append(
            {
                "date": event_date,
                "transaction_type": transaction_type,
                "transaction_description": transaction_description,
                "team_identifiers": team_identifiers,
                "player_identifiers": player_identifiers,
                "source_locator": f"{source_locator}#row={row_index}",
                "normalized_payload": normalized_payload,
                "source_system": NBA_PLAYER_MOVEMENT_SOURCE_SYSTEM,
                "source_system_label": NBA_PLAYER_MOVEMENT_SOURCE_SYSTEM,
            }
        )
    return preview_rows


def preview_nba_player_movement(
    *,
    fixture_path: Path = DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH,
    live: bool = False,
    endpoint_url: str = NBA_PLAYER_MOVEMENT_ENDPOINT_URL,
) -> dict[str, object]:
    endpoint_metadata: dict[str, str | None] = {}
    if live:
        payload, endpoint_metadata = fetch_nba_player_movement_json(endpoint_url=endpoint_url)
        source_locator = endpoint_url
    else:
        payload = read_nba_player_movement_fixture(fixture_path)
        source_locator = str(fixture_path)
    endpoint_rows = extract_nba_player_movement_rows(payload)
    preview_rows = build_nba_player_movement_preview_rows(payload, source_locator=source_locator)
    dates = sorted(row["date"] for row in preview_rows if isinstance(row.get("date"), str))
    type_counts: dict[str, int] = {}
    for row in preview_rows:
        transaction_type = str(row.get("transaction_type") or "unknown")
        type_counts[transaction_type] = type_counts.get(transaction_type, 0) + 1
    return {
        "status": "ok",
        "source_system": NBA_PLAYER_MOVEMENT_SOURCE_SYSTEM,
        "source_type": NBA_PLAYER_MOVEMENT_SOURCE_TYPE,
        "source_locator": source_locator,
        "endpoint_url": endpoint_url,
        "endpoint_metadata": endpoint_metadata,
        "total_endpoint_rows": len(endpoint_rows),
        "memphis_row_count": len(preview_rows),
        "date_range": {
            "start_date": dates[0] if dates else None,
            "end_date": dates[-1] if dates else None,
        },
        "transaction_type_counts": dict(sorted(type_counts.items())),
        "preview_rows": preview_rows,
        "row_count": len(preview_rows),
        "fixture_only": not live,
        "writes_to_database": False,
    }


def build_nba_player_movement_source_rows(
    payload: object,
    *,
    source_locator: str,
    endpoint_url: str = NBA_PLAYER_MOVEMENT_ENDPOINT_URL,
    endpoint_metadata: dict[str, str | None] | None = None,
    fetched_at: str | None = None,
) -> tuple[list[SourceRecordRow], list[SourceEventRow]]:
    endpoint_rows = extract_nba_player_movement_rows(payload)
    memphis_rows = [
        (row_index, row)
        for row_index, row in enumerate(endpoint_rows, start=1)
        if is_memphis_nba_player_movement_row(row)
    ]
    fetched_at = fetched_at or utc_now_iso()
    preview_rows = build_nba_player_movement_preview_rows(payload, source_locator=source_locator)
    dates = sorted(row["date"] for row in preview_rows if isinstance(row.get("date"), str))
    type_counts: dict[str, int] = {}
    for row in preview_rows:
        transaction_type = str(row.get("transaction_type") or "unknown")
        type_counts[transaction_type] = type_counts.get(transaction_type, 0) + 1

    source_record = SourceRecordRow(
        source_record_id="nba_player_movement:memphis",
        source_system=NBA_PLAYER_MOVEMENT_SOURCE_SYSTEM,
        source_type=NBA_PLAYER_MOVEMENT_SOURCE_TYPE,
        source_locator=source_locator,
        fetched_at=fetched_at,
        raw_payload={
            "endpoint_url": endpoint_url,
            "endpoint_metadata": endpoint_metadata or {},
            "source_locator": source_locator,
            "filter": {
                "team_id": NBA_PLAYER_MOVEMENT_MEMPHIS_TEAM_ID,
                "team_slug": NBA_PLAYER_MOVEMENT_MEMPHIS_TEAM_SLUG,
                "text_fallback": ["memphis", "grizzlies"],
            },
            "total_endpoint_rows": len(endpoint_rows),
            "memphis_row_count": len(memphis_rows),
            "date_range": {
                "start_date": dates[0] if dates else None,
                "end_date": dates[-1] if dates else None,
            },
            "transaction_type_counts": dict(sorted(type_counts.items())),
            "rows": [row for _row_index, row in memphis_rows],
        },
    )

    source_events: list[SourceEventRow] = []
    for row_index, row in memphis_rows:
        fields = extract_nba_player_movement_row_fields(row)
        event_date = fields["event_date"]
        transaction_type = fields["transaction_type"]
        normalized_event_type = str(fields["normalized_event_type"])
        description = string_or_none(fields["transaction_description"]) or "NBA.com player movement row"
        row_digest = stable_digest(
            {
                "event_date": event_date,
                "transaction_type": transaction_type,
                "description": description,
                "team_identifiers": fields["team_identifiers"],
                "player_identifiers": fields["player_identifiers"],
                "group_sort": fields["group_sort"],
                "additional_sort": fields["additional_sort"],
            }
        )
        source_group_hint = None
        if fields["group_sort"]:
            source_group_hint = f"nba_player_movement:group:{fields['group_sort']}"
        player_identifiers = fields["player_identifiers"]
        player_names: list[str] = []
        if isinstance(player_identifiers, dict) and isinstance(player_identifiers.get("player_name"), str):
            player_names = [str(player_identifiers["player_name"])]
        player_direction = infer_nba_player_movement_player_direction(
            normalized_event_type=normalized_event_type,
            description=description,
            team_identifiers=fields["team_identifiers"],
        )
        source_events.append(
            SourceEventRow(
                source_event_id=f"nba_player_movement:{row_digest}",
                source_record_id=source_record.source_record_id,
                event_date=str(event_date) if event_date else "1900-01-01",
                event_type=normalized_event_type,
                label=description,
                team_scope="MEM",
                source_group_hint=source_group_hint,
                normalized_payload={
                    "corroboration_only": True,
                    "canonical_exclusion_reason": NBA_PLAYER_MOVEMENT_CANONICAL_EXCLUSION_REASON,
                    "normalization_note": NBA_PLAYER_MOVEMENT_NORMALIZATION_NOTE,
                    "raw_transaction_type": transaction_type,
                    "normalized_event_type": normalized_event_type,
                    "transaction_description": description,
                    "player_direction": player_direction,
                    "player_names_in": player_names if player_direction == "in" else [],
                    "player_names_out": player_names if player_direction == "out" else [],
                    "pick_text_in": [],
                    "pick_text_out": [],
                    "pick_details_in": [],
                    "pick_details_out": [],
                    "group_sort": fields["group_sort"],
                    "additional_sort": fields["additional_sort"],
                    "team_identifiers": fields["team_identifiers"],
                    "player_identifiers": fields["player_identifiers"],
                    "raw_row": row,
                },
            )
        )
    return [source_record], source_events


def preview_nba_player_movement_source_rows(
    *,
    fixture_path: Path = DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH,
    live: bool = False,
    endpoint_url: str = NBA_PLAYER_MOVEMENT_ENDPOINT_URL,
) -> dict[str, object]:
    endpoint_metadata: dict[str, str | None] = {}
    if live:
        payload, endpoint_metadata = fetch_nba_player_movement_json(endpoint_url=endpoint_url)
        source_locator = endpoint_url
    else:
        payload = read_nba_player_movement_fixture(fixture_path)
        source_locator = str(fixture_path)
    source_records, source_events = build_nba_player_movement_source_rows(
        payload,
        source_locator=source_locator,
        endpoint_url=endpoint_url,
        endpoint_metadata=endpoint_metadata,
    )
    return {
        "status": "ok",
        "source_system": NBA_PLAYER_MOVEMENT_SOURCE_SYSTEM,
        "source_type": NBA_PLAYER_MOVEMENT_SOURCE_TYPE,
        "source_locator": source_locator,
        "writes_to_database": False,
        "source_records": len(source_records),
        "source_events": len(source_events),
        "source_record_ids": [row.source_record_id for row in source_records],
        "source_event_ids": [row.source_event_id for row in source_events],
        "first_source_record": source_records[0].model_dump(mode="json") if source_records else None,
        "first_source_event": source_events[0].model_dump(mode="json") if source_events else None,
    }


def load_nba_player_movement(
    database_url: str | None = None,
    *,
    fixture_path: Path = DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH,
    live: bool = False,
    endpoint_url: str = NBA_PLAYER_MOVEMENT_ENDPOINT_URL,
    dry_run: bool = True,
    execute: bool = False,
) -> dict[str, object]:
    if dry_run and execute:
        raise ValueError("Choose either dry-run mode or --execute, not both.")
    if not execute:
        return {
            **preview_nba_player_movement_source_rows(
                fixture_path=fixture_path,
                live=live,
                endpoint_url=endpoint_url,
            ),
            "dry_run": True,
            "writes_to_database": False,
        }
    if not database_url:
        raise ValueError("database_url is required when execute=True")

    endpoint_metadata: dict[str, str | None] = {}
    if live:
        payload, endpoint_metadata = fetch_nba_player_movement_json(endpoint_url=endpoint_url)
        source_locator = endpoint_url
    else:
        payload = read_nba_player_movement_fixture(fixture_path)
        source_locator = str(fixture_path)
    source_records, source_events = build_nba_player_movement_source_rows(
        payload,
        source_locator=source_locator,
        endpoint_url=endpoint_url,
        endpoint_metadata=endpoint_metadata,
    )
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        insert_source_records(connection, source_records)
        replace_source_events_for_record(
            connection,
            source_record_id=source_records[0].source_record_id,
            rows=source_events,
        )
        insert_source_events(connection, source_events)
        connection.commit()
    return {
        "status": "ok",
        "source_system": NBA_PLAYER_MOVEMENT_SOURCE_SYSTEM,
        "source_type": NBA_PLAYER_MOVEMENT_SOURCE_TYPE,
        "source_locator": source_locator,
        "dry_run": False,
        "writes_to_database": True,
        "source_records": len(source_records),
        "source_events": len(source_events),
        "source_record_ids": [row.source_record_id for row in source_records],
        "source_event_ids": [row.source_event_id for row in source_events],
    }


def read_official_release_fixture(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"articles": payload}
    if not isinstance(payload, dict):
        raise ValueError("Official release fixture must be a JSON object or array.")
    return payload


def build_official_release_fixture_bundle(
    fixture_path: Path,
    *,
    fixture_fragment_dir: Path | None = None,
) -> dict[str, object]:
    article_entries: list[dict[str, object]] = []
    explicit_source_event_ids: set[str] = set()
    source_record_ids: set[str] = set()

    def append_fixture_articles(path: Path) -> None:
        payload = read_official_release_fixture(path)
        raw_articles = payload.get("articles", [])
        if not isinstance(raw_articles, list):
            raise ValueError(f"Official release fixture {path} must contain an 'articles' list.")
        for article_index, article in enumerate(raw_articles, start=1):
            if not isinstance(article, dict):
                raise ValueError(f"Official release fixture {path} article {article_index} must be an object.")
            source_record_id = string_or_none(article.get("source_record_id"))
            if not source_record_id:
                raise ValueError(f"Official release fixture {path} article {article_index} is missing source_record_id.")
            if source_record_id in source_record_ids:
                raise ValueError(f"Duplicate official release source_record_id across aggregate bundle: {source_record_id}")
            source_record_ids.add(source_record_id)

            cloned_article = dict(article)
            cloned_article["_fixture_base_path"] = str(path.parent)
            event_entries = cloned_article.get("events", [])
            if not isinstance(event_entries, list):
                raise ValueError(f"Official release fixture {path} article {source_record_id} must contain an events list.")
            for event_index, event in enumerate(event_entries, start=1):
                if not isinstance(event, dict):
                    raise ValueError(
                        f"Official release fixture {path} article {source_record_id} event {event_index} must be an object."
                    )
                source_event_id = string_or_none(event.get("source_event_id"))
                if source_event_id:
                    if source_event_id in explicit_source_event_ids:
                        raise ValueError(
                            "Duplicate official release explicit source_event_id across aggregate bundle: "
                            f"{source_event_id}"
                        )
                    explicit_source_event_ids.add(source_event_id)
            article_entries.append(cloned_article)

    append_fixture_articles(fixture_path)

    if fixture_fragment_dir and fixture_fragment_dir.exists():
        for fragment_path in sorted(path for path in fixture_fragment_dir.glob("*.json") if path.is_file()):
            append_fixture_articles(fragment_path)
    return {"articles": article_entries}


def extract_official_article_metadata(html: str) -> dict[str, str | None]:
    title_match = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](?P<value>.*?)["\']',
        html,
        re.I | re.S,
    )
    if title_match is None:
        title_match = re.search(r"<title>(?P<value>.*?)</title>", html, re.I | re.S)
    description_match = re.search(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](?P<value>.*?)["\']',
        html,
        re.I | re.S,
    )
    published_match = re.search(r'"datePublished"\s*:\s*"(?P<value>[^"]+)"', html, re.I)
    modified_match = re.search(r'"dateModified"\s*:\s*"(?P<value>[^"]+)"', html, re.I)
    article_match = re.search(r"<article[^>]*>(?P<value>.*?)</article>", html, re.I | re.S)
    article_text = clean_html(article_match.group("value")) if article_match else clean_html(html)
    return {
        "title": clean_html(title_match.group("value")) if title_match else None,
        "description": clean_html(description_match.group("value")) if description_match else None,
        "published_at": published_match.group("value") if published_match else None,
        "modified_at": modified_match.group("value") if modified_match else None,
        "article_text_excerpt": article_text[:5000] if article_text else None,
        "html_sha1": hashlib.sha1(html.encode("utf-8")).hexdigest(),
    }


def fetch_official_article_metadata(*, source_locator: str) -> dict[str, str | None]:
    html = fetch_text(source_locator, headers=OFFICIAL_ARTICLE_HEADERS)
    return extract_official_article_metadata(html)


def build_official_release_source_rows(
    payload: dict[str, object],
    *,
    fixture_base_path: Path | None = None,
    fetch_live: bool = False,
    fetched_at: str | None = None,
) -> tuple[list[SourceRecordRow], list[SourceEventRow]]:
    article_entries = payload.get("articles", [])
    if not isinstance(article_entries, list):
        raise ValueError("Official release fixture must contain an 'articles' list.")

    fetched_at = fetched_at or utc_now_iso()
    source_records: list[SourceRecordRow] = []
    source_events: list[SourceEventRow] = []
    fixture_base_path = fixture_base_path or Path.cwd()

    for article_index, article in enumerate(article_entries, start=1):
        if not isinstance(article, dict):
            raise ValueError("Each official release article entry must be an object.")
        source_record_id = string_or_none(article.get("source_record_id"))
        source_system = string_or_none(article.get("source_system"))
        source_type = string_or_none(article.get("source_type"))
        source_locator = string_or_none(article.get("source_locator"))
        if not source_record_id:
            raise ValueError(f"Official release article entry {article_index} is missing source_record_id.")
        if source_system not in OFFICIAL_RELEASE_SOURCE_SYSTEMS:
            raise ValueError(f"Unsupported official release source_system for {source_record_id}: {source_system}")
        if source_type not in OFFICIAL_RELEASE_SOURCE_TYPES:
            raise ValueError(f"Unsupported official release source_type for {source_record_id}: {source_type}")
        if not source_locator:
            raise ValueError(f"Official release article entry {source_record_id} is missing source_locator.")

        article_metadata: dict[str, str | None] = {
            "title": string_or_none(article.get("source_title")),
            "description": string_or_none(article.get("source_description")),
            "published_at": string_or_none(article.get("source_published_at")),
            "modified_at": string_or_none(article.get("source_modified_at")),
            "article_text_excerpt": string_or_none(article.get("source_excerpt")),
            "html_sha1": None,
        }
        fixture_html_path = string_or_none(article.get("html_fixture_path"))
        article_fixture_base_path_value = string_or_none(article.get("_fixture_base_path"))
        article_fixture_base_path = (
            Path(article_fixture_base_path_value)
            if article_fixture_base_path_value
            else (fixture_base_path or Path.cwd())
        )
        fetch_mode = "fixture_metadata"
        if fetch_live:
            article_metadata = fetch_official_article_metadata(source_locator=source_locator)
            fetch_mode = "live_html"
        elif fixture_html_path:
            html_path = (article_fixture_base_path / fixture_html_path).resolve()
            article_metadata = extract_official_article_metadata(html_path.read_text(encoding="utf-8"))
            fetch_mode = "fixture_html"

        event_entries = article.get("events", [])
        if not isinstance(event_entries, list):
            raise ValueError(f"Official release article entry {source_record_id} must contain an events list.")

        source_records.append(
            SourceRecordRow(
                source_record_id=source_record_id,
                source_system=source_system,
                source_type=source_type,
                source_locator=source_locator,
                fetched_at=fetched_at,
                raw_payload={
                    "source_locator": source_locator,
                    "source_title": article_metadata.get("title") or string_or_none(article.get("source_title")),
                    "source_description": article_metadata.get("description")
                    or string_or_none(article.get("source_description")),
                    "source_published_at": article_metadata.get("published_at")
                    or string_or_none(article.get("source_published_at")),
                    "source_modified_at": article_metadata.get("modified_at")
                    or string_or_none(article.get("source_modified_at")),
                    "article_text_excerpt": article_metadata.get("article_text_excerpt")
                    or string_or_none(article.get("source_excerpt")),
                    "html_sha1": article_metadata.get("html_sha1"),
                    "fetch_mode": fetch_mode,
                    "events": event_entries,
                },
            )
        )

        for event_index, event in enumerate(event_entries, start=1):
            if not isinstance(event, dict):
                raise ValueError(f"Official release event {event_index} for {source_record_id} must be an object.")
            event_date = string_or_none(event.get("event_date"))
            event_type = string_or_none(event.get("event_type"))
            if not event_date or not event_type:
                raise ValueError(
                    f"Official release event {event_index} for {source_record_id} must include event_date and event_type."
                )
            label = string_or_none(event.get("label")) or string_or_none(article.get("source_title")) or source_record_id
            source_event_id = string_or_none(event.get("source_event_id")) or (
                f"{source_record_id}:event:{stable_digest({'event_date': event_date, 'event_type': event_type, 'index': event_index})}"
            )
            pick_details_in = event.get("pick_details_in", [])
            pick_details_out = event.get("pick_details_out", [])
            if not isinstance(pick_details_in, list) or not isinstance(pick_details_out, list):
                raise ValueError(f"Official release event {source_event_id} pick detail fields must be lists.")
            source_events.append(
                SourceEventRow(
                    source_event_id=source_event_id,
                    source_record_id=source_record_id,
                    event_date=event_date,
                    event_type=event_type,
                    label=label,
                    team_scope=string_or_none(event.get("team_scope")) or "MEM",
                    source_group_hint=string_or_none(event.get("source_group_hint")),
                    normalized_payload={
                        "corroboration_only": True,
                        "canonical_exclusion_reason": OFFICIAL_RELEASE_CANONICAL_EXCLUSION_REASON,
                        "normalization_note": OFFICIAL_RELEASE_NORMALIZATION_NOTE,
                        "source_system": source_system,
                        "source_type": source_type,
                        "source_title": article_metadata.get("title")
                        or string_or_none(article.get("source_title")),
                        "source_locator": source_locator,
                        "source_published_at": article_metadata.get("published_at")
                        or string_or_none(article.get("source_published_at")),
                        "player_names_in": list(event.get("player_names_in", [])),
                        "player_names_out": list(event.get("player_names_out", [])),
                        "pick_text_in": list(event.get("pick_text_in", [])),
                        "pick_text_out": list(event.get("pick_text_out", [])),
                        "pick_details_in": pick_details_in,
                        "pick_details_out": pick_details_out,
                        "raw_note": string_or_none(event.get("raw_note"))
                        or article_metadata.get("article_text_excerpt")
                        or string_or_none(article.get("source_excerpt"))
                        or label,
                    },
                )
            )

    return source_records, source_events


def preview_official_release_sources(
    *,
    fixture_path: Path = DEFAULT_OFFICIAL_RELEASE_FIXTURE_PATH,
    fixture_fragment_dir: Path | None = None,
    fetch_live: bool = False,
) -> dict[str, object]:
    payload = build_official_release_fixture_bundle(
        fixture_path,
        fixture_fragment_dir=fixture_fragment_dir,
    )
    source_records, source_events = build_official_release_source_rows(
        payload,
        fixture_base_path=fixture_path.parent,
        fetch_live=fetch_live,
    )
    return {
        "status": "ok",
        "source_systems": sorted({row.source_system for row in source_records}),
        "writes_to_database": False,
        "fixture_path": str(fixture_path),
        "fixture_fragment_dir": str(fixture_fragment_dir) if fixture_fragment_dir else None,
        "fetch_live": fetch_live,
        "source_records": len(source_records),
        "source_events": len(source_events),
        "source_record_ids": [row.source_record_id for row in source_records],
        "source_event_ids": [row.source_event_id for row in source_events],
        "first_source_record": source_records[0].model_dump(mode="json") if source_records else None,
        "first_source_event": source_events[0].model_dump(mode="json") if source_events else None,
    }


def load_official_release_sources(
    database_url: str | None = None,
    *,
    fixture_path: Path = DEFAULT_OFFICIAL_RELEASE_FIXTURE_PATH,
    fixture_fragment_dir: Path | None = None,
    fetch_live: bool = False,
    dry_run: bool = True,
    execute: bool = False,
) -> dict[str, object]:
    if dry_run and execute:
        raise ValueError("Choose either dry-run mode or --execute, not both.")
    if not execute:
        return {
            **preview_official_release_sources(
                fixture_path=fixture_path,
                fixture_fragment_dir=fixture_fragment_dir,
                fetch_live=fetch_live,
            ),
            "dry_run": True,
            "writes_to_database": False,
        }
    if not database_url:
        raise ValueError("database_url is required when execute=True")

    payload = build_official_release_fixture_bundle(
        fixture_path,
        fixture_fragment_dir=fixture_fragment_dir,
    )
    source_records, source_events = build_official_release_source_rows(
        payload,
        fixture_base_path=fixture_path.parent,
        fetch_live=fetch_live,
    )
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        insert_source_records(connection, source_records)
        replace_source_events_for_records(
            connection,
            source_record_ids=[row.source_record_id for row in source_records],
            rows=source_events,
        )
        insert_source_events(connection, source_events)
        connection.commit()
    return {
        "status": "ok",
        "dry_run": False,
        "writes_to_database": True,
        "fixture_path": str(fixture_path),
        "fixture_fragment_dir": str(fixture_fragment_dir) if fixture_fragment_dir else None,
        "fetch_live": fetch_live,
        "source_records": len(source_records),
        "source_events": len(source_events),
        "source_record_ids": [row.source_record_id for row in source_records],
        "source_event_ids": [row.source_event_id for row in source_events],
    }


def replace_source_events_for_record(
    connection: psycopg.Connection,
    *,
    source_record_id: str,
    rows: list[SourceEventRow],
) -> None:
    source_event_ids = [row.source_event_id for row in rows]
    with connection.cursor() as cursor:
        if source_event_ids:
            cursor.execute(
                """
                delete from foundation.source_event
                where source_record_id = %s
                  and not (source_event_id = any(%s))
                """,
                (source_record_id, source_event_ids),
            )
            return
        cursor.execute(
            """
            delete from foundation.source_event
            where source_record_id = %s
            """,
            (source_record_id,),
        )


def replace_source_events_for_records(
    connection: psycopg.Connection,
    *,
    source_record_ids: list[str],
    rows: list[SourceEventRow],
) -> None:
    rows_by_record_id: dict[str, list[SourceEventRow]] = {}
    for row in rows:
        rows_by_record_id.setdefault(row.source_record_id, []).append(row)
    for source_record_id in source_record_ids:
        replace_source_events_for_record(
            connection,
            source_record_id=source_record_id,
            rows=rows_by_record_id.get(source_record_id, []),
        )


def load_nba_reference(database_url: str, *, season: str, team_id: int) -> dict[str, object]:
    all_players_payload = fetch_nba_stats_json(
        "commonallplayers",
        {"IsOnlyCurrentSeason": 0, "LeagueID": "00", "Season": season},
    )
    roster_payload = fetch_nba_stats_json(
        "commonteamroster",
        {"LeagueID": "00", "Season": season, "TeamID": team_id},
    )

    all_players_rows = extract_nba_dataset_rows(all_players_payload)
    roster_rows = extract_nba_dataset_rows(roster_payload)

    source_records = [
        SourceRecordRow(
            source_record_id=f"nba_stats:common_all_players:{season}",
            source_system="nba_stats",
            source_type="common_all_players",
            source_locator=f"stats/commonallplayers?Season={season}",
            fetched_at=utc_now_iso(),
            raw_payload=all_players_payload,
        ),
        SourceRecordRow(
            source_record_id=f"nba_stats:common_team_roster:{season}:{team_id}",
            source_system="nba_stats",
            source_type="common_team_roster",
            source_locator=f"stats/commonteamroster?Season={season}&TeamID={team_id}",
            fetched_at=utc_now_iso(),
            raw_payload=roster_payload,
        ),
    ]

    players = build_players_from_nba_reference(all_players_rows=all_players_rows, roster_rows=roster_rows)
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        insert_source_records(connection, source_records)
        upsert_players(connection, players)
        connection.commit()
    return {
        "status": "ok",
        "source_records": len(source_records),
        "players": len(players),
        "season": season,
        "team_id": team_id,
    }


def preview_nba_reference(*, season: str, team_id: int) -> dict[str, object]:
    all_players_payload = fetch_nba_stats_json(
        "commonallplayers",
        {"IsOnlyCurrentSeason": 0, "LeagueID": "00", "Season": season},
    )
    roster_payload = fetch_nba_stats_json(
        "commonteamroster",
        {"LeagueID": "00", "Season": season, "TeamID": team_id},
    )
    all_players_rows = extract_nba_dataset_rows(all_players_payload)
    roster_rows = extract_nba_dataset_rows(roster_payload)
    players = build_players_from_nba_reference(all_players_rows=all_players_rows, roster_rows=roster_rows)
    return {
        "status": "ok",
        "all_players_rows": len(all_players_rows),
        "roster_rows": len(roster_rows),
        "players": len(players),
        "first_player": players[0].model_dump(mode="json") if players else None,
        "season": season,
        "team_id": team_id,
    }


def build_players_from_nba_reference(
    *,
    all_players_rows: list[dict[str, object]],
    roster_rows: list[dict[str, object]],
) -> list[PlayerRow]:
    by_id: dict[str, PlayerRow] = {}
    roster_ids = {f"nba:{row['PLAYER_ID']}" for row in roster_rows if row.get("PLAYER_ID")}

    for row in all_players_rows:
        normalized = normalize_common_all_players_row(row)
        if normalized.player_id in roster_ids:
            by_id[normalized.player_id] = PlayerRow(
                player_id=normalized.player_id,
                display_name=normalized.display_name,
                nba_player_ref=normalized.nba_player_ref,
            )

    for row in roster_rows:
        normalized = normalize_common_team_roster_row(row)
        existing = by_id.get(normalized.player_id)
        by_id[normalized.player_id] = PlayerRow(
            player_id=normalized.player_id,
            display_name=normalized.display_name,
            nba_player_ref=existing.nba_player_ref if existing else str(row.get("PLAYER_ID")),
            birth_date=normalized.birth_date,
            position_text=normalized.position_text,
        )
    return sorted(by_id.values(), key=lambda item: item.player_id)


def insert_source_records(connection: psycopg.Connection, rows: list[SourceRecordRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.source_record (
                    source_record_id, source_system, source_type, source_locator, fetched_at, raw_payload
                ) values (%s, %s, %s, %s, %s, %s::jsonb)
                on conflict (source_record_id) do update
                set source_system = excluded.source_system,
                    source_type = excluded.source_type,
                    source_locator = excluded.source_locator,
                    fetched_at = excluded.fetched_at,
                    raw_payload = excluded.raw_payload
                """,
                (
                    row.source_record_id,
                    row.source_system,
                    row.source_type,
                    row.source_locator,
                    row.fetched_at,
                    json.dumps(row.raw_payload),
                ),
            )


def insert_source_events(connection: psycopg.Connection, rows: list[SourceEventRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.source_event (
                    source_event_id, source_record_id, event_date, event_type, label, team_scope, source_group_hint, normalized_payload
                ) values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                on conflict (source_event_id) do update
                set source_record_id = excluded.source_record_id,
                    event_date = excluded.event_date,
                    event_type = excluded.event_type,
                    label = excluded.label,
                    team_scope = excluded.team_scope,
                    source_group_hint = excluded.source_group_hint,
                    normalized_payload = excluded.normalized_payload
                """,
                (
                    row.source_event_id,
                    row.source_record_id,
                    row.event_date,
                    row.event_type,
                    row.label,
                    row.team_scope,
                    row.source_group_hint,
                    json.dumps(row.normalized_payload),
                ),
            )


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


def slugify_name(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return normalized


def fetch_text(url: str, headers: dict[str, str], timeout: int = 20, retries: int = 3, retry_delay: float = 1.0) -> str:
    request = Request(url, headers=headers)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", "ignore")
        except (URLError, TimeoutError, socket_timeout) as exc:
            last_error = exc
            if attempt == retries:
                raise
            time.sleep(retry_delay * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("fetch_text exhausted retries without a recorded error")


def fetch_nba_stats_json(
    endpoint: str,
    params: dict[str, object],
    *,
    timeout: int = 20,
    retries: int = 4,
    retry_delay: float = 1.5,
) -> dict[str, object]:
    query = urlencode(params)
    url = f"https://stats.nba.com/stats/{endpoint}?{query}"
    request = Request(url, headers=NBA_HEADERS)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError:
            raise
        except (URLError, TimeoutError, socket_timeout) as exc:
            last_error = exc
            if attempt == retries:
                raise
            time.sleep(retry_delay * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("fetch_nba_stats_json exhausted retries without a recorded error")


def extract_nba_dataset_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    result_sets = payload.get("resultSets")
    if isinstance(result_sets, list) and result_sets:
        result = result_sets[0]
        headers = result["headers"]
        return [dict(zip(headers, row)) for row in result["rowSet"]]
    result_set = payload.get("resultSet")
    if isinstance(result_set, dict):
        headers = result_set["headers"]
        return [dict(zip(headers, row)) for row in result_set["rowSet"]]
    raise ValueError("Unrecognized NBA stats payload shape")


def clean_html(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return collapse_spaces(unescape(value))


def collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_month_day_year(value: str) -> str:
    return datetime.strptime(value, "%B %d, %Y").date().isoformat()


def normalize_nba_player_movement_date(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    for date_format in ("%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    return text


def first_present(row: dict[str, object], keys: tuple[str, ...]) -> object | None:
    casefolded = {key.lower(): value for key, value in row.items()}
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
        value = casefolded.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_identifier_text(value: object, *, zero_is_none: bool = False) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        text = str(int(value)) if value.is_integer() else format(value, "g")
    else:
        text = str(value).strip()
        if re.fullmatch(r"-?\d+\.0+", text):
            text = text.split(".", 1)[0]
    if not text:
        return None
    if zero_is_none and text == "0":
        return None
    return text


def compact_mapping(values: dict[str, str | None]) -> dict[str, str]:
    return {key: value for key, value in values.items() if value is not None}


def parse_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def stable_digest(value: object, *, length: int = 16) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:length]


def infer_draft_round(pick_overall: int) -> int:
    return 1 if pick_overall <= 30 else 2


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
