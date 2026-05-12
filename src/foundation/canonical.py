from __future__ import annotations

import hashlib
from pathlib import Path

import psycopg
from pydantic import BaseModel

from foundation.ingest import (
    SourceEventRow,
    build_pick_id,
    load_player_aliases_from_database,
    load_source_events_from_database,
    normalize_player_alias_name,
    slugify,
)


FOUNDATION_CANONICAL_BOOTSTRAP_SQL_PATH = Path("sql/0002_foundation_canonical_bootstrap.sql")


class CanonicalEventRow(BaseModel):
    canonical_event_id: str
    event_date: str
    event_type: str
    label: str
    sequence_on_date: int
    is_grouped_event: bool


class CanonicalEventMemberRow(BaseModel):
    canonical_event_id: str
    source_event_id: str


class EventAssetTransitionRow(BaseModel):
    transition_id: str
    canonical_event_id: str
    asset_id: str
    transition_type: str
    direction: str


class FoundationCanonicalBundle(BaseModel):
    canonical_events: list[CanonicalEventRow]
    canonical_event_members: list[CanonicalEventMemberRow]
    event_asset_transitions: list[EventAssetTransitionRow]


def bootstrap_foundation_canonical_schema(
    database_url: str,
    sql_path: Path = FOUNDATION_CANONICAL_BOOTSTRAP_SQL_PATH,
) -> None:
    sql_text = sql_path.read_text(encoding="utf-8")
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql_text)
        connection.commit()


def derive_foundation_canonical_bundle_from_database(database_url: str) -> FoundationCanonicalBundle:
    source_events = load_source_events_from_database(database_url)
    player_aliases = load_player_aliases_from_database(database_url)
    player_id_by_alias = {alias.normalized_alias_name: alias.player_id for alias in player_aliases}
    return derive_foundation_canonical_bundle(source_events, player_id_by_alias=player_id_by_alias)


def derive_foundation_canonical_bundle(
    source_events: list[SourceEventRow],
    *,
    player_id_by_alias: dict[str, str] | None = None,
) -> FoundationCanonicalBundle:
    groups = group_source_events(source_events)
    canonical_events: list[CanonicalEventRow] = []
    canonical_event_members: list[CanonicalEventMemberRow] = []
    event_asset_transitions: list[EventAssetTransitionRow] = []

    grouped_by_date: dict[str, list[list[SourceEventRow]]] = {}
    for group in groups:
        grouped_by_date.setdefault(group[0].event_date, []).append(group)

    for event_date in sorted(grouped_by_date):
        date_groups = sorted(
            grouped_by_date[event_date],
            key=lambda group: (canonicalize_event_type(group[0].event_type), group[0].source_event_id),
        )
        for sequence_on_date, group in enumerate(date_groups, start=1):
            canonical_event = build_canonical_event(group, sequence_on_date=sequence_on_date)
            canonical_events.append(canonical_event)
            for source_event in group:
                canonical_event_members.append(
                    CanonicalEventMemberRow(
                        canonical_event_id=canonical_event.canonical_event_id,
                        source_event_id=source_event.source_event_id,
                    )
                )
            event_asset_transitions.extend(
                build_event_asset_transitions(
                    canonical_event,
                    group,
                    player_id_by_alias=player_id_by_alias or {},
                )
            )

    return FoundationCanonicalBundle(
        canonical_events=canonical_events,
        canonical_event_members=canonical_event_members,
        event_asset_transitions=event_asset_transitions,
    )


def derive_canonical_layer_from_source_events(
    *,
    source_events: list[SourceEventRow],
    players: object | None = None,
    picks: object | None = None,
    assets: object | None = None,
) -> FoundationCanonicalBundle:
    _ = players, picks, assets
    return derive_foundation_canonical_bundle(source_events)


def build_canonical_layer_from_source_events(
    *,
    source_events: list[SourceEventRow],
    players: object | None = None,
    picks: object | None = None,
    assets: object | None = None,
) -> FoundationCanonicalBundle:
    return derive_canonical_layer_from_source_events(
        source_events=source_events,
        players=players,
        picks=picks,
        assets=assets,
    )


def load_foundation_canonical_bundle(database_url: str) -> dict[str, int]:
    bundle = derive_foundation_canonical_bundle_from_database(database_url)
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        upsert_canonical_events(connection, bundle.canonical_events)
        upsert_canonical_event_members(connection, bundle.canonical_event_members)
        upsert_event_asset_transitions(connection, bundle.event_asset_transitions)
        connection.commit()
    return {
        "canonical_events": len(bundle.canonical_events),
        "canonical_event_members": len(bundle.canonical_event_members),
        "event_asset_transitions": len(bundle.event_asset_transitions),
    }


def group_source_events(source_events: list[SourceEventRow]) -> list[list[SourceEventRow]]:
    grouped: dict[tuple[str, ...], list[SourceEventRow]] = {}
    order: list[tuple[str, ...]] = []
    for source_event in source_events:
        key = build_group_key(source_event)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(source_event)
    return [grouped[key] for key in order]


def build_group_key(source_event: SourceEventRow) -> tuple[str, ...]:
    if source_event.event_type == "trade" and source_event.source_group_hint:
        return (
            source_event.event_date,
            source_event.team_scope,
            source_event.event_type,
            source_event.source_group_hint,
        )
    return ("single", source_event.source_event_id)


