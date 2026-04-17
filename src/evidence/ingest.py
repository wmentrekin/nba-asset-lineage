from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from db_config import load_database_url
from evidence.models import NormalizedClaim, SourceRecord
from evidence.normalize import normalize_source_record
from shared.ids import stable_id, stable_payload_hash

SPOTRAC_USER_AGENT = (
    "nba-asset-lineage/0.1 (+https://github.com/wentrekin/nba-asset-lineage; contact=local)"
)


def _http_get_text(url: str, timeout_seconds: int = 60) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": SPOTRAC_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _http_post_text(url: str, form_data: dict[str, str], timeout_seconds: int = 60) -> str:
    encoded = urllib.parse.urlencode(form_data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "User-Agent": SPOTRAC_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _strip_tags(raw: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\s+", " ", html.unescape(cleaned)).strip()


def _parse_us_date(raw: str) -> date | None:
    raw_value = raw.strip()
    if not raw_value:
        return None
    try:
        return datetime.strptime(raw_value, "%b %d, %Y").date()
    except ValueError:
        return None


def _parse_currency_to_float(raw: str) -> float | None:
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned or cleaned == "--":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _within_range(value: date | None, start_date: date, end_date: date) -> bool:
    return bool(value and start_date <= value <= end_date)


def _infer_event_type(description: str) -> str:
    lower = description.lower()
    if "traded" in lower:
        return "trade"
    if "waived" in lower or "released" in lower:
        return "waiver"
    if "signed" in lower and "extension" in lower:
        return "extension"
    if "re-signed" in lower:
        return "re_signing"
    if "signed" in lower:
        return "signing"
    if "drafted" in lower:
        return "draft"
    return "state_change"


def _parse_contract_expiry_from_description(description: str) -> int | None:
    match = re.search(r"(20\d{2})-(\d{2})", description)
    if not match:
        return None
    start_year = int(match.group(1))
    suffix = int(match.group(2))
    century = (start_year // 100) * 100
    end_year = century + suffix
    if end_year < start_year:
        end_year += 100
    return end_year


def _try_parse_contract_aav_from_description(description: str) -> float | None:
    match = re.search(
        r"(\d+)\s+year[s]?\s+\$([0-9]+(?:\.[0-9]+)?)\s*(million|billion)?",
        description,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    years = int(match.group(1))
    total_value = float(match.group(2))
    unit = (match.group(3) or "").lower()
    if unit == "million":
        total_value *= 1_000_000
    elif unit == "billion":
        total_value *= 1_000_000_000
    return round(total_value / years, 2) if years > 0 else None


def _extract_counterparty(description: str) -> str | None:
    match = re.search(r"\b(?:to|from|with)\s+([A-Z][A-Za-z .'-]+)$", description)
    return match.group(1).strip() if match else None


def _parse_spotrac_transaction_html(raw_html: str, source_url: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    list_items = re.findall(r"<li class=\"list-group-item[^>]*>.*?</li>", raw_html, flags=re.DOTALL)
    for index, block in enumerate(list_items, start=1):
        anchor = re.search(
            r'<a href="(?P<href>[^"]*/nba/player/_/id/(?P<player_id>\d+)/[^"]+)"[^>]*class="text-danger h4"[^>]*>(?P<player>.*?)</a>',
            block,
            flags=re.DOTALL,
        )
        detail = re.search(
            r"<small class=\"d-block\"><strong>(?P<date>[^<]+)</strong>\s*-\s*(?P<description>.*?)</small>",
            block,
            flags=re.DOTALL,
        )
        if not anchor or not detail:
            continue

        event_date = _parse_us_date(detail.group("date"))
        if not event_date:
            continue

        description = _strip_tags(detail.group("description"))
        description_hash = stable_id("desc", description, length=10).split("_", 1)[1]
        record = {
            "player_id": anchor.group("player_id"),
            "player_href": html.unescape(anchor.group("href")),
            "player_name": _strip_tags(anchor.group("player")),
            "event_date": event_date.isoformat(),
            "description": description,
            "description_hash": description_hash,
            "event_type": _infer_event_type(description),
            "contract_expiry_year": _parse_contract_expiry_from_description(description),
            "average_annual_salary": _try_parse_contract_aav_from_description(description),
            "counterparty_team": _extract_counterparty(description),
            "source_url": source_url,
            "source_sequence": index,
        }
        if record["event_type"] != "state_change":
            records.append(record)
    return records


def fetch_spotrac_transactions(team_code: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    overall_sequence = 0
    seen_keys: set[tuple[str, str, str]] = set()
    for year in range(start_date.year, end_date.year + 1):
        window_start = max(start_date, date(year, 1, 1))
        window_end = min(end_date, date(year, 12, 31))
        source_url = (
            "https://www.spotrac.com/nba/transactions/_/start/"
            f"{window_start.isoformat()}/end/{window_end.isoformat()}/team/{team_code.lower()}"
        )
        raw_html = _http_post_text(source_url, {"ajax": "table"})
        for row in _parse_spotrac_transaction_html(raw_html, source_url):
            row_date = date.fromisoformat(row["event_date"])
            if not _within_range(row_date, start_date, end_date):
                continue
            dedupe_key = (str(row["player_id"]), row["event_date"], str(row["description"]))
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            overall_sequence += 1
            row["source_sequence"] = overall_sequence
            records.append(row)
    return records


def fetch_spotrac_contracts(team_slug: str) -> list[dict[str, Any]]:
    source_url = f"https://www.spotrac.com/nba/{team_slug}/contracts/"
    raw_html = _http_get_text(source_url)
    table_match = re.search(
        r"<table id=\"table\"[^>]*>.*?<tbody>(?P<tbody>.*?)</tbody>.*?</table>",
        raw_html,
        flags=re.DOTALL,
    )
    if not table_match:
        return []

    records: list[dict[str, Any]] = []
    for index, row_html in enumerate(re.findall(r"<tr[^>]*>.*?</tr>", table_match.group("tbody"), flags=re.DOTALL), start=1):
        player_anchor = re.search(
            r'<a href="(?P<href>[^"]*/nba/player/_/id/(?P<player_id>\d+)/[^"]+)"[^>]*class="link"[^>]*>(?P<player>[^<]+)</a>',
            row_html,
            flags=re.DOTALL,
        )
        if not player_anchor:
            continue
        cells = [_strip_tags(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.DOTALL)]
        if len(cells) < 10:
            continue

        def safe_int(idx: int) -> int | None:
            if idx >= len(cells):
                return None
            raw_value = cells[idx].strip()
            if not raw_value or raw_value == "--":
                return None
            try:
                return int(raw_value)
            except ValueError:
                return None

        start_year = safe_int(5) or safe_int(2)
        if not start_year:
            continue

        records.append(
            {
                "player_id": player_anchor.group("player_id"),
                "player_href": html.unescape(player_anchor.group("href")),
                "player_name": _strip_tags(player_anchor.group("player")),
                "position": cells[1].strip() if len(cells) > 1 else "",
                "contract_type": cells[3].strip() if len(cells) > 3 else "",
                "start_year": start_year,
                "end_year": safe_int(6),
                "years": safe_int(7),
                "value": _parse_currency_to_float(cells[8]) if len(cells) > 8 else None,
                "aav": _parse_currency_to_float(cells[9]) if len(cells) > 9 else None,
                "gtd_at_sign": _parse_currency_to_float(cells[10]) if len(cells) > 10 else None,
                "practical_gtd": _parse_currency_to_float(cells[11]) if len(cells) > 11 else None,
                "source_url": source_url,
                "source_sequence": index,
            }
        )
    return records


def fetch_nba_api_draft_history(
    start_year: int,
    end_year: int,
    team_abbrevs: set[str],
) -> list[dict[str, Any]]:
    try:
        from nba_api.stats.endpoints import drafthistory
    except ModuleNotFoundError:
        return []

    records: list[dict[str, Any]] = []
    overall_sequence = 0
    for year in range(start_year, end_year + 1):
        try:
            try:
                endpoint = drafthistory.DraftHistory(season_year_nullable=str(year))
            except TypeError:
                endpoint = drafthistory.DraftHistory(str(year))
            frames = endpoint.get_data_frames()
            if not frames:
                continue
            for row in frames[0].to_dict(orient="records"):
                team_abbrev = str(row.get("TEAM_ABBREVIATION") or "").strip().upper()
                if team_abbrevs and team_abbrev not in team_abbrevs:
                    continue
                overall_sequence += 1
                payload = dict(row)
                payload["event_date"] = date(int(str(payload["SEASON"])), 6, 30).isoformat()
                payload["source_sequence"] = overall_sequence
                records.append(payload)
        except Exception:
            continue
    return records


def build_live_source_records(
    *,
    sources: set[str],
    team_slug: str,
    team_code: str,
    team_abbrevs: set[str],
    start_date: date,
    end_date: date,
    captured_at: datetime | None = None,
    parser_version: str = "stage1-live-v1",
) -> list[SourceRecord]:
    captured_at_value = captured_at or datetime.utcnow()
    created_at = captured_at_value
    source_records: list[SourceRecord] = []

    if "spotrac" in sources:
        for row in fetch_spotrac_transactions(team_code, start_date, end_date):
            source_records.append(
                _build_source_record(
                    source_system="spotrac",
                    source_type="spotrac_transaction",
                    source_locator=row["source_url"],
                    source_url=row["source_url"],
                    raw_payload=row,
                    captured_at=captured_at_value,
                    parser_version=parser_version,
                    created_at=created_at,
                )
            )
        for row in fetch_spotrac_contracts(team_slug):
            source_records.append(
                _build_source_record(
                    source_system="spotrac",
                    source_type="spotrac_contract",
                    source_locator=row["source_url"],
                    source_url=row["source_url"],
                    raw_payload=row,
                    captured_at=captured_at_value,
                    parser_version=parser_version,
                    created_at=created_at,
                )
            )

    if "nba_api" in sources:
        for row in fetch_nba_api_draft_history(start_date.year, end_date.year, team_abbrevs):
            row_date = date.fromisoformat(str(row["event_date"]))
            if not _within_range(row_date, start_date, end_date):
                continue
            source_records.append(
                _build_source_record(
                    source_system="nba_api",
                    source_type="nba_api_draft_history",
                    source_locator="nba_api.stats.endpoints.drafthistory",
                    source_url="https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/drafthistory/",
                    raw_payload=row,
                    captured_at=captured_at_value,
                    parser_version=parser_version,
                    created_at=created_at,
                )
            )

    return source_records


def _coerce_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def capture_source_records(raw_records: Any) -> list[SourceRecord]:
    if isinstance(raw_records, dict):
        records_input = [raw_records]
    elif isinstance(raw_records, (list, tuple)):
        records_input = list(raw_records)
    else:
        records_input = [raw_records]

    source_records_by_id: dict[str, SourceRecord] = {}
    for raw_record in records_input:
        source_record = _build_source_record(
            source_system=str(raw_record["source_system"]),
            source_type=str(raw_record["source_type"]),
            source_locator=str(raw_record["source_locator"]),
            source_url=raw_record.get("source_url"),
            raw_payload=dict(raw_record.get("raw_payload") or {}),
            captured_at=raw_record["captured_at"],
            parser_version=str(raw_record["parser_version"]),
            created_at=raw_record.get("captured_at") or datetime.utcnow().isoformat(),
        )
        existing = source_records_by_id.get(source_record.source_record_id)
        if existing is None:
            source_records_by_id[source_record.source_record_id] = source_record
        else:
            source_records_by_id[source_record.source_record_id] = SourceRecord(
                source_record_id=existing.source_record_id,
                source_system=existing.source_system,
                source_type=existing.source_type,
                source_locator=existing.source_locator,
                source_url=existing.source_url,
                captured_at=existing.captured_at,
                raw_payload=existing.raw_payload,
                payload_hash=existing.payload_hash,
                parser_version=existing.parser_version,
                created_at=existing.created_at,
                duplicate_count=existing.duplicate_count + 1,
            )
    return list(source_records_by_id.values())


ingest_source_records = capture_source_records


def _build_source_record(
    *,
    source_system: str,
    source_type: str,
    source_locator: str,
    source_url: str | None,
    raw_payload: dict[str, Any],
    captured_at: datetime,
    parser_version: str,
    created_at: datetime,
) -> SourceRecord:
    payload_hash = stable_payload_hash(raw_payload)
    source_record_id = stable_id("source_record", source_system, source_type, source_locator, payload_hash)
    return SourceRecord(
        source_record_id=source_record_id,
        source_system=source_system,
        source_type=source_type,
        source_locator=source_locator,
        source_url=source_url,
        captured_at=captured_at,
        raw_payload=raw_payload,
        payload_hash=payload_hash,
        parser_version=parser_version,
        created_at=created_at,
    )


def bootstrap_evidence_schema(sql_path: Path | str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required to bootstrap the redesign evidence schema.") from exc

    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with psycopg.connect(load_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
        conn.commit()


def insert_source_records(conn: Any, source_records: Iterable[SourceRecord]) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for record in source_records:
            cur.execute(
                """
                insert into evidence.source_records (
                    source_record_id,
                    source_system,
                    source_type,
                    source_locator,
                    source_url,
                    captured_at,
                    raw_payload,
                    payload_hash,
                    parser_version,
                    created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                on conflict (source_record_id) do nothing
                returning source_record_id
                """,
                (
                    record.source_record_id,
                    record.source_system,
                    record.source_type,
                    record.source_locator,
                    record.source_url,
                    record.captured_at,
                    json.dumps(record.raw_payload, sort_keys=True, default=str),
                    record.payload_hash,
                    record.parser_version,
                    record.created_at,
                ),
            )
            if cur.fetchone() is not None:
                inserted += 1
    return inserted


def insert_normalized_claims(conn: Any, claims: Iterable[NormalizedClaim]) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for claim in claims:
            cur.execute(
                """
                insert into evidence.normalized_claims (
                    claim_id,
                    source_record_id,
                    claim_type,
                    claim_subject_type,
                    claim_subject_key,
                    claim_group_hint,
                    claim_date,
                    source_sequence,
                    claim_payload,
                    confidence_flag,
                    normalizer_version,
                    created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                on conflict (claim_id) do nothing
                returning claim_id
                """,
                (
                    claim.claim_id,
                    claim.source_record_id,
                    claim.claim_type,
                    claim.claim_subject_type,
                    claim.claim_subject_key,
                    claim.claim_group_hint,
                    claim.claim_date,
                    claim.source_sequence,
                    json.dumps(claim.claim_payload, sort_keys=True, default=str),
                    claim.confidence_flag,
                    claim.normalizer_version,
                    claim.created_at,
                ),
            )
            if cur.fetchone() is not None:
                inserted += 1
    return inserted


def fetch_source_records(conn: Any, *, source_record_id: str | None = None) -> list[SourceRecord]:
    sql = """
        select
            source_record_id,
            source_system,
            source_type,
            source_locator,
            source_url,
            captured_at,
            raw_payload,
            payload_hash,
            parser_version,
            created_at
        from evidence.source_records
    """
    params: tuple[Any, ...] = ()
    if source_record_id:
        sql += " where source_record_id = %s"
        params = (source_record_id,)
    sql += " order by created_at, source_record_id"

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        SourceRecord(
            source_record_id=row[0],
            source_system=row[1],
            source_type=row[2],
            source_locator=row[3],
            source_url=row[4],
            captured_at=row[5],
            raw_payload=row[6],
            payload_hash=row[7],
            parser_version=row[8],
            created_at=row[9],
            duplicate_count=1,
        )
        for row in rows
    ]


def normalize_source_records(
    conn: Any,
    *,
    normalizer_version: str,
    source_record_id: str | None = None,
    created_at: datetime | None = None,
) -> list[NormalizedClaim]:
    records = fetch_source_records(conn, source_record_id=source_record_id)
    claims: list[NormalizedClaim] = []
    for record in records:
        claims.extend(
            normalize_source_record(
                record,
                normalizer_version=normalizer_version,
                created_at=created_at,
            )
        )
    return claims


def ingest_live_source_records(
    *,
    sources: set[str],
    team_slug: str,
    team_code: str,
    team_abbrevs: set[str],
    start_date: date,
    end_date: date,
    parser_version: str = "stage1-live-v1",
) -> dict[str, int]:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required to ingest redesign evidence rows.") from exc

    source_records = build_live_source_records(
        sources=sources,
        team_slug=team_slug,
        team_code=team_code,
        team_abbrevs=team_abbrevs,
        start_date=start_date,
        end_date=end_date,
        parser_version=parser_version,
    )
    with psycopg.connect(load_database_url()) as conn:
        inserted = insert_source_records(conn, source_records)
        conn.commit()
    return {
        "source_record_count": len(source_records),
        "inserted_source_record_count": inserted,
    }
