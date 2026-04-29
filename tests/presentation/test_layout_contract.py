from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from canonical.models import (
    AssetState,
    CanonicalAsset,
    CanonicalEvent,
    CanonicalPickAsset,
    CanonicalPickResolution,
    CanonicalPlayerIdentity,
    CanonicalPlayerTenure,
)
from editorial.models import EditorialBuild, EditorialOverlayBuildResult, EditorialStoryChapter
from presentation.contract import build_layout_contract, build_presentation_contract
from presentation.validate import validate_layout_contract
from redesign_cli import _build_editorial_chapter_rows, _validate_editorial_chapter_rows


NOW = datetime(2026, 4, 20, 12, 0, 0)


def _event(
    event_id: str,
    event_type: str,
    event_date: str,
    order: int,
    label: str,
    *,
    transaction_group_key: str | None = None,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        event_date=date.fromisoformat(event_date),
        event_order=order,
        event_label=label,
        description=label,
        transaction_group_key=transaction_group_key or event_id,
        is_compound=False,
        notes=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _identity(player_id: str, name: str) -> CanonicalPlayerIdentity:
    return CanonicalPlayerIdentity(
        player_id=player_id,
        display_name=name,
        normalized_name=name.lower(),
        nba_person_id=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _tenure(
    tenure_id: str,
    player_id: str,
    start: str,
    end: str | None,
    entry_event_id: str,
    exit_event_id: str | None,
) -> CanonicalPlayerTenure:
    return CanonicalPlayerTenure(
        player_tenure_id=tenure_id,
        player_id=player_id,
        tenure_start_date=date.fromisoformat(start),
        tenure_end_date=date.fromisoformat(end) if end else None,
        entry_event_id=entry_event_id,
        exit_event_id=exit_event_id,
        tenure_type="signing",
        roster_path_type="free_agency",
        created_at=NOW,
        updated_at=NOW,
    )


def _asset(asset_id: str, kind: str, label: str, *, tenure_id: str | None = None, pick_id: str | None = None) -> CanonicalAsset:
    return CanonicalAsset(
        asset_id=asset_id,
        asset_kind=kind,
        player_tenure_id=tenure_id,
        pick_asset_id=pick_id,
        asset_label=label,
        created_at=NOW,
        updated_at=NOW,
    )


def _pick_asset(pick_id: str, current_stage: str = "drafted_player") -> CanonicalPickAsset:
    return CanonicalPickAsset(
        pick_asset_id=pick_id,
        origin_team_code="UTA",
        draft_year=2024,
        draft_round=2,
        protection_summary=None,
        protection_payload={},
        drafted_player_id="player_gg",
        current_pick_stage=current_stage,
        created_at=NOW,
        updated_at=NOW,
    )


def _pick_resolution(
    resolution_id: str,
    pick_id: str,
    state_type: str,
    start: str,
    source_event_id: str | None,
    drafted_player_id: str | None = None,
    state_payload: dict[str, object] | None = None,
) -> CanonicalPickResolution:
    return CanonicalPickResolution(
        pick_resolution_id=resolution_id,
        pick_asset_id=pick_id,
        state_type=state_type,
        effective_start_date=date.fromisoformat(start),
        effective_end_date=None,
        overall_pick_number=45 if state_type in {"resolved_pick", "drafted_player"} else None,
        lottery_context=None,
        drafted_player_id=drafted_player_id,
        source_event_id=source_event_id,
        state_payload=state_payload or {"state_type": state_type},
        created_at=NOW,
        updated_at=NOW,
    )


def _story_chapter(
    chapter_id: str,
    start: str,
    end: str,
    *,
    focus_payload: dict[str, object] | None = None,
) -> EditorialStoryChapter:
    return EditorialStoryChapter(
        editorial_build_id="editorial_build_test",
        story_chapter_id=chapter_id,
        slug=chapter_id,
        chapter_order=1,
        title="Chapter",
        body="Body",
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        focus_payload=focus_payload or {},
        era_id=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _editorial_result(*chapters: EditorialStoryChapter) -> EditorialOverlayBuildResult:
    return EditorialOverlayBuildResult(
        build=EditorialBuild(
            editorial_build_id="editorial_build_test",
            built_at=NOW,
            builder_version="stage7-editorial-overlay-v1",
            presentation_build_id="presentation_build_test",
            notes="test",
        ),
        annotations=[],
        calendar_markers=[],
        game_overlays=[],
        eras=[],
        story_chapters=list(chapters),
    )


def _build_presentation(**overrides):
    inputs = {
        "events": [],
        "assets": [],
        "player_identities": [],
        "player_tenures": [],
        "pick_assets": [],
        "pick_resolutions": [],
        "asset_states": [],
        "built_at": NOW,
    }
    inputs.update(overrides)
    return build_presentation_contract(**inputs)


def test_layout_contract_projects_required_groups_headshots_and_chapters(tmp_path: Path):
    events = [
        _event("event_sign_john", "signing", "2024-01-01", 1, "Memphis signs John Doe"),
        _event("event_sign_jane", "signing", "2024-02-01", 1, "Memphis signs Jane Doe"),
        _event("event_waive_jane", "waiver", "2024-02-15", 1, "Memphis waives Jane Doe"),
    ]
    presentation_result = _build_presentation(
        events=events,
        player_identities=[_identity("player_john", "John Doe"), _identity("player_jane", "Jane Doe")],
        player_tenures=[
            _tenure("tenure_john", "player_john", "2024-01-01", None, "event_sign_john", None),
            _tenure("tenure_jane", "player_jane", "2024-02-01", "2024-02-15", "event_sign_jane", "event_waive_jane"),
        ],
        assets=[
            _asset("asset_john", "player_tenure", "John Doe Memphis tenure", tenure_id="tenure_john"),
            _asset("asset_jane", "player_tenure", "Jane Doe Memphis tenure", tenure_id="tenure_jane"),
        ],
    )

    frontend_public_root = tmp_path / "frontend" / "public"
    headshot_dir = frontend_public_root / "headshots"
    headshot_dir.mkdir(parents=True)
    (headshot_dir / "john.png").write_text("png", encoding="utf-8")
    manifest_path = tmp_path / "stage8_headshot_manifest.yaml"
    manifest_path.write_text("asset_john: headshots/john.png\nasset_jane: headshots/missing.png\n", encoding="utf-8")

    editorial_result = _editorial_result(
        _story_chapter(
            "chapter_reset",
            "2024-01-01",
            "2024-03-01",
            focus_payload={
                "date_range": {"start_date": "2024-01-01", "end_date": "2024-03-01"},
                "event_ids": ["event_sign_john", "missing_event"],
                "asset_ids": ["asset_john", "missing_asset"],
                "default_zoom": 45,
            },
        )
    )
    layout_result = build_layout_contract(
        presentation_result=presentation_result,
        editorial_overlays=editorial_result,
        built_at=NOW,
        headshot_manifest_path=manifest_path,
        frontend_public_root=frontend_public_root,
    )

    assert set(layout_result.as_contract()) == {
        "layout_meta",
        "lane_layout",
        "event_layout",
        "label_layout",
        "chapter_layout",
    }
    lane_by_asset = {row.asset_id: row for row in layout_result.lane_layout}
    assert lane_by_asset["asset_john"].identity_marker.image_path == "headshots/john.png"
    assert lane_by_asset["asset_john"].identity_marker.marker_variant == "headshot_text"
    assert lane_by_asset["asset_jane"].identity_marker.image_path is None
    assert lane_by_asset["asset_jane"].identity_marker.marker_variant == "text_only"
    assert lane_by_asset["asset_john"].display_rank < lane_by_asset["asset_jane"].display_rank

    chapter = layout_result.chapter_layout[0]
    assert chapter.highlight_event_ids == ["event_sign_john"]
    assert chapter.highlight_asset_ids == ["asset_john"]
    assert chapter.default_zoom == 45
    assert chapter.minimap_anchor_id in {row.segment_id for row in layout_result.layout_meta.minimap_segments}

    report = validate_layout_contract(
        result=layout_result,
        presentation_result=presentation_result,
        editorial_overlays=editorial_result,
        frontend_public_root=frontend_public_root,
    )
    assert report.ok

    chapter_rows = _build_editorial_chapter_rows(editorial_result)
    _validate_editorial_chapter_rows(
        chapter_rows,
        chapter_layout_ids={row.story_chapter_id for row in layout_result.chapter_layout},
    )
    assert [row["story_chapter_id"] for row in chapter_rows] == [row.story_chapter_id for row in layout_result.chapter_layout]


def test_same_day_trade_clustering_uses_transaction_group_key():
    presentation_result = _build_presentation(
        events=[
            _event("event_trade_a", "trade", "2024-02-08", 1, "Trade A", transaction_group_key="deadline_a"),
            _event("event_trade_b", "trade", "2024-02-08", 2, "Trade B", transaction_group_key="deadline_a"),
            _event("event_trade_c", "trade", "2024-02-08", 3, "Trade C", transaction_group_key="deadline_b"),
            _event("event_waive", "waiver", "2024-02-08", 4, "Waive D"),
        ]
    )

    layout_result = build_layout_contract(presentation_result=presentation_result, built_at=NOW)

    assert len(layout_result.event_layout) == 3
    grouped_cluster = next(row for row in layout_result.event_layout if row.cluster_order == 1)
    assert grouped_cluster.member_event_ids == ["event_trade_a", "event_trade_b"]
    assert grouped_cluster.event_id == "event_trade_a"
    assert {tuple(row.member_event_ids) for row in layout_result.event_layout} == {
        ("event_trade_a", "event_trade_b"),
        ("event_trade_c",),
        ("event_waive",),
    }

    report = validate_layout_contract(result=layout_result, presentation_result=presentation_result)
    assert report.ok


def test_transition_links_cover_pick_to_player_clusters():
    events = [
        _event("event_trade_pick", "trade", "2024-01-10", 1, "Memphis acquires Utah second"),
        _event("event_draft", "draft", "2024-06-26", 1, "Memphis drafts GG Jackson"),
    ]
    presentation_result = _build_presentation(
        events=events,
        assets=[_asset("asset_pick_45", "pick_continuity", "Utah 2024 round 2 pick", pick_id="pick_45")],
        player_identities=[_identity("player_gg", "GG Jackson")],
        pick_assets=[_pick_asset("pick_45")],
        pick_resolutions=[
            _pick_resolution("resolution_future", "pick_45", "future_pick", "2024-01-10", "event_trade_pick"),
            _pick_resolution("resolution_drafted", "pick_45", "drafted_player", "2024-06-26", "event_draft", "player_gg"),
        ],
    )

    layout_result = build_layout_contract(presentation_result=presentation_result, built_at=NOW)

    draft_cluster = next(row for row in layout_result.event_layout if row.event_id == "event_draft")
    assert draft_cluster.junction_type == "draft_transition"
    assert draft_cluster.member_event_ids == ["event_draft"]
    assert len(draft_cluster.transition_links) == 1
    transition_link = draft_cluster.transition_links[0]
    assert transition_link.link_type == "pick_to_player"
    assert transition_link.source_segment_id in draft_cluster.incoming_slots
    assert transition_link.target_segment_id in draft_cluster.outgoing_slots
    assert {anchor.segment_id for anchor in draft_cluster.transition_anchors} == {
        transition_link.source_segment_id,
        transition_link.target_segment_id,
    }
    lane_by_segment = {row.segment_id: row for row in layout_result.lane_layout}
    assert lane_by_segment[transition_link.source_segment_id].continuity_anchor == lane_by_segment[transition_link.target_segment_id].continuity_anchor

    report = validate_layout_contract(result=layout_result, presentation_result=presentation_result)
    assert report.ok


def test_transition_links_cover_multi_hop_draft_transition_clusters():
    events = [
        _event("event_trade_pick", "trade", "2024-01-10", 1, "Memphis acquires Utah second"),
        _event("event_draft", "draft", "2024-06-26", 1, "Memphis drafts GG Jackson"),
    ]
    presentation_result = _build_presentation(
        events=events,
        assets=[_asset("asset_pick_45", "pick_continuity", "Utah 2024 round 2 pick", pick_id="pick_45")],
        player_identities=[_identity("player_gg", "GG Jackson")],
        pick_assets=[_pick_asset("pick_45")],
        pick_resolutions=[
            _pick_resolution("resolution_future", "pick_45", "future_pick", "2024-01-10", "event_trade_pick"),
            _pick_resolution("resolution_resolved", "pick_45", "resolved_pick", "2024-06-26", "event_draft"),
            _pick_resolution("resolution_drafted", "pick_45", "drafted_player", "2024-06-26", "event_draft", "player_gg"),
        ],
    )

    layout_result = build_layout_contract(presentation_result=presentation_result, built_at=NOW)

    draft_cluster = next(row for row in layout_result.event_layout if row.event_id == "event_draft")
    assert draft_cluster.junction_type == "draft_transition"
    edge_by_segment_id = {edge.edge_id: edge for edge in presentation_result.edges}
    segment_by_stage = {
        edge.payload.get("pick_stage"): edge.edge_id
        for edge in presentation_result.edges
        if edge.asset_id == "asset_pick_45"
    }
    assert {(link.source_segment_id, link.target_segment_id, link.link_type) for link in draft_cluster.transition_links} == {
        (segment_by_stage["future_pick"], segment_by_stage["resolved_pick"], "same_asset"),
        (segment_by_stage["resolved_pick"], segment_by_stage["drafted_player"], "pick_to_player"),
    }
    assert {anchor.segment_id for anchor in draft_cluster.transition_anchors} == {
        segment_by_stage["future_pick"],
        segment_by_stage["resolved_pick"],
        segment_by_stage["drafted_player"],
    }
    assert edge_by_segment_id[segment_by_stage["resolved_pick"]].edge_type == "pick_line"
    assert edge_by_segment_id[segment_by_stage["drafted_player"]].edge_type == "transition_line"

    report = validate_layout_contract(result=layout_result, presentation_result=presentation_result)
    assert report.ok


def test_required_lane_group_visibility_survives_layout_export():
    events = [
        _event("event_sign_main", "signing", "2024-01-01", 1, "Memphis signs Main Player"),
        _event("event_sign_two_way", "signing", "2024-01-02", 1, "Memphis signs Two Way Player"),
        _event("event_trade_pick", "trade", "2024-01-10", 1, "Memphis acquires Utah second"),
    ]
    two_way_state = AssetState(
        asset_state_id="state_two_way",
        asset_id="asset_two_way",
        state_type="player_contract_interval",
        effective_start_date=date.fromisoformat("2024-01-02"),
        effective_end_date=None,
        state_payload={"contract_type": "two-way"},
        source_event_id="event_sign_two_way",
        created_at=NOW,
        updated_at=NOW,
    )
    presentation_result = _build_presentation(
        events=events,
        player_identities=[_identity("player_main", "Main Player"), _identity("player_two_way", "Two Way Player")],
        player_tenures=[
            _tenure("tenure_main", "player_main", "2024-01-01", None, "event_sign_main", None),
            _tenure("tenure_two_way", "player_two_way", "2024-01-02", None, "event_sign_two_way", None),
        ],
        assets=[
            _asset("asset_main", "player_tenure", "Main Player Memphis tenure", tenure_id="tenure_main"),
            _asset("asset_two_way", "player_tenure", "Two Way Player Memphis tenure", tenure_id="tenure_two_way"),
            _asset("asset_pick_45", "pick_continuity", "Utah 2024 round 2 pick", pick_id="pick_45"),
        ],
        pick_assets=[_pick_asset("pick_45", current_stage="future_pick")],
        pick_resolutions=[_pick_resolution("resolution_future", "pick_45", "future_pick", "2024-01-10", "event_trade_pick")],
        asset_states=[two_way_state],
    )

    layout_result = build_layout_contract(presentation_result=presentation_result, built_at=NOW)

    assert {row.lane_group for row in layout_result.lane_layout} == {"future_picks", "main_roster", "two_way"}
    assert len(layout_result.lane_layout) == len(presentation_result.edges)
    assert {row.segment_id for row in layout_result.label_layout} == {row.segment_id for row in layout_result.lane_layout}

    report = validate_layout_contract(result=layout_result, presentation_result=presentation_result)
    assert report.ok
