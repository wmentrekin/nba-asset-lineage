from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from canonical.models import CanonicalAsset, CanonicalEvent
from editorial.contract import (
    build_editorial_overlays,
    editorial_overlays_to_json,
    fetch_editorial_overlays,
    load_editorial_bundle,
)
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
from presentation.contract import build_presentation_contract, presentation_contract_to_json
from redesign_cli import _build_editorial_chapter_rows, _validate_editorial_chapter_rows


NOW = datetime(2026, 4, 20, 12, 0, 0)
EDITORIAL_BUILD_ID = "editorial_build_1"


def _event(event_id: str, event_date: str) -> CanonicalEvent:
    parsed = date.fromisoformat(event_date)
    return CanonicalEvent(
        event_id=event_id,
        event_type="trade",
        event_date=parsed,
        event_order=1,
        event_label=event_id,
        description=event_id,
        transaction_group_key=event_id,
        is_compound=False,
        notes=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _asset(asset_id: str) -> CanonicalAsset:
    return CanonicalAsset(
        asset_id=asset_id,
        asset_kind="player_tenure",
        player_tenure_id="tenure_1",
        pick_asset_id=None,
        asset_label="Asset",
        created_at=NOW,
        updated_at=NOW,
    )


def _annotation(annotation_id: str, start: str, end: str, *, event_id: str | None = None, asset_id: str | None = None, priority: int = 10) -> EditorialAnnotation:
    return EditorialAnnotation(
        editorial_build_id=EDITORIAL_BUILD_ID,
        annotation_id=annotation_id,
        annotation_type="note",
        title=annotation_id,
        body=annotation_id,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        event_id=event_id,
        asset_id=asset_id,
        priority=priority,
        created_at=NOW,
        updated_at=NOW,
    )


def _bundle() -> EditorialOverlayBundle:
    era = EditorialEra(
        editorial_build_id=EDITORIAL_BUILD_ID,
        era_id="era_reset",
        title="Reset era",
        start_date=date.fromisoformat("2024-02-08"),
        end_date=date.fromisoformat("2025-06-30"),
        description="Multi-season reset",
        priority=80,
        created_at=NOW,
        updated_at=NOW,
    )
    return EditorialOverlayBundle(
        annotations=[
            _annotation("annotation_event", "2024-02-08", "2024-02-08", event_id="event_trade", asset_id="asset_1", priority=90),
            _annotation("annotation_range", "2024-02-09", "2025-06-30", priority=70),
        ],
        calendar_markers=[
            EditorialCalendarMarker(
                editorial_build_id=EDITORIAL_BUILD_ID,
                calendar_marker_id="marker_deadline",
                marker_type="trade_deadline",
                label="2024 trade deadline",
                marker_date=date.fromisoformat("2024-02-08"),
                payload={"league": "nba"},
                created_at=NOW,
                updated_at=NOW,
            )
        ],
        game_overlays=[
            EditorialGameOverlay(
                editorial_build_id=EDITORIAL_BUILD_ID,
                game_overlay_id="game_overlay_bos",
                game_date=date.fromisoformat("2024-02-08"),
                opponent="Boston Celtics",
                home_away="home",
                result="loss",
                score_display="131-91",
                payload={"notable": True},
                created_at=NOW,
                updated_at=NOW,
            )
        ],
        eras=[era],
        story_chapters=[
            EditorialStoryChapter(
                editorial_build_id=EDITORIAL_BUILD_ID,
                story_chapter_id="chapter_reset",
                slug="reset",
                chapter_order=1,
                title="A reset begins",
                body="Narrative copy.",
                start_date=date.fromisoformat("2024-02-08"),
                end_date=date.fromisoformat("2025-06-30"),
                focus_payload={
                    "date_range": {"start_date": "2024-02-08", "end_date": "2025-06-30"},
                    "event_ids": ["event_trade"],
                    "asset_ids": ["asset_1"],
                    "lane_groups": ["main_roster"],
                },
                era_id="era_reset",
                created_at=NOW,
                updated_at=NOW,
            )
        ],
    )


def test_load_editorial_bundle_parses_tracked_seed_file():
    bundle = load_editorial_bundle(Path("configs/data"))

    assert len(bundle.annotations) == 2
    assert len(bundle.calendar_markers) == 1
    assert len(bundle.game_overlays) == 1
    assert len(bundle.eras) == 1
    assert len(bundle.story_chapters) == 1


def test_build_and_validate_editorial_overlays_cover_minimum_stage_7_scenarios():
    bundle = _bundle()
    result = build_editorial_overlays(bundle, built_at=NOW, presentation_build_id="presentation_build_1")

    assert result.build.presentation_build_id == "presentation_build_1"
    assert len(result.annotations) == 2
    assert len(result.game_overlays) == 1
    assert len(result.eras) == 1
    assert len(result.story_chapters) == 1

    report = validate_editorial_overlays(
        annotations=result.annotations,
        calendar_markers=result.calendar_markers,
        game_overlays=result.game_overlays,
        eras=result.eras,
        story_chapters=result.story_chapters,
        canonical_events=[_event("event_trade", "2024-02-08")],
        canonical_assets=[_asset("asset_1")],
    )
    assert report.ok
    assert report.annotation_count == 2
    assert report.game_overlay_count == 1
    assert report.era_count == 1


def test_validate_flags_incoherent_dates_and_missing_links():
    bad_bundle = EditorialOverlayBundle(
        annotations=[
            EditorialAnnotation(
                editorial_build_id=EDITORIAL_BUILD_ID,
                annotation_id="bad_annotation",
                annotation_type="note",
                title="Bad",
                body="Bad",
                start_date=date.fromisoformat("2024-02-10"),
                end_date=date.fromisoformat("2024-02-08"),
                event_id="missing_event",
                asset_id="missing_asset",
                priority=10,
                created_at=NOW,
                updated_at=NOW,
            )
        ],
        calendar_markers=[],
        game_overlays=[],
        eras=[],
        story_chapters=[
            EditorialStoryChapter(
                editorial_build_id=EDITORIAL_BUILD_ID,
                story_chapter_id="bad_chapter",
                slug="bad",
                chapter_order=1,
                title="Bad chapter",
                body="Bad",
                start_date=date.fromisoformat("2024-02-10"),
                end_date=date.fromisoformat("2024-02-08"),
                focus_payload={"date_range": {"start_date": "2024-02-10", "end_date": "2024-02-08"}},
                era_id="missing_era",
                created_at=NOW,
                updated_at=NOW,
            )
        ],
    )

    report = validate_editorial_overlays(
        annotations=bad_bundle.annotations,
        calendar_markers=bad_bundle.calendar_markers,
        game_overlays=bad_bundle.game_overlays,
        eras=bad_bundle.eras,
        story_chapters=bad_bundle.story_chapters,
    )

    assert not report.ok
    assert any("annotation end_date before start_date" in error for error in report.errors)
    assert any("story chapter end_date before start_date" in error for error in report.errors)
    assert any("story chapter references unknown era_id" in error for error in report.errors)


def test_validate_emits_warning_for_overlapping_high_priority_annotations():
    bundle = EditorialOverlayBundle(
        annotations=[
            _annotation("annotation_one", "2024-02-08", "2024-02-10", priority=90),
            _annotation("annotation_two", "2024-02-09", "2024-02-11", priority=95),
        ],
        calendar_markers=[],
        game_overlays=[],
        eras=[],
        story_chapters=[],
    )

    report = validate_editorial_overlays(
        annotations=bundle.annotations,
        calendar_markers=bundle.calendar_markers,
        game_overlays=bundle.game_overlays,
        eras=bundle.eras,
        story_chapters=bundle.story_chapters,
    )

    assert report.ok
    assert any("high-priority annotation overlap" in warning for warning in report.warnings)


def test_combined_presentation_export_keeps_editorial_payload_separate():
    presentation = build_presentation_contract(
        events=[_event("event_trade", "2024-02-08")],
        assets=[_asset("asset_1")],
        player_identities=[],
        player_tenures=[],
        pick_assets=[],
        pick_resolutions=[],
        asset_states=[],
        built_at=NOW,
    )
    editorial = EditorialOverlayBuildResult(
        build=EditorialBuild(
            editorial_build_id=EDITORIAL_BUILD_ID,
            built_at=NOW,
            builder_version="stage7-editorial-overlay-v1",
            presentation_build_id="presentation_build_1",
            notes=None,
        ),
        **_bundle().__dict__,
    )

    payload = json.loads(presentation_contract_to_json(presentation, editorial_overlays=editorial))

    assert set(payload) == {"nodes", "edges", "lanes", "editorial", "meta"}
    assert set(payload["editorial"]) == {"annotations", "calendar_markers", "game_overlays", "eras", "story_chapters", "meta"}
    assert payload["meta"]["node_count"] == len(payload["nodes"])
    assert payload["editorial"]["meta"]["annotation_count"] == 2


def test_editorial_chapter_export_rows_only_emit_story_chapter_fields():
    rows = _build_editorial_chapter_rows(_bundle())

    assert rows == [
        {
            "story_chapter_id": "chapter_reset",
            "slug": "reset",
            "chapter_order": 1,
            "title": "A reset begins",
            "body": "Narrative copy.",
            "start_date": date.fromisoformat("2024-02-08"),
            "end_date": date.fromisoformat("2025-06-30"),
        }
    ]
    assert set(rows[0]) == {
        "story_chapter_id",
        "slug",
        "chapter_order",
        "title",
        "body",
        "start_date",
        "end_date",
    }


def test_editorial_chapter_export_validation_fails_loudly_on_layout_mismatch():
    rows = _build_editorial_chapter_rows(_bundle())

    with pytest.raises(RuntimeError, match="out of sync with chapter_layout"):
        _validate_editorial_chapter_rows(rows, chapter_layout_ids=set())


def test_editorial_chapter_export_validation_fails_loudly_on_duplicate_ids():
    rows = _build_editorial_chapter_rows(_bundle()) * 2

    with pytest.raises(RuntimeError, match="duplicate story_chapter_id"):
        _validate_editorial_chapter_rows(rows, chapter_layout_ids={"chapter_reset"})


class _FakeCursor:
    def __init__(self, responses: list[object]):
        self._responses = responses
        self.queries: list[tuple[str, tuple[object, ...] | None]] = []
        self._index = 0

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
        self.queries.append((query, params))

    def fetchone(self):
        value = self._responses[self._index]
        self._index += 1
        return value

    def fetchall(self):
        value = self._responses[self._index]
        self._index += 1
        return value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, responses: list[object]):
        self.cursor_obj = _FakeCursor(responses)

    def cursor(self):
        return self.cursor_obj


