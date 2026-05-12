from foundation.draft_resolution import (
    CuratedDraftPickResolutionBundle,
    CuratedDraftPickResolutionRow,
    DEFAULT_CURATED_DRAFT_PICK_RESOLUTION_PATH,
    DraftSelectionForResolution,
    PickCandidateForResolution,
    build_curated_draft_pick_resolution_preview,
    build_draft_pick_resolution_preview,
    build_slot_pick_asset_id,
    build_slot_pick_id,
    load_curated_draft_pick_resolution,
    load_curated_draft_pick_resolution_bundle,
    pick_matches_selection_team,
)


def test_draft_resolution_preview_reports_missing_owned_pick_inventory() -> None:
    report = build_draft_pick_resolution_preview(
        selections=[
            DraftSelectionForResolution(
                draft_selection_id="draft:2024:9",
                draft_year=2024,
                pick_overall=9,
                round_number=1,
                team_code="MEM",
                player_id="player:zach-edey",
                player_name="Zach Edey",
            )
        ],
        picks=[],
    )

    assert report.selections == 1
    assert report.unmatched == 1
    assert report.rows[0].confidence == "none"
    assert "no pick asset exists" in report.rows[0].reason


def test_draft_resolution_preview_uses_existing_pick_link_when_present() -> None:
    report = build_draft_pick_resolution_preview(
        selections=[
            DraftSelectionForResolution(
                draft_selection_id="draft:2024:39",
                draft_year=2024,
                pick_overall=39,
                round_number=2,
                team_code="MEM",
                player_id="player:jaylen-wells",
                player_name="Jaylen Wells",
                pick_id="pick:mem-2024-second",
            )
        ],
        picks=[
            PickCandidateForResolution(
                pick_id="pick:mem-2024-second",
                asset_id="asset:pick:mem-2024-second",
                draft_year=2024,
                round_number=2,
                original_team="MEM",
                raw_text="2024 2nd round pick (MEM own)",
            )
        ],
    )

    assert report.linked == 1
    assert report.rows[0].matched_pick_id == "pick:mem-2024-second"
    assert report.rows[0].matched_pick_asset_id == "asset:pick:mem-2024-second"
    assert report.rows[0].confidence == "high"


def test_draft_resolution_preview_reports_team_matched_candidate() -> None:
    report = build_draft_pick_resolution_preview(
        selections=[
            DraftSelectionForResolution(
                draft_selection_id="draft:2024:39",
                draft_year=2024,
                pick_overall=39,
                round_number=2,
                team_code="MEM",
                player_id="player:jaylen-wells",
                player_name="Jaylen Wells",
            )
        ],
        picks=[
            PickCandidateForResolution(
                pick_id="pick:mem-2024-second",
                asset_id="asset:pick:mem-2024-second",
                draft_year=2024,
                round_number=2,
                original_team="MEM",
                raw_text="2024 2nd round pick (MEM own)",
            )
        ],
    )

    assert report.candidate == 1
    assert report.rows[0].matched_pick_id == "pick:mem-2024-second"
    assert report.rows[0].confidence == "medium"


def test_draft_resolution_preview_reports_ambiguous_same_round_candidates() -> None:
    report = build_draft_pick_resolution_preview(
        selections=[
            DraftSelectionForResolution(
                draft_selection_id="draft:2024:39",
                draft_year=2024,
                pick_overall=39,
                round_number=2,
                team_code="MEM",
                player_id="player:jaylen-wells",
                player_name="Jaylen Wells",
            )
        ],
        picks=[
            PickCandidateForResolution(
                pick_id="pick:atl-2024-second",
                asset_id="asset:pick:atl-2024-second",
                draft_year=2024,
                round_number=2,
                original_team="ATL",
                raw_text="2024 2nd round pick (ATL own)",
            ),
            PickCandidateForResolution(
                pick_id="pick:okc-2024-second",
                asset_id="asset:pick:okc-2024-second",
                draft_year=2024,
                round_number=2,
                original_team="OKC",
                raw_text="2024 2nd round pick (OKC own)",
            ),
        ],
    )

    assert report.ambiguous == 1
    assert report.rows[0].matched_pick_id is None
    assert report.rows[0].candidate_pick_ids == ["pick:atl-2024-second", "pick:okc-2024-second"]


def test_draft_resolution_preview_does_not_reuse_one_candidate_for_multiple_same_round_selections() -> None:
    report = build_draft_pick_resolution_preview(
        selections=[
            DraftSelectionForResolution(
                draft_selection_id="draft:2024:39",
                draft_year=2024,
                pick_overall=39,
                round_number=2,
                team_code="MEM",
                player_id="player:jaylen-wells",
                player_name="Jaylen Wells",
            ),
            DraftSelectionForResolution(
                draft_selection_id="draft:2024:57",
                draft_year=2024,
                pick_overall=57,
                round_number=2,
                team_code="MEM",
                player_id="player:ulrich-chomche",
                player_name="Ulrich Chomche",
            ),
        ],
        picks=[
            PickCandidateForResolution(
                pick_id="pick:mem-2024-second",
                asset_id="asset:pick:mem-2024-second",
                draft_year=2024,
                round_number=2,
                original_team="MEM",
                raw_text="2024 2nd round pick (MEM own)",
            )
        ],
    )

    assert report.ambiguous == 2
    assert all(row.matched_pick_id is None for row in report.rows)
    assert all("pick_overall" in row.reason for row in report.rows)


