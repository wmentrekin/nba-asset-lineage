from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from canonical.models import CanonicalAsset, CanonicalEvent
from db_config import load_database_url
from editorial.models import (
    EditorialAnnotation,
    EditorialBuild,
    EditorialCalendarMarker,
    EditorialEra,
    EditorialGameOverlay,
    EditorialOverlayBundle,
    EditorialOverlayBuildResult,
    EditorialStoryChapter,
)
from editorial.validate import validate_editorial_overlays
from shared.ids import stable_id, stable_payload_hash


def bootstrap_editorial_overlay_schema(sql_path: Path | str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required to bootstrap editorial overlay tables.") from exc

    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with psycopg.connect(load_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
        conn.commit()


def _connect():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for editorial overlay builds.") from exc
    return psycopg.connect(load_database_url())


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _json_ready(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=_json_default))


def _iter_editorial_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    patterns = ("stage7_editorial_*.yaml", "stage7_editorial_*.yml", "stage7_editorial_*.json")
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(root.rglob(pattern)))
    return files


def _load_structured_file(path: Path) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(raw_text)
    else:
        data = yaml.safe_load(raw_text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Editorial overlay file must contain a mapping at top level: {path}")
    if "editorial" in data and isinstance(data["editorial"], dict):
        return dict(data["editorial"])
    return data


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_string(value: Any, *, field_name: str, source: str) -> str:
    text = _string_or_none(value)
    if text is None:
        raise ValueError(f"{field_name} must be a non-empty string in {source}")
    return text


def _required_date(value: Any, *, field_name: str, source: str) -> date:
    text = _required_string(value, field_name=field_name, source=source)
    return date.fromisoformat(text)


def _required_int(value: Any, *, field_name: str, source: str) -> int:
    if value is None:
        raise ValueError(f"{field_name} must be provided in {source}")
    return int(value)


def _payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    return dict(value)


def _annotation_from_entry(entry: dict[str, Any], *, source: str) -> EditorialAnnotation:
    start_date = _required_date(entry.get("start_date"), field_name="start_date", source=source)
    end_date = _required_date(entry.get("end_date"), field_name="end_date", source=source)
    annotation_id = _string_or_none(entry.get("annotation_id")) or stable_id(
        "annotation",
        source,
        entry.get("annotation_type"),
        entry.get("title"),
        entry.get("body"),
        start_date.isoformat(),
        end_date.isoformat(),
        entry.get("event_id"),
        entry.get("asset_id"),
        entry.get("priority"),
    )
    return EditorialAnnotation(
        editorial_build_id="",
        annotation_id=annotation_id,
        annotation_type=_required_string(entry.get("annotation_type"), field_name="annotation_type", source=source),
        title=_required_string(entry.get("title"), field_name="title", source=source),
        body=_required_string(entry.get("body"), field_name="body", source=source),
        start_date=start_date,
        end_date=end_date,
        event_id=_string_or_none(entry.get("event_id")),
        asset_id=_string_or_none(entry.get("asset_id")),
        priority=_required_int(entry.get("priority"), field_name="priority", source=source),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def _calendar_marker_from_entry(entry: dict[str, Any], *, source: str) -> EditorialCalendarMarker:
    marker_date = _required_date(entry.get("marker_date"), field_name="marker_date", source=source)
    calendar_marker_id = _string_or_none(entry.get("calendar_marker_id")) or stable_id(
        "calendar_marker",
        source,
        entry.get("marker_type"),
        entry.get("label"),
        marker_date.isoformat(),
        entry.get("payload"),
    )
    return EditorialCalendarMarker(
        editorial_build_id="",
        calendar_marker_id=calendar_marker_id,
        marker_type=_required_string(entry.get("marker_type"), field_name="marker_type", source=source),
        label=_required_string(entry.get("label"), field_name="label", source=source),
        marker_date=marker_date,
        payload=_payload(entry.get("payload")),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def _game_overlay_from_entry(entry: dict[str, Any], *, source: str) -> EditorialGameOverlay:
    game_date = _required_date(entry.get("game_date"), field_name="game_date", source=source)
    game_overlay_id = _string_or_none(entry.get("game_overlay_id")) or stable_id(
        "game_overlay",
        source,
        game_date.isoformat(),
        entry.get("opponent"),
        entry.get("home_away"),
        entry.get("result"),
        entry.get("score_display"),
        entry.get("payload"),
    )
    return EditorialGameOverlay(
        editorial_build_id="",
        game_overlay_id=game_overlay_id,
        game_date=game_date,
        opponent=_required_string(entry.get("opponent"), field_name="opponent", source=source),
        home_away=_required_string(entry.get("home_away"), field_name="home_away", source=source),
        result=_required_string(entry.get("result"), field_name="result", source=source),
        score_display=_required_string(entry.get("score_display"), field_name="score_display", source=source),
        payload=_payload(entry.get("payload")),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def _era_from_entry(entry: dict[str, Any], *, source: str) -> EditorialEra:
    start_date = _required_date(entry.get("start_date"), field_name="start_date", source=source)
    end_date = _required_date(entry.get("end_date"), field_name="end_date", source=source)
    era_id = _string_or_none(entry.get("era_id")) or stable_id(
        "era",
        source,
        entry.get("title"),
        start_date.isoformat(),
        end_date.isoformat(),
    )
    return EditorialEra(
        editorial_build_id="",
        era_id=era_id,
        title=_required_string(entry.get("title"), field_name="title", source=source),
        start_date=start_date,
        end_date=end_date,
        description=_required_string(entry.get("description"), field_name="description", source=source),
        priority=_required_int(entry.get("priority"), field_name="priority", source=source),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def _story_chapter_from_entry(entry: dict[str, Any], *, source: str) -> EditorialStoryChapter:
    start_date = _required_date(entry.get("start_date"), field_name="start_date", source=source)
    end_date = _required_date(entry.get("end_date"), field_name="end_date", source=source)
    chapter_order = _required_int(entry.get("chapter_order"), field_name="chapter_order", source=source)
    story_chapter_id = _string_or_none(entry.get("story_chapter_id")) or stable_id(
        "story_chapter",
        source,
        entry.get("slug"),
        chapter_order,
        entry.get("title"),
        start_date.isoformat(),
        end_date.isoformat(),
    )
    return EditorialStoryChapter(
        editorial_build_id="",
        story_chapter_id=story_chapter_id,
        slug=_required_string(entry.get("slug"), field_name="slug", source=source),
        chapter_order=chapter_order,
        title=_required_string(entry.get("title"), field_name="title", source=source),
        body=_required_string(entry.get("body"), field_name="body", source=source),
        start_date=start_date,
        end_date=end_date,
        focus_payload=_payload(entry.get("focus_payload")),
        era_id=_string_or_none(entry.get("era_id")),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def load_editorial_bundle(root: Path | str, *, default_source_label: str = "local") -> EditorialOverlayBundle:
    root_path = Path(root)
    annotations: list[EditorialAnnotation] = []
    calendar_markers: list[EditorialCalendarMarker] = []
    game_overlays: list[EditorialGameOverlay] = []
    eras: list[EditorialEra] = []
    story_chapters: list[EditorialStoryChapter] = []

    for path in _iter_editorial_files(root_path):
        payload = _load_structured_file(path)
        source_label = str(path.relative_to(root_path)) if root_path.exists() and root_path.is_dir() else str(path)
        if not payload:
            continue
        for entry in payload.get("annotations", []):
            annotations.append(_annotation_from_entry(dict(entry), source=source_label or default_source_label))
        for entry in payload.get("calendar_markers", []):
            calendar_markers.append(_calendar_marker_from_entry(dict(entry), source=source_label or default_source_label))
        for entry in payload.get("game_overlays", []):
            game_overlays.append(_game_overlay_from_entry(dict(entry), source=source_label or default_source_label))
        for entry in payload.get("eras", []):
            eras.append(_era_from_entry(dict(entry), source=source_label or default_source_label))
        for entry in payload.get("story_chapters", []):
            story_chapters.append(_story_chapter_from_entry(dict(entry), source=source_label or default_source_label))

    return EditorialOverlayBundle(
        annotations=annotations,
        calendar_markers=calendar_markers,
        game_overlays=game_overlays,
        eras=eras,
        story_chapters=story_chapters,
    )


def _sorted_bundle(bundle: EditorialOverlayBundle) -> EditorialOverlayBundle:
    return EditorialOverlayBundle(
        annotations=sorted(bundle.annotations, key=lambda row: (row.start_date, row.end_date, row.priority, row.annotation_id)),
        calendar_markers=sorted(bundle.calendar_markers, key=lambda row: (row.marker_date, row.calendar_marker_id)),
        game_overlays=sorted(bundle.game_overlays, key=lambda row: (row.game_date, row.game_overlay_id)),
        eras=sorted(bundle.eras, key=lambda row: (row.start_date, row.end_date, row.priority, row.era_id)),
        story_chapters=sorted(bundle.story_chapters, key=lambda row: (row.chapter_order, row.start_date, row.story_chapter_id)),
    )


def build_editorial_overlays(
    bundle: EditorialOverlayBundle,
    *,
    builder_version: str = "stage7-editorial-overlay-v1",
    presentation_build_id: str | None = None,
    built_at: datetime | None = None,
) -> EditorialOverlayBuildResult:
    built_at_value = built_at or datetime.utcnow()
    normalized_bundle = _sorted_bundle(bundle)
    input_hash = stable_payload_hash(
        {
            "annotation_ids": [row.annotation_id for row in normalized_bundle.annotations],
            "calendar_marker_ids": [row.calendar_marker_id for row in normalized_bundle.calendar_markers],
            "game_overlay_ids": [row.game_overlay_id for row in normalized_bundle.game_overlays],
            "era_ids": [row.era_id for row in normalized_bundle.eras],
            "story_chapter_ids": [row.story_chapter_id for row in normalized_bundle.story_chapters],
        }
    )
    build = EditorialBuild(
        editorial_build_id=stable_id(
            "editorial_build",
            builder_version,
            built_at_value.isoformat(),
            presentation_build_id or input_hash,
        ),
        built_at=built_at_value,
        builder_version=builder_version,
        presentation_build_id=presentation_build_id,
        notes="Stage 7 editorial overlay build",
    )
    return EditorialOverlayBuildResult(
        build=build,
        annotations=[replace(row, editorial_build_id=build.editorial_build_id) for row in normalized_bundle.annotations],
        calendar_markers=[replace(row, editorial_build_id=build.editorial_build_id) for row in normalized_bundle.calendar_markers],
        game_overlays=[replace(row, editorial_build_id=build.editorial_build_id) for row in normalized_bundle.game_overlays],
        eras=[replace(row, editorial_build_id=build.editorial_build_id) for row in normalized_bundle.eras],
        story_chapters=[replace(row, editorial_build_id=build.editorial_build_id) for row in normalized_bundle.story_chapters],
    )


def _fetch_latest_presentation_build_id(conn: Any) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select presentation_build_id
            from presentation.builds
            order by built_at desc, presentation_build_id desc
            limit 1
            """
        )
        row = cur.fetchone()
    return row[0] if row else None


def persist_editorial_overlay_build(conn: Any, result: EditorialOverlayBuildResult) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into editorial.builds (
                editorial_build_id,
                built_at,
                builder_version,
                presentation_build_id,
                notes
            )
            values (%s, %s, %s, %s, %s)
            on conflict (editorial_build_id) do update set
                built_at = excluded.built_at,
                builder_version = excluded.builder_version,
                presentation_build_id = excluded.presentation_build_id,
                notes = excluded.notes
            """,
            (
                result.build.editorial_build_id,
                result.build.built_at,
                result.build.builder_version,
                result.build.presentation_build_id,
                result.build.notes,
            ),
        )
        for row in result.annotations:
            cur.execute(
                """
                insert into editorial.annotations (
                    editorial_build_id,
                    annotation_id,
                    annotation_type,
                    title,
                    body,
                    start_date,
                    end_date,
                    event_id,
                    asset_id,
                    priority,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (editorial_build_id, annotation_id) do update set
                    annotation_type = excluded.annotation_type,
                    title = excluded.title,
                    body = excluded.body,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    event_id = excluded.event_id,
                    asset_id = excluded.asset_id,
                    priority = excluded.priority,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    row.editorial_build_id,
                    row.annotation_id,
                    row.annotation_type,
                    row.title,
                    row.body,
                    row.start_date,
                    row.end_date,
                    row.event_id,
                    row.asset_id,
                    row.priority,
                    row.created_at,
                    row.updated_at,
                ),
            )
        for row in result.calendar_markers:
            cur.execute(
                """
                insert into editorial.calendar_markers (
                    editorial_build_id,
                    calendar_marker_id,
                    marker_type,
                    label,
                    marker_date,
                    payload,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                on conflict (editorial_build_id, calendar_marker_id) do update set
                    marker_type = excluded.marker_type,
                    label = excluded.label,
                    marker_date = excluded.marker_date,
                    payload = excluded.payload,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    row.editorial_build_id,
                    row.calendar_marker_id,
                    row.marker_type,
                    row.label,
                    row.marker_date,
                    json.dumps(_json_ready(row.payload), sort_keys=True),
                    row.created_at,
                    row.updated_at,
                ),
            )
        for row in result.game_overlays:
            cur.execute(
                """
                insert into editorial.game_overlays (
                    editorial_build_id,
                    game_overlay_id,
                    game_date,
                    opponent,
                    home_away,
                    result,
                    score_display,
                    payload,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                on conflict (editorial_build_id, game_overlay_id) do update set
                    game_date = excluded.game_date,
                    opponent = excluded.opponent,
                    home_away = excluded.home_away,
                    result = excluded.result,
                    score_display = excluded.score_display,
                    payload = excluded.payload,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    row.editorial_build_id,
                    row.game_overlay_id,
                    row.game_date,
                    row.opponent,
                    row.home_away,
                    row.result,
                    row.score_display,
                    json.dumps(_json_ready(row.payload), sort_keys=True),
                    row.created_at,
                    row.updated_at,
                ),
            )
        for row in result.eras:
            cur.execute(
                """
                insert into editorial.eras (
                    editorial_build_id,
                    era_id,
                    title,
                    start_date,
                    end_date,
                    description,
                    priority,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (editorial_build_id, era_id) do update set
                    title = excluded.title,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    description = excluded.description,
                    priority = excluded.priority,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    row.editorial_build_id,
                    row.era_id,
                    row.title,
                    row.start_date,
                    row.end_date,
                    row.description,
                    row.priority,
                    row.created_at,
                    row.updated_at,
                ),
            )
        for row in result.story_chapters:
            cur.execute(
                """
                insert into editorial.story_chapters (
                    editorial_build_id,
                    story_chapter_id,
                    slug,
                    chapter_order,
                    title,
                    body,
                    start_date,
                    end_date,
                    era_id,
                    focus_payload,
                    created_at,
                    updated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                on conflict (editorial_build_id, story_chapter_id) do update set
                    slug = excluded.slug,
                    chapter_order = excluded.chapter_order,
                    title = excluded.title,
                    body = excluded.body,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    era_id = excluded.era_id,
                    focus_payload = excluded.focus_payload,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    row.editorial_build_id,
                    row.story_chapter_id,
                    row.slug,
                    row.chapter_order,
                    row.title,
                    row.body,
                    row.start_date,
                    row.end_date,
                    row.era_id,
                    json.dumps(_json_ready(row.focus_payload), sort_keys=True),
                    row.created_at,
                    row.updated_at,
                ),
            )
    return result.counts()


def build_and_persist_editorial_overlays(
    *,
    input_path: Path | str = Path("configs/data"),
    builder_version: str = "stage7-editorial-overlay-v1",
    presentation_build_id: str | None = None,
) -> dict[str, int]:
    bundle = load_editorial_bundle(input_path)
    with _connect() as conn:
        presentation_build_id_value = presentation_build_id or _fetch_latest_presentation_build_id(conn)
        result = build_editorial_overlays(
            bundle,
            builder_version=builder_version,
            presentation_build_id=presentation_build_id_value,
        )
        counts = persist_editorial_overlay_build(conn, result)
        conn.commit()
    return counts


def fetch_editorial_overlays(conn: Any, editorial_build_id: str | None = None) -> EditorialOverlayBuildResult:
    with conn.cursor() as cur:
        if editorial_build_id is None:
            cur.execute(
                """
                select
                    editorial_build_id,
                    built_at,
                    builder_version,
                    presentation_build_id,
                    notes
                from editorial.builds
                order by built_at desc, editorial_build_id desc
                limit 1
                """
            )
        else:
            cur.execute(
                """
                select
                    editorial_build_id,
                    built_at,
                    builder_version,
                    presentation_build_id,
                    notes
                from editorial.builds
                where editorial_build_id = %s
                """,
                (editorial_build_id,),
            )
        build_row = cur.fetchone()
        if build_row is None:
            raise RuntimeError("no editorial build found")
        editorial_build_id_value = build_row[0]
        cur.execute(
            """
            select
                editorial_build_id,
                annotation_id,
                annotation_type,
                title,
                body,
                start_date,
                end_date,
                event_id,
                asset_id,
                priority,
                created_at,
                updated_at
            from editorial.annotations
            where editorial_build_id = %s
            order by start_date, end_date, priority desc, annotation_id
            """,
            (editorial_build_id_value,),
        )
        annotation_rows = cur.fetchall()
        cur.execute(
            """
            select
                editorial_build_id,
                calendar_marker_id,
                marker_type,
                label,
                marker_date,
                payload,
                created_at,
                updated_at
            from editorial.calendar_markers
            where editorial_build_id = %s
            order by marker_date, calendar_marker_id
            """,
            (editorial_build_id_value,),
        )
        marker_rows = cur.fetchall()
        cur.execute(
            """
            select
                editorial_build_id,
                game_overlay_id,
                game_date,
                opponent,
                home_away,
                result,
                score_display,
                payload,
                created_at,
                updated_at
            from editorial.game_overlays
            where editorial_build_id = %s
            order by game_date, game_overlay_id
            """,
            (editorial_build_id_value,),
        )
        game_rows = cur.fetchall()
        cur.execute(
            """
            select
                editorial_build_id,
                era_id,
                title,
                start_date,
                end_date,
                description,
                priority,
                created_at,
                updated_at
            from editorial.eras
            where editorial_build_id = %s
            order by start_date, end_date, priority desc, era_id
            """,
            (editorial_build_id_value,),
        )
        era_rows = cur.fetchall()
        cur.execute(
            """
            select
                editorial_build_id,
                story_chapter_id,
                slug,
                chapter_order,
                title,
                body,
                start_date,
                end_date,
                era_id,
                focus_payload,
                created_at,
                updated_at
            from editorial.story_chapters
            where editorial_build_id = %s
            order by chapter_order, start_date, story_chapter_id
            """,
            (editorial_build_id_value,),
        )
        story_rows = cur.fetchall()

    build = EditorialBuild(
        editorial_build_id=build_row[0],
        built_at=build_row[1],
        builder_version=build_row[2],
        presentation_build_id=build_row[3],
        notes=build_row[4],
    )
    annotations = [
        EditorialAnnotation(
            editorial_build_id=row[0],
            annotation_id=row[1],
            annotation_type=row[2],
            title=row[3],
            body=row[4],
            start_date=row[5],
            end_date=row[6],
            event_id=row[7],
            asset_id=row[8],
            priority=row[9],
            created_at=row[10],
            updated_at=row[11],
        )
        for row in annotation_rows
    ]
    calendar_markers = [
        EditorialCalendarMarker(
            editorial_build_id=row[0],
            calendar_marker_id=row[1],
            marker_type=row[2],
            label=row[3],
            marker_date=row[4],
            payload=row[5],
            created_at=row[6],
            updated_at=row[7],
        )
        for row in marker_rows
    ]
    game_overlays = [
        EditorialGameOverlay(
            editorial_build_id=row[0],
            game_overlay_id=row[1],
            game_date=row[2],
            opponent=row[3],
            home_away=row[4],
            result=row[5],
            score_display=row[6],
            payload=row[7],
            created_at=row[8],
            updated_at=row[9],
        )
        for row in game_rows
    ]
    eras = [
        EditorialEra(
            editorial_build_id=row[0],
            era_id=row[1],
            title=row[2],
            start_date=row[3],
            end_date=row[4],
            description=row[5],
            priority=row[6],
            created_at=row[7],
            updated_at=row[8],
        )
        for row in era_rows
    ]
    story_chapters = [
        EditorialStoryChapter(
            editorial_build_id=row[0],
            story_chapter_id=row[1],
            slug=row[2],
            chapter_order=row[3],
            title=row[4],
            body=row[5],
            start_date=row[6],
            end_date=row[7],
            era_id=row[8],
            focus_payload=row[9],
            created_at=row[10],
            updated_at=row[11],
        )
        for row in story_rows
    ]
    return EditorialOverlayBuildResult(
        build=build,
        annotations=annotations,
        calendar_markers=calendar_markers,
        game_overlays=game_overlays,
        eras=eras,
        story_chapters=story_chapters,
    )


def editorial_overlays_to_json(result: EditorialOverlayBuildResult) -> str:
    return json.dumps(_json_ready(result.as_contract()), sort_keys=True, indent=2)


def export_editorial_overlays_json(output_path: Path | str | None = None) -> str:
    with _connect() as conn:
        result = fetch_editorial_overlays(conn)
    payload = editorial_overlays_to_json(result)
    if output_path is not None:
        Path(output_path).write_text(payload + "\n", encoding="utf-8")
    return payload


def validate_editorial_overlay_bundle(
    bundle: EditorialOverlayBundle,
    *,
    canonical_events: Iterable[CanonicalEvent] = (),
    canonical_assets: Iterable[CanonicalAsset] = (),
) -> Any:
    return validate_editorial_overlays(
        annotations=bundle.annotations,
        calendar_markers=bundle.calendar_markers,
        game_overlays=bundle.game_overlays,
        eras=bundle.eras,
        story_chapters=bundle.story_chapters,
        canonical_events=canonical_events,
        canonical_assets=canonical_assets,
    )