def test_fetch_editorial_overlays_defaults_to_latest_build_and_scopes_rows():
    build_row = (EDITORIAL_BUILD_ID, NOW, "stage7-editorial-overlay-v1", "presentation_build_1", None)
    row = (
        EDITORIAL_BUILD_ID,
        "annotation_1",
        "note",
        "Annotation",
        "Body",
        date.fromisoformat("2024-02-08"),
        date.fromisoformat("2024-02-08"),
        "event_trade",
        "asset_1",
        10,
        NOW,
        NOW,
    )
    conn = _FakeConn([build_row, [row], [], [], [], []])

    result = fetch_editorial_overlays(conn)

    assert result.build.editorial_build_id == EDITORIAL_BUILD_ID
    assert result.annotations[0].editorial_build_id == EDITORIAL_BUILD_ID
    assert conn.cursor_obj.queries[0][0].lower().strip().startswith("select")
    assert conn.cursor_obj.queries[1][1] == (EDITORIAL_BUILD_ID,)


def test_fetch_editorial_overlays_can_target_a_specific_build():
    build_row = (EDITORIAL_BUILD_ID, NOW, "stage7-editorial-overlay-v1", "presentation_build_1", None)
    conn = _FakeConn([build_row, [], [], [], [], []])

    result = fetch_editorial_overlays(conn, editorial_build_id=EDITORIAL_BUILD_ID)

    assert result.build.editorial_build_id == EDITORIAL_BUILD_ID
    assert conn.cursor_obj.queries[0][1] == (EDITORIAL_BUILD_ID,)