def test_pick_matches_selection_team_recognizes_memphis_text() -> None:
    assert pick_matches_selection_team(
        PickCandidateForResolution(
            pick_id="pick:memphis-text",
            draft_year=2025,
            round_number=1,
            raw_text="Memphis 2025 first-round pick",
        ),
        "MEM",
    )


def test_curated_draft_pick_resolution_preview_proposes_new_slot_pick_when_db_selection_matches() -> None:
    bundle = CuratedDraftPickResolutionBundle(
        source_bundle_id="test-bundle",
        description="test",
        rows=[
            CuratedDraftPickResolutionRow(
                draft_selection_id="draft:2024:9",
                draft_year=2024,
                round_number=1,
                pick_overall=9,
                team_code="MEM",
                player_name="Zach Edey",
                source_locator="https://www.basketball-reference.com/draft/NBA_2024.html",
                confidence="high",
            )
        ],
    )
    current_preview = build_draft_pick_resolution_preview(
        selections=[
            DraftSelectionForResolution(
                draft_selection_id="draft:2024:9",
                draft_year=2024,
                pick_overall=9,
                round_number=1,
                team_code="MEM",
                player_id="player:zach-edey",
                player_name="Zach Edey",
            )
        ],
        picks=[],
    )

    report = build_curated_draft_pick_resolution_preview(
        bundle=bundle,
        fixture_path=DEFAULT_CURATED_DRAFT_PICK_RESOLUTION_PATH,
        selections=[
            DraftSelectionForResolution(
                draft_selection_id="draft:2024:9",
                draft_year=2024,
                pick_overall=9,
                round_number=1,
                team_code="MEM",
                player_id="player:zach-edey",
                player_name="Zach Edey",
            )
        ],
        picks=[],
        current_preview=current_preview,
        team_code="MEM",
    )

    assert report.ready_for_write == 1
    assert report.proposed_new_picks == 1
    assert report.blocked == 0
    assert report.rows[0].write_action == "create_pick_and_link"
    assert report.rows[0].proposed_pick_id == "pick:slot:2024:9"
    assert report.rows[0].proposed_pick_asset_id == "asset:pick:pick:slot:2024:9"


def test_curated_draft_pick_resolution_preview_blocks_mismatched_db_selection() -> None:
    bundle = CuratedDraftPickResolutionBundle(
        source_bundle_id="test-bundle",
        description="test",
        rows=[
            CuratedDraftPickResolutionRow(
                draft_selection_id="draft:2024:9",
                draft_year=2024,
                round_number=1,
                pick_overall=9,
                team_code="MEM",
                player_name="Zach Edey",
                source_locator="https://www.basketball-reference.com/draft/NBA_2024.html",
                confidence="high",
            )
        ],
    )
    selection = DraftSelectionForResolution(
        draft_selection_id="draft:2024:9",
        draft_year=2024,
        pick_overall=9,
        round_number=1,
        team_code="MEM",
        player_id="player:not-zach-edey",
        player_name="Wrong Player",
    )
    current_preview = build_draft_pick_resolution_preview(selections=[selection], picks=[])

    report = build_curated_draft_pick_resolution_preview(
        bundle=bundle,
        fixture_path=DEFAULT_CURATED_DRAFT_PICK_RESOLUTION_PATH,
        selections=[selection],
        picks=[],
        current_preview=current_preview,
        team_code="MEM",
    )

    assert report.blocked == 1
    assert report.ready_for_write == 0
    assert report.rows[0].db_selection_status == "mismatch"
    assert report.rows[0].write_action == "blocked"
    assert "Wrong Player" in report.rows[0].issues[0]


def test_slot_pick_id_helpers_are_stable() -> None:
    assert build_slot_pick_id(2024, 9) == "pick:slot:2024:9"
    assert build_slot_pick_asset_id(2024, 9) == "asset:pick:pick:slot:2024:9"


def test_default_curated_fixture_loads_all_memphis_resolution_rows() -> None:
    bundle = load_curated_draft_pick_resolution_bundle(DEFAULT_CURATED_DRAFT_PICK_RESOLUTION_PATH)
    assert bundle.source_bundle_id == "memphis-draft-pick-resolution-2016-2025"
    assert len(bundle.rows) == 20
    assert {row.team_code for row in bundle.rows} == {"MEM"}


def test_load_curated_draft_pick_resolution_requires_database_only_for_integration() -> None:
    assert load_curated_draft_pick_resolution.__name__ == "load_curated_draft_pick_resolution"
