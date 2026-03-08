from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any

from db_config import load_db_config

SPOTRAC_USER_AGENT = (
    "nba-asset-lineage/0.1 (+https://github.com/wentrekin/nba-asset-lineage; contact=local)"
)


def _progress(step: str, **fields: Any) -> None:
    payload = {
        "log_type": "progress",
        "step": step,
        "ts_utc": datetime.utcnow().isoformat(),
    }
    payload.update(fields)
    print(json.dumps(payload, sort_keys=True, default=str), flush=True)


def _stable_id(prefix: str, *parts: Any) -> str:
    joined = "|".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _payload_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _http_get_text(url: str, timeout_seconds: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": SPOTRAC_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _http_post_text(url: str, form_data: dict[str, str], timeout_seconds: int = 60) -> str:
    encoded = urllib.parse.urlencode(form_data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "User-Agent": SPOTRAC_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _strip_tags(raw: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\s+", " ", html.unescape(cleaned)).strip()


def _parse_us_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%b %d, %Y").date()
    except ValueError:
        return None


def _parse_currency_to_float(raw: str) -> float | None:
    if not raw:
        return None
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _resolve_date(value: str, fallback: str) -> date:
    candidate = (value or "").strip().lower()
    if candidate in {"", "rolling", "today", "present"}:
        return date.fromisoformat(fallback)
    return date.fromisoformat(value)


def _within_range(d: date | None, start_date: date, end_date: date) -> bool:
    return bool(d and start_date <= d <= end_date)


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
    if "signed" in lower and "two-way" in lower:
        return "conversion"
    if "signed" in lower:
        return "contract_signing"
    if "drafted" in lower:
        return "draft_pick"
    return "state_change"


def _infer_action(event_type: str) -> str:
    if event_type in {"contract_signing", "re_signing", "draft_pick"}:
        return "acquire"
    if event_type == "waiver":
        return "relinquish"
    if event_type in {"extension", "conversion"}:
        return "modify"
    if event_type == "trade":
        return "transform"
    return "modify"


def _infer_direction(description: str, event_type: str) -> str:
    lower = description.lower()
    if event_type in {"contract_signing", "re_signing", "extension", "conversion", "draft_pick"}:
        return "incoming"
    if event_type == "waiver":
        return "outgoing"
    if event_type == "trade":
        if " to " in lower:
            return "outgoing"
        if " from " in lower or " with " in lower:
            return "incoming"
        return "bidirectional"
    return "neutral"


def _parse_first_team_abbrev(description: str) -> str | None:
    match = re.search(r"\(([A-Z]{2,4})\)", description)
    return match.group(1) if match else None


def _try_parse_contract_aav_from_description(description: str) -> float | None:
    match = re.search(
        r"(\d+)\s+year[s]?\s+\$([0-9]+(?:\.[0-9]+)?)\s*(million|billion)?",
        description,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    years = int(match.group(1))
    total = float(match.group(2))
    unit = (match.group(3) or "").lower()
    if unit == "million":
        total *= 1_000_000
    elif unit == "billion":
        total *= 1_000_000_000
    if years <= 0:
        return None
    return round(total / years, 2)


def _try_parse_contract_expiry_from_description(description: str) -> int | None:
    match = re.search(r"(20\d{2})-(\d{2})", description)
    if not match:
        return None
    start = int(match.group(1))
    suffix = int(match.group(2))
    century = (start // 100) * 100
    end = century + suffix
    if end < start:
        end += 100
    return end


def _parse_spotrac_transaction_html(raw_html: str, source_url: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    li_blocks = re.findall(r"<li class=\"list-group-item[^>]*>.*?</li>", raw_html, flags=re.DOTALL)
    for block in li_blocks:
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

        player_name = _strip_tags(anchor.group("player"))
        description = _strip_tags(detail.group("description"))
        event_type = _infer_event_type(description)

        rows.append(
            {
                "source_url": source_url,
                "player_id": anchor.group("player_id"),
                "player_href": html.unescape(anchor.group("href")),
                "player_name": player_name,
                "event_date": event_date,
                "description": description,
                "team_abbrev": _parse_first_team_abbrev(description),
                "event_type": event_type,
                "action_raw": _infer_action(event_type),
                "direction_raw": _infer_direction(description, event_type),
                "contract_expiry_year": _try_parse_contract_expiry_from_description(description),
                "average_annual_salary": _try_parse_contract_aav_from_description(description),
            }
        )
    return rows


def _fetch_spotrac_transactions(
    team_code: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for year in range(start_date.year, end_date.year + 1):
        window_start = max(start_date, date(year, 1, 1))
        window_end = min(end_date, date(year, 12, 31))
        url = (
            "https://www.spotrac.com/nba/transactions/_/start/"
            f"{window_start.isoformat()}/end/{window_end.isoformat()}/team/{team_code.lower()}"
        )
        html_fragment = _http_post_text(url, {"ajax": "table"})
        rows = _parse_spotrac_transaction_html(html_fragment, url)

        for row in rows:
            row_date = row.get("event_date")
            if not _within_range(row_date, start_date, end_date):
                continue
            if row["event_type"] == "state_change":
                continue
            key = (
                str(row.get("player_id") or ""),
                row_date.isoformat() if isinstance(row_date, date) else "",
                str(row.get("description") or ""),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            output.append(row)

    return output


def _fetch_spotrac_contracts(team_slug: str) -> list[dict[str, Any]]:
    url = f"https://www.spotrac.com/nba/{team_slug}/contracts/"
    raw_html = _http_get_text(url)

    table_match = re.search(
        r"<table id=\"table\"[^>]*>.*?<tbody>(?P<tbody>.*?)</tbody>.*?</table>",
        raw_html,
        flags=re.DOTALL,
    )
    if not table_match:
        return []

    rows: list[dict[str, Any]] = []
    tbody = table_match.group("tbody")
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", tbody, flags=re.DOTALL):
        player_anchor = re.search(
            r'<a href="(?P<href>[^"]*/nba/player/_/id/(?P<player_id>\d+)/[^"]+)"[^>]*class="link"[^>]*>(?P<player>[^<]+)</a>',
            tr,
            flags=re.DOTALL,
        )
        if not player_anchor:
            continue

        td_cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.DOTALL)
        normalized = [_strip_tags(cell) for cell in td_cells]
        if len(normalized) < 10:
            continue

        def _safe_int(idx: int) -> int | None:
            if idx >= len(normalized):
                return None
            raw = normalized[idx].strip()
            if not raw or raw == "--":
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        def _safe_text(idx: int) -> str:
            return normalized[idx].strip() if idx < len(normalized) else ""

        start_year = _safe_int(5) or _safe_int(2)
        end_year = _safe_int(6)
        if not start_year:
            continue

        rows.append(
            {
                "source_url": url,
                "player_id": player_anchor.group("player_id"),
                "player_href": html.unescape(player_anchor.group("href")),
                "player_name": _strip_tags(player_anchor.group("player")),
                "position": _safe_text(1),
                "contract_type": _safe_text(3),
                "start_year": start_year,
                "end_year": end_year,
                "years": _safe_int(7),
                "value": _parse_currency_to_float(_safe_text(8)),
                "aav": _parse_currency_to_float(_safe_text(9)),
                "gtd_at_sign": _parse_currency_to_float(_safe_text(10)),
                "practical_gtd": _parse_currency_to_float(_safe_text(11)),
            }
        )
    return rows


def _fetch_nba_api_draft_history(
    start_year: int,
    end_year: int,
    team_abbrevs: set[str],
    progress_every: int = 5,
) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    try:
        from nba_api.stats.endpoints import drafthistory
    except ModuleNotFoundError:
        notes.append("nba_api package is not installed; skipped nba_api draft ingestion.")
        return [], notes

    output: list[dict[str, Any]] = []
    total = end_year - start_year + 1
    for year in range(start_year, end_year + 1):
        if (year - start_year) % progress_every == 0:
            _progress(
                "nba_api_fetch_progress",
                season_year=year,
                seasons_done=year - start_year,
                seasons_total=total,
            )
        try:
            try:
                endpoint = drafthistory.DraftHistory(season_year_nullable=str(year))
            except TypeError:
                endpoint = drafthistory.DraftHistory(str(year))
            frames = endpoint.get_data_frames()
            if not frames:
                continue
            rows = frames[0].to_dict(orient="records")
            for row in rows:
                team_abbrev = str(row.get("TEAM_ABBREVIATION") or "").strip().upper()
                if team_abbrevs and team_abbrev not in team_abbrevs:
                    continue
                output.append(row)
        except Exception as exc:  # pragma: no cover
            notes.append(f"nba_api draft fetch failed for season {year}: {exc}")
    return output, notes


def _build_live_raw_rows(
    *,
    sources: set[str],
    team_slug: str,
    team_code: str,
    team_abbrevs: set[str],
    start_date: date,
    end_date: date,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    notes: list[str] = []
    event_rows: list[dict[str, Any]] = []
    asset_rows: list[dict[str, Any]] = []
    link_rows: list[dict[str, Any]] = []

    if "spotrac" in sources:
        _progress("spotrac_fetch_start", team_slug=team_slug)
        try:
            tx_rows = _fetch_spotrac_transactions(team_code, start_date, end_date)
            contract_rows = _fetch_spotrac_contracts(team_slug)
            _progress("spotrac_fetch_complete", transactions_raw=len(tx_rows), contracts_raw=len(contract_rows))
        except urllib.error.URLError as exc:
            notes.append(f"Spotrac fetch failed: {exc}")
            tx_rows = []
            contract_rows = []
            _progress("spotrac_fetch_failed", error=str(exc))

        tx_in_range = 0
        for tx in tx_rows:
            event_date = tx["event_date"]
            if not _within_range(event_date, start_date, end_date):
                continue
            tx_in_range += 1

            desc_hash = hashlib.sha1(tx["description"].encode("utf-8")).hexdigest()[:10]
            source_event_ref = f"spotrac_tx_{tx['player_id']}_{event_date.isoformat()}_{desc_hash}"
            source_asset_ref = f"spotrac_player_{tx['player_id']}"

            event_payload = dict(tx)
            event_payload["event_date"] = event_date.isoformat()
            event_rows.append(
                {
                    "source_system": "spotrac",
                    "source_event_ref": source_event_ref,
                    "event_date_raw": event_date.isoformat(),
                    "event_type_raw": tx["event_type"],
                    "source_url": tx["source_url"],
                    "source_payload": event_payload,
                }
            )

            asset_payload = dict(tx)
            asset_payload["event_date"] = event_date.isoformat()
            asset_rows.append(
                {
                    "source_system": "spotrac",
                    "source_asset_ref": source_asset_ref,
                    "asset_type_raw": "two_way" if "two-way" in tx["description"].lower() else "player",
                    "effective_date_raw": event_date.isoformat(),
                    "source_payload": asset_payload,
                }
            )

            link_payload = {
                "description": tx["description"],
                "player_id": tx["player_id"],
                "player_name": tx["player_name"],
            }
            link_rows.append(
                {
                    "source_system": "spotrac",
                    "source_event_ref": source_event_ref,
                    "source_asset_ref": source_asset_ref,
                    "action_raw": tx["action_raw"],
                    "direction_raw": tx["direction_raw"],
                    "effective_date_raw": event_date.isoformat(),
                    "source_payload": link_payload,
                }
            )

        contracts_in_range = 0
        for contract in contract_rows:
            start_year = contract["start_year"]
            end_year = contract.get("end_year") or start_year
            effective_start = date(start_year, 1, 1)
            effective_end = date(end_year, 12, 31)
            if effective_end < start_date or effective_start > end_date:
                continue
            contracts_in_range += 1

            source_asset_ref = f"spotrac_player_{contract['player_id']}"
            payload = dict(contract)
            asset_rows.append(
                {
                    "source_system": "spotrac",
                    "source_asset_ref": source_asset_ref,
                    "asset_type_raw": "player",
                    "effective_date_raw": effective_start.isoformat(),
                    "source_payload": payload,
                }
            )

        _progress(
            "spotrac_transform_complete",
            transactions_in_range=tx_in_range,
            contracts_in_range=contracts_in_range,
            event_rows_total=len(event_rows),
            asset_rows_total=len(asset_rows),
            link_rows_total=len(link_rows),
        )

    if "nba_api" in sources:
        start_year = start_date.year
        end_year = end_date.year
        _progress("nba_api_fetch_start", start_year=start_year, end_year=end_year)
        rows, nba_notes = _fetch_nba_api_draft_history(start_year, end_year, team_abbrevs)
        notes.extend(nba_notes)
        _progress("nba_api_fetch_complete", rows_raw=len(rows), notes_count=len(nba_notes))

        rows_in_range = 0
        for row in rows:
            season_raw = str(row.get("SEASON") or "").strip()
            if not season_raw.isdigit():
                continue
            season = int(season_raw)
            event_date = date(season, 6, 30)
            if not _within_range(event_date, start_date, end_date):
                continue
            rows_in_range += 1

            person_id = str(row.get("PERSON_ID") or "").strip()
            team_abbrev = str(row.get("TEAM_ABBREVIATION") or "").strip().upper()
            round_number = row.get("ROUND_NUMBER")
            overall_pick = row.get("OVERALL_PICK")

            source_event_ref = f"nba_api_draft_{season}_{round_number}_{overall_pick}_{person_id or 'unknown'}"
            source_asset_ref = f"nba_api_player_{person_id}" if person_id else f"nba_api_pick_{team_abbrev}_{season}_{overall_pick}"

            event_rows.append(
                {
                    "source_system": "nba_api",
                    "source_event_ref": source_event_ref,
                    "event_date_raw": event_date.isoformat(),
                    "event_type_raw": "draft_pick",
                    "source_url": "https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/drafthistory/",
                    "source_payload": row,
                }
            )

            asset_rows.append(
                {
                    "source_system": "nba_api",
                    "source_asset_ref": source_asset_ref,
                    "asset_type_raw": "player" if person_id else "future_draft_pick",
                    "effective_date_raw": event_date.isoformat(),
                    "source_payload": row,
                }
            )

            link_rows.append(
                {
                    "source_system": "nba_api",
                    "source_event_ref": source_event_ref,
                    "source_asset_ref": source_asset_ref,
                    "action_raw": "transform",
                    "direction_raw": "incoming",
                    "effective_date_raw": event_date.isoformat(),
                    "source_payload": row,
                }
            )

        _progress(
            "nba_api_transform_complete",
            rows_in_range=rows_in_range,
            event_rows_total=len(event_rows),
            asset_rows_total=len(asset_rows),
            link_rows_total=len(link_rows),
        )

    return {
        "events": event_rows,
        "assets": asset_rows,
        "links": link_rows,
    }, notes


def _write_raw_rows_to_bronze(
    *,
    rows: dict[str, list[dict[str, Any]]],
    run_mode: str,
    source_system: str,
) -> tuple[str, int]:
    config = load_db_config()
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for live ingestion writes.") from exc

    events = rows["events"]
    assets = rows["assets"]
    links = rows["links"]

    with psycopg.connect(config.dsn) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bronze.ingest_runs (
                    pipeline_name, source_system, run_mode, status, started_at
                )
                values (%s, %s, %s, %s, %s)
                returning run_id
                """,
                (
                    "bronze_ingest_live",
                    source_system,
                    run_mode,
                    "running",
                    datetime.utcnow(),
                ),
            )
            run_id = str(cur.fetchone()[0])

        written = 0
        try:
            with conn.cursor() as cur:
                for row in events:
                    payload_hash = _payload_hash(row["source_payload"])
                    cur.execute(
                        """
                        insert into bronze.raw_events (
                            ingest_run_id,
                            source_system,
                            source_event_ref,
                            event_date_raw,
                            event_type_raw,
                            source_url,
                            source_payload,
                            payload_hash
                        )
                        values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                        on conflict (source_system, source_event_ref, payload_hash) do nothing
                        returning raw_event_id
                        """,
                        (
                            run_id,
                            row["source_system"],
                            row["source_event_ref"],
                            row["event_date_raw"],
                            row["event_type_raw"],
                            row["source_url"],
                            json.dumps(row["source_payload"], sort_keys=True, default=str),
                            payload_hash,
                        ),
                    )
                    if cur.fetchone() is not None:
                        written += 1

                for row in assets:
                    payload_hash = _payload_hash(row["source_payload"])
                    cur.execute(
                        """
                        insert into bronze.raw_assets (
                            ingest_run_id,
                            source_system,
                            source_asset_ref,
                            asset_type_raw,
                            effective_date_raw,
                            source_payload,
                            payload_hash
                        )
                        values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                        on conflict (source_system, source_asset_ref, payload_hash) do nothing
                        returning raw_asset_id
                        """,
                        (
                            run_id,
                            row["source_system"],
                            row["source_asset_ref"],
                            row["asset_type_raw"],
                            row["effective_date_raw"],
                            json.dumps(row["source_payload"], sort_keys=True, default=str),
                            payload_hash,
                        ),
                    )
                    if cur.fetchone() is not None:
                        written += 1

                for row in links:
                    payload_hash = _payload_hash(row["source_payload"])
                    cur.execute(
                        """
                        insert into bronze.raw_event_asset_links (
                            ingest_run_id,
                            source_system,
                            source_event_ref,
                            source_asset_ref,
                            action_raw,
                            direction_raw,
                            effective_date_raw,
                            source_payload,
                            payload_hash
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                        on conflict (source_system, source_event_ref, source_asset_ref, action_raw, payload_hash) do nothing
                        returning raw_link_id
                        """,
                        (
                            run_id,
                            row["source_system"],
                            row["source_event_ref"],
                            row["source_asset_ref"],
                            row["action_raw"],
                            row["direction_raw"],
                            row["effective_date_raw"],
                            json.dumps(row["source_payload"], sort_keys=True, default=str),
                            payload_hash,
                        ),
                    )
                    if cur.fetchone() is not None:
                        written += 1

            status = "success" if written > 0 else "no_new_data"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update bronze.ingest_runs
                    set status = %s,
                        finished_at = %s,
                        records_seen = %s,
                        records_written = %s,
                        notes = %s
                    where run_id = %s::uuid
                    """,
                    (
                        status,
                        datetime.utcnow(),
                        len(events) + len(assets) + len(links),
                        written,
                        "Live ingestion into bronze.raw_* tables",
                        run_id,
                    ),
                )
            conn.commit()
        except Exception as exc:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update bronze.ingest_runs
                    set status = %s,
                        finished_at = %s,
                        records_seen = %s,
                        records_written = %s,
                        error_text = %s
                    where run_id = %s::uuid
                    """,
                    (
                        "failed",
                        datetime.utcnow(),
                        len(events) + len(assets) + len(links),
                        written,
                        str(exc),
                        run_id,
                    ),
                )
            conn.commit()
            raise

    return run_id, written


def run_live_sources_ingest(context: dict[str, str]) -> dict[str, Any]:
    start_date = _resolve_date(context["start_date"], context["as_of_date"])
    end_date = _resolve_date(context["end_date"], context["as_of_date"])
    dry_run = context["dry_run"] == "true"
    team_slug = context.get("team_slug", "memphis-grizzlies")
    team_code = context.get("team_code", "mem")
    sources = {
        entry.strip().lower()
        for entry in context.get("sources", "spotrac").split(",")
        if entry.strip()
    }
    team_abbrevs = {
        entry.strip().upper()
        for entry in context.get("team_abbrevs", "MEM,VAN").split(",")
        if entry.strip()
    }

    _progress(
        "live_ingest_start",
        sources=sorted(sources),
        team_slug=team_slug,
        start_date=start_date,
        end_date=end_date,
        dry_run=dry_run,
    )

    rows, notes = _build_live_raw_rows(
        sources=sources,
        team_slug=team_slug,
        team_code=team_code,
        team_abbrevs=team_abbrevs,
        start_date=start_date,
        end_date=end_date,
    )

    records_seen = len(rows["events"]) + len(rows["assets"]) + len(rows["links"])
    _progress(
        "live_ingest_rows_built",
        events=len(rows["events"]),
        assets=len(rows["assets"]),
        links=len(rows["links"]),
        records_seen=records_seen,
        notes_count=len(notes),
    )

    if records_seen == 0:
        manifest = {
            "stage": "bronze_ingest",
            "ingest_mode": "live_sources",
            "status": "no_new_data",
            "source_systems": sorted(sources),
            "records_seen": 0,
            "records_written": 0,
            "event_rows": 0,
            "asset_rows": 0,
            "link_rows": 0,
            "notes": notes + ["No live source records were parsed for the requested range."],
            "updated_at_utc": datetime.utcnow().isoformat(),
        }
        print(json.dumps(manifest, sort_keys=True))
        return manifest

    if dry_run:
        manifest = {
            "stage": "bronze_ingest",
            "ingest_mode": "live_sources",
            "status": "success",
            "source_systems": sorted(sources),
            "records_seen": records_seen,
            "records_written": 0,
            "event_rows": len(rows["events"]),
            "asset_rows": len(rows["assets"]),
            "link_rows": len(rows["links"]),
            "notes": notes + ["Dry-run mode: fetched/parsed live data, skipped DB writes."],
            "updated_at_utc": datetime.utcnow().isoformat(),
        }
        print(json.dumps(manifest, sort_keys=True))
        return manifest

    _progress("db_upsert_start", table="bronze.raw_events", rows=len(rows["events"]))
    _progress("db_upsert_start", table="bronze.raw_assets", rows=len(rows["assets"]))
    _progress("db_upsert_start", table="bronze.raw_event_asset_links", rows=len(rows["links"]))

    run_id, records_written = _write_raw_rows_to_bronze(
        rows=rows,
        run_mode=context["run_mode"],
        source_system=",".join(sorted(sources)),
    )

    _progress("db_upsert_complete", run_id=run_id, records_written=records_written)

    manifest = {
        "stage": "bronze_ingest",
        "ingest_mode": "live_sources",
        "status": "success" if records_written > 0 else "no_new_data",
        "run_id": run_id,
        "source_systems": sorted(sources),
        "records_seen": records_seen,
        "records_written": records_written,
        "event_rows": len(rows["events"]),
        "asset_rows": len(rows["assets"]),
        "link_rows": len(rows["links"]),
        "notes": notes,
        "updated_at_utc": datetime.utcnow().isoformat(),
    }
    print(json.dumps(manifest, sort_keys=True))
    return manifest
