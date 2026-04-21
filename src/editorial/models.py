from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class EditorialBuild:
    editorial_build_id: str
    built_at: datetime
    builder_version: str
    presentation_build_id: str | None
    notes: str | None

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class EditorialAnnotation:
    annotation_id: str
    annotation_type: str
    title: str
    body: str
    start_date: date
    end_date: date
    event_id: str | None
    asset_id: str | None
    priority: int
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class EditorialCalendarMarker:
    calendar_marker_id: str
    marker_type: str
    label: str
    marker_date: date
    payload: JsonDict
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class EditorialGameOverlay:
    game_overlay_id: str
    game_date: date
    opponent: str
    home_away: str
    result: str
    score_display: str
    payload: JsonDict
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class EditorialEra:
    era_id: str
    title: str
    start_date: date
    end_date: date
    description: str
    priority: int
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class EditorialStoryChapter:
    story_chapter_id: str
    slug: str
    chapter_order: int
    title: str
    body: str
    start_date: date
    end_date: date
    focus_payload: JsonDict
    era_id: str | None
    created_at: datetime
    updated_at: datetime

    def as_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class EditorialOverlayBundle:
    annotations: list[EditorialAnnotation]
    calendar_markers: list[EditorialCalendarMarker]
    game_overlays: list[EditorialGameOverlay]
    eras: list[EditorialEra]
    story_chapters: list[EditorialStoryChapter]

    def counts(self) -> JsonDict:
        return {
            "annotation_count": len(self.annotations),
            "calendar_marker_count": len(self.calendar_markers),
            "game_overlay_count": len(self.game_overlays),
            "era_count": len(self.eras),
            "story_chapter_count": len(self.story_chapters),
        }

    def as_contract(self) -> JsonDict:
        return {
            "annotations": [row.as_dict() for row in self.annotations],
            "calendar_markers": [row.as_dict() for row in self.calendar_markers],
            "game_overlays": [row.as_dict() for row in self.game_overlays],
            "eras": [row.as_dict() for row in self.eras],
            "story_chapters": [row.as_dict() for row in self.story_chapters],
        }


@dataclass(frozen=True)
class EditorialOverlayBuildResult:
    build: EditorialBuild
    annotations: list[EditorialAnnotation]
    calendar_markers: list[EditorialCalendarMarker]
    game_overlays: list[EditorialGameOverlay]
    eras: list[EditorialEra]
    story_chapters: list[EditorialStoryChapter]

    def counts(self) -> JsonDict:
        return {
            "editorial_build_id": self.build.editorial_build_id,
            **EditorialOverlayBundle(
                annotations=self.annotations,
                calendar_markers=self.calendar_markers,
                game_overlays=self.game_overlays,
                eras=self.eras,
                story_chapters=self.story_chapters,
            ).counts(),
        }

    def as_contract(self) -> JsonDict:
        return {
            **EditorialOverlayBundle(
                annotations=self.annotations,
                calendar_markers=self.calendar_markers,
                game_overlays=self.game_overlays,
                eras=self.eras,
                story_chapters=self.story_chapters,
            ).as_contract(),
            "meta": {
                **self.build.as_dict(),
                **EditorialOverlayBundle(
                    annotations=self.annotations,
                    calendar_markers=self.calendar_markers,
                    game_overlays=self.game_overlays,
                    eras=self.eras,
                    story_chapters=self.story_chapters,
                ).counts(),
            },
        }
