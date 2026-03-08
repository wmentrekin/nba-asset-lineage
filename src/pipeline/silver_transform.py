from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from db_config import load_db_config


SOURCE_PRIORITY = {
    "sportradar": 1,
    "nba_api": 2,
    "nba_com": 3,
    "spotrac": 4,
}

EVENT_TYPE_ALIASES = {
    "trade": "trade",
    "draft": "draft_pick",
    "draft_pick": "draft_pick",
    "waive": "waiver",
    "waiver": "waiver",
    "contract_signing": "contract_signing",
    "signing": "contract_signing",
    "extension": "extension",
    "re_signing": "re_signing",
    "resigning": "re_signing",
    "conversion": "conversion",
    "two_way_signing": "conversion",
    "state_change": "state_change",
}

ASSET_TYPE_ALIASES = {
    "player": "player",
    "full_roster": "full_roster",
    "two_way": "two_way",
    "future_draft_pick": "future_draft_pick",
    "pick": "future_draft_pick",
}

ACTION_ALIASES = {
    "acquire": "acquire",
    "relinquish": "relinquish",
    "modify": "modify",
    "terminate": "terminate",
    "transform": "transform",
}

DIRECTION_ALIASES = {
    "incoming": "incoming",
    "outgoing": "outgoing",
    "bidirectional": "bidirectional",
    "neutral": "neutral",
}


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join("" if value is None else str(value) for value in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _priority(source_system: str) -> int:
    return SOURCE_PRIORITY.get(source_system.lower().strip(), 99)


def _resolve_date(value: str, fallback: str) -> date:
    candidate = (value or "").strip().lower()
    if candidate in {"", "rolling", "today", "present"}:
        return date.fromisoformat(fallback)
    return date.fromisoformat(value)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {"value": decoded}
        except json.JSONDecodeError:
            return {"value": value}
    return {"value": value}


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    raw = _clean_text(value)
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    try:
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            return date.fromisoformat(raw)
        return datetime.fromisoformat(raw).date()
    except ValueError:
        pass

    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raw = _clean_text(value)
    if not raw:
        return None
    raw = raw.replace(",", "")
    if raw.isdigit():
        return int(raw)
    return None


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    raw = _clean_text(value).replace("$", "").replace(",", "")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except Exception:
        return None


def _normalize_event_type(value: str, payload: dict[str, Any]) -> str:
    candidate = _clean_text(value).lower()
    if candidate in EVENT_TYPE_ALIASES:
        return EVENT_TYPE_ALIASES[candidate]

    desc = _clean_text(payload.get("description")).lower()
    for key, mapped in (
        ("traded", "trade"),
        ("drafted", "draft_pick"),
        ("waived", "waiver"),
        ("released", "waiver"),
        ("re-signed", "re_signing"),
        ("extension", "extension"),
        ("two-way", "conversion"),
        ("signed", "contract_signing"),
    ):
        if key in desc:
            return mapped
    return "state_change"


def _normalize_asset_type(value: str, payload: dict[str, Any]) -> str:
    candidate = _clean_text(value).lower()
    if candidate in ASSET_TYPE_ALIASES:
        return ASSET_TYPE_ALIASES[candidate]

    if _clean_text(payload.get("PERSON_ID")):
        return "player"
    if payload.get("OVERALL_PICK") or payload.get("pick_number"):
        return "future_draft_pick"
    return "player"


def _normalize_action(value: str) -> str:
    candidate = _clean_text(value).lower()
    return ACTION_ALIASES.get(candidate, "modify")


def _normalize_direction(value: str) -> str:
    candidate = _clean_text(value).lower()
    return DIRECTION_ALIASES.get(candidate, "neutral")


def _infer_operating_team(d: date, team_hint: str | None) -> str:
    hint = _clean_text(team_hint).upper()
    if hint in {"MEM", "VAN"}:
        return hint
    return "VAN" if d < date(2001, 7, 1) else "MEM"


def _pick_first(payload: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in payload and payload[key] not in ("", None):
            return payload[key]
    return None


def _event_label(event_type: str, payload: dict[str, Any], source_event_ref: str) -> str:
    description = _clean_text(payload.get("description") or payload.get("DESCRIPTION"))
    if description:
        return description[:220]
    player = _clean_text(payload.get("player_name") or payload.get("PLAYER_NAME"))
    if player:
        return f"{event_type}: {player}"
    return f"{event_type}: {source_event_ref}"


def _asset_key(asset_type: str, payload: dict[str, Any], source_asset_ref: str) -> str:
    if asset_type == "future_draft_pick":
        original_team = _clean_text(
            _pick_first(payload, ["original_team", "TEAM_ABBREVIATION", "team_abbrev"])
        )
        pick_year = _pick_first(payload, ["pick_year", "SEASON"])
        pick_round = _pick_first(payload, ["pick_round", "ROUND_NUMBER"])
        pick_number = _pick_first(payload, ["pick_number", "OVERALL_PICK"])
        return (
            f"pick:{original_team or 'UNK'}:{pick_year or 'UNK'}:"
            f"{pick_round or 'UNK'}:{pick_number or 'UNK'}"
        )

    player_name = _clean_text(_pick_first(payload, ["player_name", "PLAYER_NAME", "player"]))
    if player_name:
        return f"player:{player_name.lower().replace(' ', '_')}"
    return f"asset:{source_asset_ref}"


def _parse_end_date(payload: dict[str, Any]) -> date | None:
    direct = _parse_date(_pick_first(payload, ["effective_end_date", "end_date"]))
    if direct:
        return direct
    end_year = _parse_int(_pick_first(payload, ["end_year", "contract_expiry_year"]))
    if end_year:
        return date(end_year, 12, 31)
    return None


def _lineage_date_from_row(link_row: dict[str, Any], event_date: date | None) -> date | None:
    parsed = _parse_date(link_row.get("effective_date_raw"))
    if parsed:
        return parsed
    return event_date


def _fetch_bronze_rows(cur: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    cur.execute(
        """
        select
            raw_event_id,
            source_system,
            source_event_ref,
            event_date_raw,
            event_type_raw,
            source_url,
            source_payload,
            payload_hash,
            created_at
        from bronze.raw_events
        """
    )
    event_rows = [dict(row) for row in cur.fetchall()]

    cur.execute(
        """
        select
            raw_asset_id,
            source_system,
            source_asset_ref,
            asset_type_raw,
            effective_date_raw,
            source_payload,
            payload_hash,
            created_at
        from bronze.raw_assets
        """
    )
    asset_rows = [dict(row) for row in cur.fetchall()]

    cur.execute(
        """
        select
            raw_link_id,
            source_system,
            source_event_ref,
            source_asset_ref,
            action_raw,
            direction_raw,
            effective_date_raw,
            source_payload,
            payload_hash,
            created_at
        from bronze.raw_event_asset_links
        """
    )
    link_rows = [dict(row) for row in cur.fetchall()]
    return event_rows, asset_rows, link_rows


def run_silver_transform(context: dict[str, str]) -> dict[str, object]:
    start_date = _resolve_date(context["start_date"], context["as_of_date"])
    end_date = _resolve_date(context["end_date"], context["as_of_date"])
    dry_run = context["dry_run"] == "true"
    franchise_id = context["franchise_id"]

    config = load_db_config()
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for silver transform.") from exc

    with psycopg.connect(config.dsn) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            raw_events, raw_assets, raw_links = _fetch_bronze_rows(cur)

        event_candidates: dict[str, dict[str, Any]] = {}
        for row in raw_events:
            payload = _as_dict(row.get("source_payload"))
            event_date = _parse_date(row.get("event_date_raw"))
            if event_date is None:
                event_date = _parse_date(_pick_first(payload, ["event_date", "DATE", "date"]))
            if event_date is None or event_date < start_date or event_date > end_date:
                continue

            source_system = _clean_text(row.get("source_system"))
            source_event_ref = _clean_text(row.get("source_event_ref"))
            if not source_system or not source_event_ref:
                continue

            event_type = _normalize_event_type(_clean_text(row.get("event_type_raw")), payload)
            team_hint = _pick_first(payload, ["team_abbrev", "TEAM_ABBREVIATION", "team_id", "TEAM_ID"])
            operating_team_id = _infer_operating_team(event_date, _clean_text(team_hint))
            event_id = _stable_id("evt", source_system, source_event_ref)
            score = (
                _priority(source_system),
                -int(row["created_at"].timestamp()) if row.get("created_at") else 0,
                _clean_text(row.get("payload_hash")),
            )
            candidate = {
                "event_id": event_id,
                "source_system": source_system,
                "source_event_ref": source_event_ref,
                "event_date": event_date,
                "event_type": event_type,
                "event_label": _event_label(event_type, payload, source_event_ref),
                "description": _clean_text(
                    _pick_first(payload, ["description", "DESCRIPTION", "event_label"])
                ),
                "source_url": _clean_text(row.get("source_url")),
                "team_id": _clean_text(team_hint),
                "franchise_id": franchise_id,
                "operating_team_id": operating_team_id,
                "score": score,
            }

            current = event_candidates.get(event_id)
            if current is None or candidate["score"] < current["score"]:
                event_candidates[event_id] = candidate

        ordered_events = sorted(
            event_candidates.values(),
            key=lambda item: (item["event_date"], item["event_type"], item["event_id"]),
        )
        event_order_by_id: dict[str, int] = {}
        per_day_counter: dict[date, int] = {}
        for event in ordered_events:
            event_date = event["event_date"]
            per_day_counter[event_date] = per_day_counter.get(event_date, 0) + 1
            event_order_by_id[event["event_id"]] = per_day_counter[event_date]

        event_rows: list[dict[str, Any]] = []
        event_lookup: dict[tuple[str, str], dict[str, Any]] = {}
        for event in ordered_events:
            event.pop("score", None)
            event["event_order"] = event_order_by_id[event["event_id"]]
            event_rows.append(event)
            event_lookup[(event["source_system"], event["source_event_ref"])] = event

        asset_rows: list[dict[str, Any]] = []
        asset_lookup: dict[tuple[str, str], str] = {}
        for row in raw_assets:
            payload = _as_dict(row.get("source_payload"))
            source_system = _clean_text(row.get("source_system"))
            source_asset_ref = _clean_text(row.get("source_asset_ref"))
            if not source_system or not source_asset_ref:
                continue

            start = _parse_date(row.get("effective_date_raw"))
            if start is None:
                start = _parse_date(_pick_first(payload, ["event_date", "DATE", "date"]))
            if start is None:
                season = _parse_int(_pick_first(payload, ["SEASON", "pick_year"]))
                if season:
                    start = date(season, 6, 30)
            if start is None:
                continue

            end = _parse_end_date(payload)
            if start > end_date:
                continue
            if end and end < start_date:
                continue

            asset_type = _normalize_asset_type(_clean_text(row.get("asset_type_raw")), payload)
            subtype = _clean_text(_pick_first(payload, ["position", "contract_type", "subtype"]))
            player_name = _clean_text(_pick_first(payload, ["player_name", "PLAYER_NAME", "player"]))
            contract_expiry_year = _parse_int(
                _pick_first(payload, ["contract_expiry_year", "end_year"])
            )
            average_annual_salary = _parse_decimal(
                _pick_first(payload, ["average_annual_salary", "aav"])
            )
            team_hint = _clean_text(
                _pick_first(payload, ["team_abbrev", "TEAM_ABBREVIATION", "team_id"])
            )
            operating_team_id = _infer_operating_team(start, team_hint)
            asset_id = _stable_id("asset", source_system, source_asset_ref)
            edge_id = _stable_id("edge", asset_id, start.isoformat(), _clean_text(row.get("payload_hash")))
            asset_lookup[(source_system, source_asset_ref)] = asset_id

            description = _clean_text(_pick_first(payload, ["description", "DESCRIPTION"]))
            prior_transactions: list[dict[str, Any]] = []
            if description:
                prior_transactions.append(
                    {
                        "date": start.isoformat(),
                        "event_type": _normalize_event_type(
                            _clean_text(_pick_first(payload, ["event_type", "event_type_raw"])),
                            payload,
                        ),
                        "description": description,
                    }
                )

            pick_year = _parse_int(_pick_first(payload, ["pick_year", "SEASON"]))
            pick_round = _parse_int(_pick_first(payload, ["pick_round", "ROUND_NUMBER"]))
            pick_number = _parse_int(_pick_first(payload, ["pick_number", "OVERALL_PICK"]))

            asset_rows.append(
                {
                    "edge_id": edge_id,
                    "asset_id": asset_id,
                    "asset_key": _asset_key(asset_type, payload, source_asset_ref),
                    "source_system": source_system,
                    "source_asset_ref": source_asset_ref,
                    "asset_type": asset_type,
                    "subtype": subtype or None,
                    "start_date": start,
                    "end_date": end,
                    "is_active_at_end": bool(end is None or end >= end_date),
                    "player_name": player_name or None,
                    "contract_expiry_year": contract_expiry_year,
                    "average_annual_salary": average_annual_salary,
                    "acquisition_method": _clean_text(
                        _pick_first(payload, ["event_type", "event_type_raw", "action_raw"])
                    )
                    or None,
                    "prior_transactions": json.dumps(prior_transactions) if prior_transactions else None,
                    "original_team": _clean_text(
                        _pick_first(payload, ["original_team", "TEAM_ABBREVIATION", "team_abbrev"])
                    )
                    or None,
                    "pick_year": pick_year,
                    "pick_round": pick_round,
                    "pick_number": pick_number,
                    "protections_raw": _clean_text(_pick_first(payload, ["protections", "protections_raw"]))
                    or None,
                    "swap_conditions_raw": _clean_text(
                        _pick_first(payload, ["swap_conditions", "swap_conditions_raw"])
                    )
                    or None,
                    "owner_team_id": team_hint or operating_team_id,
                    "franchise_id": franchise_id,
                    "operating_team_id": operating_team_id,
                }
            )

        lineage_rows: list[dict[str, Any]] = []
        skipped_links = 0
        for row in raw_links:
            source_system = _clean_text(row.get("source_system"))
            source_event_ref = _clean_text(row.get("source_event_ref"))
            source_asset_ref = _clean_text(row.get("source_asset_ref"))
            if not source_system or not source_event_ref or not source_asset_ref:
                skipped_links += 1
                continue

            event = event_lookup.get((source_system, source_event_ref))
            asset_id = asset_lookup.get((source_system, source_asset_ref))
            if event is None or asset_id is None:
                skipped_links += 1
                continue

            effective_date = _lineage_date_from_row(row, event["event_date"])
            if effective_date is None or effective_date < start_date or effective_date > end_date:
                continue

            payload_hash = _clean_text(row.get("payload_hash"))
            lineage_id = _stable_id(
                "lin",
                source_system,
                source_event_ref,
                source_asset_ref,
                _clean_text(row.get("action_raw")),
                _clean_text(row.get("direction_raw")),
                effective_date.isoformat(),
                payload_hash,
            )

            lineage_rows.append(
                {
                    "lineage_id": lineage_id,
                    "event_id": event["event_id"],
                    "asset_id": asset_id,
                    "action_raw": _normalize_action(_clean_text(row.get("action_raw"))),
                    "direction_raw": _normalize_direction(_clean_text(row.get("direction_raw"))),
                    "effective_date": effective_date,
                    "source_system": source_system,
                    "source_event_ref": source_event_ref,
                    "source_asset_ref": source_asset_ref,
                    "source_link_id": str(row.get("raw_link_id") or ""),
                    "franchise_id": franchise_id,
                }
            )

        records_seen = len(raw_events) + len(raw_assets) + len(raw_links)
        records_written = len(event_rows) + len(asset_rows) + len(lineage_rows)

        if dry_run:
            manifest = {
                "stage": "silver_transform",
                "status": "success" if records_written > 0 else "no_new_data",
                "franchise_id": franchise_id,
                "run_mode": context["run_mode"],
                "as_of_date": context["as_of_date"],
                "records_seen": records_seen,
                "records_written": 0,
                "events_built": len(event_rows),
                "assets_built": len(asset_rows),
                "lineage_built": len(lineage_rows),
                "links_skipped": skipped_links,
                "notes": "Dry-run mode: Bronze->Silver rows built, DB writes skipped.",
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            print(json.dumps(manifest, sort_keys=True))
            return manifest

        with conn.cursor() as cur:
            cur.execute(
                """
                delete from silver.event_asset_lineage
                where franchise_id = %s
                  and effective_date >= %s
                  and effective_date <= %s
                """,
                (franchise_id, start_date, end_date),
            )
            cur.execute(
                """
                delete from silver.assets
                where franchise_id = %s
                  and start_date >= %s
                  and start_date <= %s
                """,
                (franchise_id, start_date, end_date),
            )
            cur.execute(
                """
                delete from silver.events
                where franchise_id = %s
                  and event_date >= %s
                  and event_date <= %s
                """,
                (franchise_id, start_date, end_date),
            )

            event_sql = """
                insert into silver.events (
                    event_id, source_system, source_event_ref, event_date, event_type,
                    event_label, description, source_url, team_id, event_order,
                    franchise_id, operating_team_id
                )
                values (
                    %(event_id)s, %(source_system)s, %(source_event_ref)s, %(event_date)s, %(event_type)s,
                    %(event_label)s, %(description)s, %(source_url)s, %(team_id)s, %(event_order)s,
                    %(franchise_id)s, %(operating_team_id)s
                )
                on conflict (event_id) do update
                set source_system = excluded.source_system,
                    source_event_ref = excluded.source_event_ref,
                    event_date = excluded.event_date,
                    event_type = excluded.event_type,
                    event_label = excluded.event_label,
                    description = excluded.description,
                    source_url = excluded.source_url,
                    team_id = excluded.team_id,
                    event_order = excluded.event_order,
                    franchise_id = excluded.franchise_id,
                    operating_team_id = excluded.operating_team_id,
                    updated_at = now()
            """
            for row in event_rows:
                cur.execute(event_sql, row)

            asset_sql = """
                insert into silver.assets (
                    edge_id, asset_id, asset_key, source_system, source_asset_ref, asset_type,
                    subtype, start_date, end_date, is_active_at_end, player_name, contract_expiry_year,
                    average_annual_salary, acquisition_method, prior_transactions, original_team,
                    pick_year, pick_round, pick_number, protections_raw, swap_conditions_raw,
                    owner_team_id, franchise_id, operating_team_id
                )
                values (
                    %(edge_id)s, %(asset_id)s, %(asset_key)s, %(source_system)s, %(source_asset_ref)s, %(asset_type)s,
                    %(subtype)s, %(start_date)s, %(end_date)s, %(is_active_at_end)s, %(player_name)s, %(contract_expiry_year)s,
                    %(average_annual_salary)s, %(acquisition_method)s, %(prior_transactions)s::jsonb, %(original_team)s,
                    %(pick_year)s, %(pick_round)s, %(pick_number)s, %(protections_raw)s, %(swap_conditions_raw)s,
                    %(owner_team_id)s, %(franchise_id)s, %(operating_team_id)s
                )
                on conflict (edge_id) do update
                set asset_id = excluded.asset_id,
                    asset_key = excluded.asset_key,
                    source_system = excluded.source_system,
                    source_asset_ref = excluded.source_asset_ref,
                    asset_type = excluded.asset_type,
                    subtype = excluded.subtype,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    is_active_at_end = excluded.is_active_at_end,
                    player_name = excluded.player_name,
                    contract_expiry_year = excluded.contract_expiry_year,
                    average_annual_salary = excluded.average_annual_salary,
                    acquisition_method = excluded.acquisition_method,
                    prior_transactions = excluded.prior_transactions,
                    original_team = excluded.original_team,
                    pick_year = excluded.pick_year,
                    pick_round = excluded.pick_round,
                    pick_number = excluded.pick_number,
                    protections_raw = excluded.protections_raw,
                    swap_conditions_raw = excluded.swap_conditions_raw,
                    owner_team_id = excluded.owner_team_id,
                    franchise_id = excluded.franchise_id,
                    operating_team_id = excluded.operating_team_id,
                    updated_at = now()
            """
            for row in asset_rows:
                cur.execute(asset_sql, row)

            lineage_sql = """
                insert into silver.event_asset_lineage (
                    lineage_id, event_id, asset_id, action_raw, direction_raw, effective_date,
                    source_system, source_event_ref, source_asset_ref, source_link_id, franchise_id
                )
                values (
                    %(lineage_id)s, %(event_id)s, %(asset_id)s, %(action_raw)s, %(direction_raw)s, %(effective_date)s,
                    %(source_system)s, %(source_event_ref)s, %(source_asset_ref)s, %(source_link_id)s, %(franchise_id)s
                )
                on conflict (lineage_id) do update
                set event_id = excluded.event_id,
                    asset_id = excluded.asset_id,
                    action_raw = excluded.action_raw,
                    direction_raw = excluded.direction_raw,
                    effective_date = excluded.effective_date,
                    source_system = excluded.source_system,
                    source_event_ref = excluded.source_event_ref,
                    source_asset_ref = excluded.source_asset_ref,
                    source_link_id = excluded.source_link_id,
                    franchise_id = excluded.franchise_id
            """
            for row in lineage_rows:
                cur.execute(lineage_sql, row)
        conn.commit()

    manifest = {
        "stage": "silver_transform",
        "status": "success" if records_written > 0 else "no_new_data",
        "franchise_id": franchise_id,
        "run_mode": context["run_mode"],
        "as_of_date": context["as_of_date"],
        "records_seen": records_seen,
        "records_written": records_written,
        "events_written": len(event_rows),
        "assets_written": len(asset_rows),
        "lineage_written": len(lineage_rows),
        "links_skipped": skipped_links,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(manifest, sort_keys=True, default=str))
    return manifest
