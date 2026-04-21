from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from canonical.models import CanonicalAsset, CanonicalEvent
from editorial.models import (
    EditorialAnnotation,
    EditorialCalendarMarker,
    EditorialEra,
    EditorialGameOverlay,
    EditorialStoryChapter,
)


ALLOWED_LANE_GROUPS = {"main_roster", "two_way", "future_picks"}
HIGH_PRIORITY_THRESHOLD = 80


@dataclass(frozen=True)
class EditorialOverlayValidationReport:
    annotation_count: int
    calendar_marker_count: int
    game_overlay_count: int
    era_count: int
    story_chapter_count: int
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _date_interval_overlaps(left_start: date, left_end: date, right_start: date, right_end: date) -> bool:
    return left_start <= right_end and right_start <= left_end


def _reference_sets(
    canonical_events: Iterable[CanonicalEvent],
    canonical_assets: Iterable[CanonicalAsset],
    eras: Iterable[EditorialEra],
    annotations: Iterable[EditorialAnnotation],
) -> tuple[set[str], set[str], set[str], set[str]]:
    return (
        {row.event_id for row in canonical_events},
        {row.asset_id for row in canonical_assets},
        {row.era_id for row in eras},
        {row.annotation_id for row in annotations},
    )


def _focus_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"focus_payload.{key} must be a list")
    result: list[str] = []
    for entry in value:
        text = str(entry).strip()
        if not text:
            raise ValueError(f"focus_payload.{key} must not contain blank values")
        result.append(text)
    return result