def canonicalize_event_type(source_event_type: str) -> str:
    if source_event_type in {"trade", "draft", "waiver", "signing"}:
        return source_event_type
    if source_event_type in {"re_signing", "extension", "conversion"}:
        return "signing"
    if source_event_type == "release":
        return "waiver"
    raise ValueError(f"Unsupported source event type for canonicalization: {source_event_type}")


def build_canonical_event(group: list[SourceEventRow], *, sequence_on_date: int) -> CanonicalEventRow:
    first = group[0]
    canonical_event_type = canonicalize_event_type(first.event_type)
    member_ids = ",".join(source_event.source_event_id for source_event in group)
    digest = hashlib.sha1(member_ids.encode("utf-8")).hexdigest()[:12]
    canonical_event_id = f"canonical:{first.event_date}:{canonical_event_type}:{digest}"
    label = first.label if len(group) == 1 else f"Memphis grouped trade"
    return CanonicalEventRow(
        canonical_event_id=canonical_event_id,
        event_date=first.event_date,
        event_type=canonical_event_type,
        label=label,
        sequence_on_date=sequence_on_date,
        is_grouped_event=len(group) > 1,
    )


def build_event_asset_transitions(
    canonical_event: CanonicalEventRow,
    group: list[SourceEventRow],
    *,
    player_id_by_alias: dict[str, str] | None = None,
) -> list[EventAssetTransitionRow]:
    inbound_assets: set[str] = set()
    outbound_assets: set[str] = set()
    alias_lookup = player_id_by_alias or {}

    for source_event in group:
        payload = source_event.normalized_payload
        for player_name in payload.get("player_names_in", []):
            if isinstance(player_name, str) and player_name.strip():
                inbound_assets.add(build_player_asset_id(player_name, player_id_by_alias=alias_lookup))
        for player_name in payload.get("player_names_out", []):
            if isinstance(player_name, str) and player_name.strip():
                outbound_assets.add(build_player_asset_id(player_name, player_id_by_alias=alias_lookup))
        for detail in payload.get("pick_details_in", []):
            raw_text = detail.get("raw_text") if is_normalized_pick_detail(detail) else None
            if isinstance(raw_text, str):
                inbound_assets.add(build_pick_asset_id(raw_text))
        for detail in payload.get("pick_details_out", []):
            raw_text = detail.get("raw_text") if is_normalized_pick_detail(detail) else None
            if isinstance(raw_text, str):
                outbound_assets.add(build_pick_asset_id(raw_text))

    transitions: list[EventAssetTransitionRow] = []
    for asset_id in sorted(inbound_assets - outbound_assets):
        transitions.append(
            EventAssetTransitionRow(
                transition_id=f"{canonical_event.canonical_event_id}:in:{asset_id}",
                canonical_event_id=canonical_event.canonical_event_id,
                asset_id=asset_id,
                transition_type="acquired",
                direction="in",
            )
        )
    for asset_id in sorted(outbound_assets - inbound_assets):
        transitions.append(
            EventAssetTransitionRow(
                transition_id=f"{canonical_event.canonical_event_id}:out:{asset_id}",
                canonical_event_id=canonical_event.canonical_event_id,
                asset_id=asset_id,
                transition_type="departed",
                direction="out",
            )
        )
    return transitions


def build_player_asset_id(display_name: str, *, player_id_by_alias: dict[str, str] | None = None) -> str:
    player_id = (player_id_by_alias or {}).get(normalize_player_alias_name(display_name))
    if player_id and player_id.startswith("player:"):
        return f"asset:player:{player_id.removeprefix('player:')}"
    return f"asset:player:{slugify(display_name)}"


def build_pick_asset_id(raw_text: str) -> str:
    return f"asset:pick:{build_pick_id(raw_text)}"


def is_normalized_pick_detail(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        isinstance(value.get("raw_text"), str)
        and bool(str(value.get("raw_text")).strip())
        and isinstance(value.get("draft_year"), int)
        and isinstance(value.get("round_number"), int)
    )


def upsert_canonical_events(connection: psycopg.Connection, rows: list[CanonicalEventRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.canonical_event (
                    canonical_event_id, event_date, event_type, label, sequence_on_date, is_grouped_event
                ) values (%s, %s, %s, %s, %s, %s)
                on conflict (canonical_event_id) do update
                set event_date = excluded.event_date,
                    event_type = excluded.event_type,
                    label = excluded.label,
                    sequence_on_date = excluded.sequence_on_date,
                    is_grouped_event = excluded.is_grouped_event
                """,
                (
                    row.canonical_event_id,
                    row.event_date,
                    row.event_type,
                    row.label,
                    row.sequence_on_date,
                    row.is_grouped_event,
                ),
            )


def upsert_canonical_event_members(connection: psycopg.Connection, rows: list[CanonicalEventMemberRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.canonical_event_member (
                    canonical_event_id, source_event_id
                ) values (%s, %s)
                on conflict (canonical_event_id, source_event_id) do nothing
                """,
                (row.canonical_event_id, row.source_event_id),
            )


def upsert_event_asset_transitions(connection: psycopg.Connection, rows: list[EventAssetTransitionRow]) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            cursor.execute(
                """
                insert into foundation.event_asset_transition (
                    transition_id, canonical_event_id, asset_id, transition_type, direction
                ) values (%s, %s, %s, %s, %s)
                on conflict (transition_id) do update
                set canonical_event_id = excluded.canonical_event_id,
                    asset_id = excluded.asset_id,
                    transition_type = excluded.transition_type,
                    direction = excluded.direction
                """,
                (
                    row.transition_id,
                    row.canonical_event_id,
                    row.asset_id,
                    row.transition_type,
                    row.direction,
                ),
            )
