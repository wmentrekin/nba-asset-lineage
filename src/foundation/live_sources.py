from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from socket import timeout as socket_timeout
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg

from foundation.ingest import PlayerRow, RosterBaselinePlayerRow, SourceEventRow, SourceRecordRow, upsert_roster_baseline_players
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


def build_bref_transactions_url(team_code: str, season_end_year: int) -> str:
    return f"https://www.basketball-reference.com/teams/{team_code.upper()}/{season_end_year}_transactions.html"


def build_bref_team_season_url(team_code: str, season_end_year: int) -> str:
    return f"https://www.basketball-reference.com/teams/{team_code.upper()}/{season_end_year}.html"


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
    return source_records, source_events


def load_bref_source_events(database_url: str, *, team_code: str, season_end_year: int) -> dict[str, object]:
    html = fetch_bref_transactions_html(team_code=team_code, season_end_year=season_end_year)
    source_records, source_events = build_bref_source_rows(
        team_code=team_code,
        season_end_year=season_end_year,
        html=html,
    )
    with psycopg.connect(database_url, connect_timeout=20) as connection:
        insert_source_records(connection, source_records)
        insert_source_events(connection, source_events)
        connection.commit()
    return {
        "status": "ok",
        "source_records": len(source_records),
        "source_events": len(source_events),
        "season_end_year": season_end_year,
        "team_code": team_code.upper(),
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
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return collapse_spaces(unescape(value))


def collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_month_day_year(value: str) -> str:
    return datetime.strptime(value, "%B %d, %Y").date().isoformat()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