def validate_editorial_overlays(
    *,
    annotations: Iterable[EditorialAnnotation],
    calendar_markers: Iterable[EditorialCalendarMarker],
    game_overlays: Iterable[EditorialGameOverlay],
    eras: Iterable[EditorialEra],
    story_chapters: Iterable[EditorialStoryChapter],
    canonical_events: Iterable[CanonicalEvent] = (),
    canonical_assets: Iterable[CanonicalAsset] = (),
) -> EditorialOverlayValidationReport:
    annotations_list = list(annotations)
    calendar_markers_list = list(calendar_markers)
    game_overlays_list = list(game_overlays)
    eras_list = list(eras)
    story_chapters_list = list(story_chapters)
    canonical_events_list = list(canonical_events)
    canonical_assets_list = list(canonical_assets)

    errors: list[str] = []
    warnings: list[str] = []

    duplicate_annotation_ids = [row_id for row_id, count in Counter(row.annotation_id for row in annotations_list).items() if count > 1]
    if duplicate_annotation_ids:
        errors.append(f"duplicate annotation_ids: {', '.join(sorted(duplicate_annotation_ids))}")

    duplicate_calendar_marker_ids = [row_id for row_id, count in Counter(row.calendar_marker_id for row in calendar_markers_list).items() if count > 1]
    if duplicate_calendar_marker_ids:
        errors.append(f"duplicate calendar_marker_ids: {', '.join(sorted(duplicate_calendar_marker_ids))}")

    duplicate_game_overlay_ids = [row_id for row_id, count in Counter(row.game_overlay_id for row in game_overlays_list).items() if count > 1]
    if duplicate_game_overlay_ids:
        errors.append(f"duplicate game_overlay_ids: {', '.join(sorted(duplicate_game_overlay_ids))}")

    duplicate_era_ids = [row_id for row_id, count in Counter(row.era_id for row in eras_list).items() if count > 1]
    if duplicate_era_ids:
        errors.append(f"duplicate era_ids: {', '.join(sorted(duplicate_era_ids))}")

    duplicate_chapter_ids = [row_id for row_id, count in Counter(row.story_chapter_id for row in story_chapters_list).items() if count > 1]
    if duplicate_chapter_ids:
        errors.append(f"duplicate story_chapter_ids: {', '.join(sorted(duplicate_chapter_ids))}")

    canonical_event_ids, asset_ids, era_ids, chapter_annotation_ids = _reference_sets(
        canonical_events_list,
        canonical_assets_list,
        eras_list,
        annotations_list,
    )

    for annotation in annotations_list:
        if annotation.end_date < annotation.start_date:
            errors.append(f"annotation end_date before start_date: {annotation.annotation_id}")
        if annotation.priority < 0:
            errors.append(f"annotation priority must be non-negative: {annotation.annotation_id}")
        if not annotation.annotation_type.strip():
            errors.append(f"annotation type must be non-empty: {annotation.annotation_id}")
        if not annotation.title.strip():
            errors.append(f"annotation title must be non-empty: {annotation.annotation_id}")
        if not annotation.body.strip():
            errors.append(f"annotation body must be non-empty: {annotation.annotation_id}")
        if annotation.event_id is not None and annotation.event_id not in canonical_event_ids:
            errors.append(f"annotation references unknown event_id: {annotation.annotation_id}/{annotation.event_id}")
        if annotation.asset_id is not None and annotation.asset_id not in asset_ids:
            errors.append(f"annotation references unknown asset_id: {annotation.annotation_id}/{annotation.asset_id}")
        if annotation.event_id is not None:
            event = next((row for row in canonical_events_list if row.event_id == annotation.event_id), None)
            if event is not None and not (annotation.start_date <= event.event_date <= annotation.end_date):
                errors.append(f"annotation event date outside annotation range: {annotation.annotation_id}")

    for marker in calendar_markers_list:
        if not marker.marker_type.strip():
            errors.append(f"calendar marker_type must be non-empty: {marker.calendar_marker_id}")
        if not marker.label.strip():
            errors.append(f"calendar marker label must be non-empty: {marker.calendar_marker_id}")

    for overlay in game_overlays_list:
        if not overlay.opponent.strip():
            errors.append(f"game overlay opponent must be non-empty: {overlay.game_overlay_id}")
        if overlay.home_away.strip().lower() not in {"home", "away"}:
            errors.append(f"game overlay home_away must be home or away: {overlay.game_overlay_id}")
        if not overlay.result.strip():
            errors.append(f"game overlay result must be non-empty: {overlay.game_overlay_id}")
        if not overlay.score_display.strip():
            errors.append(f"game overlay score_display must be non-empty: {overlay.game_overlay_id}")

    for era in eras_list:
        if era.end_date < era.start_date:
            errors.append(f"era end_date before start_date: {era.era_id}")
        if era.priority < 0:
            errors.append(f"era priority must be non-negative: {era.era_id}")
        if not era.title.strip():
            errors.append(f"era title must be non-empty: {era.era_id}")

    chapter_orders = [row.chapter_order for row in story_chapters_list]
    duplicate_chapter_orders = [order for order, count in Counter(chapter_orders).items() if count > 1]
    if duplicate_chapter_orders:
        errors.append(f"duplicate story_chapter chapter_order values: {', '.join(str(order) for order in sorted(duplicate_chapter_orders))}")

    for chapter in story_chapters_list:
        if chapter.end_date < chapter.start_date:
            errors.append(f"story chapter end_date before start_date: {chapter.story_chapter_id}")
        if not chapter.slug.strip():
            errors.append(f"story chapter slug must be non-empty: {chapter.story_chapter_id}")
        if not chapter.title.strip():
            errors.append(f"story chapter title must be non-empty: {chapter.story_chapter_id}")
        if not chapter.body.strip():
            errors.append(f"story chapter body must be non-empty: {chapter.story_chapter_id}")
        if not isinstance(chapter.focus_payload, dict):
            errors.append(f"story chapter focus_payload must be an object: {chapter.story_chapter_id}")
            continue
        focus_payload = chapter.focus_payload
        if "date_range" in focus_payload:
            date_range = focus_payload.get("date_range")
            if not isinstance(date_range, dict):
                errors.append(f"story chapter focus_payload.date_range must be an object: {chapter.story_chapter_id}")
            else:
                start_value = str(date_range.get("start_date") or "").strip()
                end_value = str(date_range.get("end_date") or "").strip()
                if not start_value or not end_value:
                    errors.append(f"story chapter focus_payload.date_range requires start_date and end_date: {chapter.story_chapter_id}")
                else:
                    try:
                        start_date = date.fromisoformat(start_value)
                        end_date = date.fromisoformat(end_value)
                    except ValueError:
                        errors.append(f"story chapter focus_payload.date_range must use ISO dates: {chapter.story_chapter_id}")
                    else:
                        if end_date < start_date:
                            errors.append(f"story chapter focus_payload.date_range end before start: {chapter.story_chapter_id}")

        for event_id in _focus_list(focus_payload, "event_ids"):
            if event_id not in canonical_event_ids:
                errors.append(f"story chapter references unknown event_id: {chapter.story_chapter_id}/{event_id}")

        for asset_id in _focus_list(focus_payload, "asset_ids"):
            if asset_id not in asset_ids:
                errors.append(f"story chapter references unknown asset_id: {chapter.story_chapter_id}/{asset_id}")

        for lane_group in _focus_list(focus_payload, "lane_groups"):
            if lane_group not in ALLOWED_LANE_GROUPS:
                errors.append(f"story chapter references unknown lane_group: {chapter.story_chapter_id}/{lane_group}")

        for annotation_id in _focus_list(focus_payload, "annotation_ids"):
            if annotation_id not in chapter_annotation_ids:
                errors.append(f"story chapter references unknown annotation_id: {chapter.story_chapter_id}/{annotation_id}")

        if chapter.era_id is not None and chapter.era_id not in era_ids:
            errors.append(f"story chapter references unknown era_id: {chapter.story_chapter_id}/{chapter.era_id}")

    high_priority_annotations = [row for row in annotations_list if row.priority >= HIGH_PRIORITY_THRESHOLD]
    for index, left in enumerate(high_priority_annotations):
        for right in high_priority_annotations[index + 1 :]:
            if _date_interval_overlaps(left.start_date, left.end_date, right.start_date, right.end_date):
                warnings.append(
                    f"high-priority annotation overlap: {left.annotation_id} overlaps {right.annotation_id}"
                )

    return EditorialOverlayValidationReport(
        annotation_count=len(annotations_list),
        calendar_marker_count=len(calendar_markers_list),
        game_overlay_count=len(game_overlays_list),
        era_count=len(eras_list),
        story_chapter_count=len(story_chapters_list),
        errors=errors,
        warnings=warnings,
    )
