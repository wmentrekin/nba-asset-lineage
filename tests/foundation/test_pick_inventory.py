from foundation.pick_inventory import PickInventoryObligation
from foundation.pick_inventory import ExistingPickInventoryObligation
from foundation.pick_inventory import PickInventoryFixture
from foundation.pick_inventory import PickInventorySnapshot
from foundation.pick_inventory import build_pick_and_asset_rows_for_obligations
from foundation.pick_inventory import build_pick_inventory_obligation_preview
from foundation.pick_inventory import build_pick_inventory_obligation_rows
from foundation.pick_inventory import build_pick_inventory_snapshot_load_result
from foundation.pick_inventory import build_obligation_pick_id
from foundation.pick_inventory import build_own_pick_id
from foundation.pick_inventory import build_roster_snapshot_pick_rows
from foundation.pick_inventory import is_future_pick
from foundation.pick_inventory import load_projectable_future_pick_obligations
from foundation.pick_inventory import project_pick_inventory_rows


def make_obligation(
    obligation_id: str = "obligation:incoming:2028:orl",
    *,
    confidence: str = "curated",
    loadable: bool = True,
    source_event_id: str | None = None,
) -> PickInventoryObligation:
    return PickInventoryObligation(
        obligation_id=obligation_id,
        effective_date="2025-06-15",
        perspective_team_code="MEM",
        owner_team_code="MEM",
        original_team_code="ORL",
        draft_year=2028,
        round_number=1,
        direction="incoming",
        holding_status="owned",
        obligation_type="traded_pick",
        source_urls=["https://example.com/source"],
        source_labels=["Example source"],
        retrieved_at="2026-05-14T00:00:00Z",
        source_event_id=source_event_id,
        confidence=confidence,  # type: ignore[arg-type]
        loadable=loadable,
        notes="Curated test obligation.",
    )


def test_is_future_pick_uses_known_draft_dates_and_fallback_dates() -> None:
    assert is_future_pick("2024-06-25", 2024, 1)
    assert not is_future_pick("2024-06-27", 2024, 1)
    assert is_future_pick("2032-06-29", 2032, 2)
    assert not is_future_pick("2032-06-30", 2032, 2)


def test_project_pick_inventory_rows_seeds_future_own_pick_baseline() -> None:
    rows = project_pick_inventory_rows(
        snapshots=[
            PickInventorySnapshot(
                snapshot_id="snapshot:mem:2024-25:post_draft",
                snapshot_date="2024-07-01",
                snapshot_kind="post_draft",
                season="2024-25",
                team_code="MEM",
            )
        ],
        obligations=[],
        team_code="MEM",
        max_draft_year=2026,
    )

    assert [row.pick_id for row in rows] == [
        "pick:inventory:mem:2025:r1:own",
        "pick:inventory:mem:2025:r2:own",
        "pick:inventory:mem:2026:r1:own",
        "pick:inventory:mem:2026:r2:own",
    ]
    assert all(row.holding_status == "owned" for row in rows)


def test_project_pick_inventory_applies_incoming_and_outgoing_obligations_by_date() -> None:
    snapshots = [
        PickInventorySnapshot(
            snapshot_id="snapshot:mem:2024-25:season_closing",
            snapshot_date="2025-06-30",
            snapshot_kind="season_closing",
            season="2024-25",
            team_code="MEM",
        ),
        PickInventorySnapshot(
            snapshot_id="snapshot:mem:2025-26:post_draft",
            snapshot_date="2025-07-01",
            snapshot_kind="post_draft",
            season="2025-26",
            team_code="MEM",
        ),
    ]
    obligations = [
        PickInventoryObligation(
            obligation_id="obligation:incoming:2028:orl",
            effective_date="2025-06-15",
            team_code="MEM",
            draft_year=2028,
            round_number=1,
            original_team="ORL",
            direction="incoming",
            holding_status="owned",
            obligation_type="traded_pick",
            confidence="curated",
        ),
        PickInventoryObligation(
            obligation_id="obligation:outgoing:2026:mem",
            effective_date="2025-06-15",
            team_code="MEM",
            draft_year=2026,
            round_number=1,
            original_team="MEM",
            direction="outgoing",
            holding_status="encumbered",
            obligation_type="swap",
            confidence="uncertain",
        ),
    ]

    rows = project_pick_inventory_rows(
        snapshots=snapshots,
        obligations=obligations,
        team_code="MEM",
        max_draft_year=2028,
    )

    closing_rows = [row for row in rows if row.snapshot_id == "snapshot:mem:2024-25:season_closing"]
    post_draft_rows = [row for row in rows if row.snapshot_id == "snapshot:mem:2025-26:post_draft"]
    own_2026_first = next(row for row in closing_rows if row.pick_id == build_own_pick_id("MEM", 2026, 1))
    incoming_orlando = [row for row in closing_rows if row.original_team == "ORL"]

    assert own_2026_first.holding_status == "encumbered"
    assert own_2026_first.source_obligation_id == "obligation:outgoing:2026:mem"
    assert len(incoming_orlando) == 1
    assert incoming_orlando[0].holding_status == "owned"
    assert len(post_draft_rows) == len(closing_rows)


def test_obligation_pick_id_uses_pick_slot_not_obligation_id() -> None:
    incoming_obligation = PickInventoryObligation(
        obligation_id="obligation:incoming:2028:orl",
        effective_date="2025-06-15",
        perspective_team_code="MEM",
        owner_team_code="MEM",
        original_team_code="ORL",
        draft_year=2028,
        round_number=1,
        direction="incoming",
        holding_status="owned",
        obligation_type="traded_pick",
    )
    outgoing_obligation = PickInventoryObligation(
        obligation_id="obligation:outgoing:2028:orl",
        effective_date="2026-02-10",
        perspective_team_code="MEM",
        owner_team_code="ORL",
        original_team_code="ORL",
        draft_year=2028,
        round_number=1,
        direction="outgoing",
        holding_status="owed_out",
        obligation_type="traded_pick",
    )

    assert build_obligation_pick_id(incoming_obligation) == "pick:inventory:mem:2028:r1:orl"
    assert build_obligation_pick_id(outgoing_obligation) == build_obligation_pick_id(incoming_obligation)


def test_project_pick_inventory_replaces_non_mem_incoming_with_later_outgoing() -> None:
    rows = project_pick_inventory_rows(
        snapshots=[
            PickInventorySnapshot(
                snapshot_id="snapshot:mem:2026-27:post_deadline",
                snapshot_date="2027-02-11",
                snapshot_kind="post_deadline",
                season="2026-27",
                team_code="MEM",
            )
        ],
        obligations=[
            PickInventoryObligation(
                obligation_id="obligation:incoming:2028:orl",
                effective_date="2025-06-15",
                perspective_team_code="MEM",
                owner_team_code="MEM",
                original_team_code="ORL",
                draft_year=2028,
                round_number=1,
                direction="incoming",
                holding_status="owned",
                obligation_type="traded_pick",
            ),
            PickInventoryObligation(
                obligation_id="obligation:outgoing:2028:orl",
                effective_date="2026-02-10",
                perspective_team_code="MEM",
                owner_team_code="ORL",
                original_team_code="ORL",
                draft_year=2028,
                round_number=1,
                direction="outgoing",
                holding_status="owed_out",
                obligation_type="traded_pick",
            ),
        ],
        team_code="MEM",
        max_draft_year=2028,
    )

    orlando_rows = [row for row in rows if row.pick_id == "pick:inventory:mem:2028:r1:orl"]

    assert len(orlando_rows) == 1
    assert orlando_rows[0].holding_status == "owed_out"
    assert orlando_rows[0].source_obligation_id == "obligation:outgoing:2028:orl"


def test_project_pick_inventory_drops_resolved_picks_after_draft_date() -> None:
    rows = project_pick_inventory_rows(
        snapshots=[
            PickInventorySnapshot(
                snapshot_id="snapshot:mem:2025-26:season_closing",
                snapshot_date="2026-06-30",
                snapshot_kind="season_closing",
                season="2025-26",
                team_code="MEM",
            )
        ],
        obligations=[
            PickInventoryObligation(
                obligation_id="obligation:incoming:2026:lac",
                effective_date="2023-02-09",
                team_code="MEM",
                draft_year=2026,
                round_number=2,
                original_team="LAC",
                direction="incoming",
                holding_status="owned",
                obligation_type="traded_pick",
            )
        ],
        team_code="MEM",
        max_draft_year=2027,
    )

    assert all(row.draft_year != 2026 for row in rows)


def test_pick_inventory_obligation_preview_blocks_missing_required_source_metadata() -> None:
    legacy_row = PickInventoryObligation(
        obligation_id="obligation:legacy",
        effective_date="2025-06-15",
        team_code="MEM",
        original_team="ORL",
        draft_year=2028,
        round_number=1,
        direction="incoming",
        holding_status="owned",
        obligation_type="traded_pick",
        source_urls=["https://example.com/source"],
        confidence="curated",
    )
    fixture = PickInventoryFixture(
        fixture_id="test",
        team_code="MEM",
        rows=[legacy_row],
        row_field_names={
            "obligation:legacy": {
                "obligation_id",
                "effective_date",
                "team_code",
                "original_team",
                "draft_year",
                "round_number",
                "direction",
                "holding_status",
                "obligation_type",
                "source_urls",
                "confidence",
            }
        },
    )

    preview = build_pick_inventory_obligation_preview(
        fixture=fixture,
        fixture_path=__file__,
        team_code="MEM",
        existing_rows=[],
    )

    assert preview.ready_rows == 0
    assert preview.blocked_rows == 1
    assert "loadable rows require perspective_team_code" in preview.rows[0].issues
    assert "loadable rows require owner_team_code" in preview.rows[0].issues
    assert "loadable rows require original_team_code" in preview.rows[0].issues
    assert "loadable rows require at least one source label" in preview.rows[0].issues
    assert "loadable rows require retrieved_at" in preview.rows[0].issues


def test_pick_inventory_obligation_preview_blocks_uncertain_loadable_rows() -> None:
    uncertain_row = make_obligation("obligation:uncertain", confidence="uncertain")
    fixture = PickInventoryFixture(
        fixture_id="test",
        team_code="MEM",
        rows=[uncertain_row],
        row_field_names={"obligation:uncertain": set(uncertain_row.model_dump(mode="json"))},
    )

    preview = build_pick_inventory_obligation_preview(
        fixture=fixture,
        fixture_path=__file__,
        team_code="MEM",
        existing_rows=[],
    )

    assert preview.ready_rows == 0
    assert preview.blocked_rows == 1
    assert "uncertain rows cannot be loadable" in preview.rows[0].issues


def test_pick_inventory_obligation_preview_excludes_loadable_false_rows_from_writes() -> None:
    blocked_documentation_row = make_obligation("obligation:documented-only", loadable=False)
    fixture = PickInventoryFixture(
        fixture_id="test",
        team_code="MEM",
        rows=[blocked_documentation_row],
        row_field_names={"obligation:documented-only": set(blocked_documentation_row.model_dump(mode="json"))},
    )

    preview = build_pick_inventory_obligation_preview(
        fixture=fixture,
        fixture_path=__file__,
        team_code="MEM",
        existing_rows=[],
    )

    assert preview.blocked_rows == 0
    assert preview.ready_rows == 0
    assert preview.rows[0].existing_status == "not_loadable"


def test_pick_inventory_obligation_preview_blocks_conflicts_without_allow_updates() -> None:
    fixture_row = make_obligation("obligation:correction")
    existing_row = ExistingPickInventoryObligation(
        obligation_id="obligation:correction",
        effective_date=fixture_row.effective_date,
        perspective_team_code=fixture_row.perspective_team_code or "MEM",
        owner_team_code="UNKNOWN",
        original_team_code=fixture_row.original_team_code or "ORL",
        draft_year=fixture_row.draft_year,
        round_number=fixture_row.round_number,
        direction=fixture_row.direction,
        holding_status=fixture_row.holding_status,
        obligation_type=fixture_row.obligation_type,
        confidence=fixture_row.confidence,
        loadable=fixture_row.loadable,
    )
    fixture = PickInventoryFixture(
        fixture_id="test",
        team_code="MEM",
        rows=[fixture_row],
        row_field_names={"obligation:correction": set(fixture_row.model_dump(mode="json"))},
    )

    preview = build_pick_inventory_obligation_preview(
        fixture=fixture,
        fixture_path=__file__,
        team_code="MEM",
        existing_rows=[existing_row],
    )

    assert preview.blocked_rows == 1
    assert preview.ready_rows == 0
    assert preview.existing_conflicting_rows == 1
    assert "conflicts with the fixture row" in preview.rows[0].issues[0]


def test_pick_inventory_obligation_preview_allows_explicit_source_backed_update_ids() -> None:
    fixture_row = make_obligation("obligation:correction")
    existing_row = ExistingPickInventoryObligation(
        obligation_id="obligation:correction",
        effective_date=fixture_row.effective_date,
        perspective_team_code=fixture_row.perspective_team_code or "MEM",
        owner_team_code="UNKNOWN",
        original_team_code=fixture_row.original_team_code or "ORL",
        draft_year=fixture_row.draft_year,
        round_number=fixture_row.round_number,
        direction=fixture_row.direction,
        holding_status=fixture_row.holding_status,
        obligation_type=fixture_row.obligation_type,
        confidence=fixture_row.confidence,
        loadable=fixture_row.loadable,
    )
    fixture = PickInventoryFixture(
        fixture_id="test",
        team_code="MEM",
        rows=[fixture_row],
        row_field_names={"obligation:correction": set(fixture_row.model_dump(mode="json"))},
    )

    preview = build_pick_inventory_obligation_preview(
        fixture=fixture,
        fixture_path=__file__,
        team_code="MEM",
        existing_rows=[existing_row],
        allow_update_ids={"obligation:correction"},
    )

    assert preview.blocked_rows == 0
    assert preview.ready_rows == 1
    assert preview.existing_conflicting_rows == 1
    assert preview.rows[0].issues == []
    assert "explicitly listed in allow_update_ids" in preview.rows[0].warnings[0]


def test_projectable_future_pick_obligations_excludes_documentation_rows(tmp_path) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        """
        {
          "fixture_id": "test",
          "team_code": "MEM",
          "rows": [
            {
              "obligation_id": "obligation:ready",
              "effective_date": "2025-06-15",
              "perspective_team_code": "MEM",
              "owner_team_code": "MEM",
              "original_team_code": "ORL",
              "draft_year": 2028,
              "round_number": 1,
              "direction": "incoming",
              "holding_status": "owned",
              "obligation_type": "traded_pick",
              "source_urls": ["https://example.com/source"],
              "source_labels": ["Example source"],
              "retrieved_at": "2026-05-14T00:00:00Z",
              "confidence": "validated",
              "loadable": true
            },
            {
              "obligation_id": "obligation:documentation-only",
              "effective_date": "2025-06-15",
              "perspective_team_code": "MEM",
              "owner_team_code": "MEM",
              "original_team_code": "ORL",
              "draft_year": 2029,
              "round_number": 2,
              "direction": "incoming",
              "holding_status": "conditional",
              "obligation_type": "conditional_fallback",
              "source_urls": ["https://example.com/source"],
              "source_labels": ["Example source"],
              "retrieved_at": "2026-05-14T00:00:00Z",
              "confidence": "uncertain",
              "loadable": false
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    rows = load_projectable_future_pick_obligations(fixture_path)

    assert [row.obligation_id for row in rows] == ["obligation:ready"]


def test_pick_inventory_obligation_load_rows_and_entity_rows_use_ready_rows_only() -> None:
    ready_row = make_obligation("obligation:ready")
    documented_row = make_obligation("obligation:documented-only", loadable=False)
    fixture = PickInventoryFixture(
        fixture_id="test",
        team_code="MEM",
        rows=[ready_row, documented_row],
        row_field_names={
            "obligation:ready": set(ready_row.model_dump(mode="json")),
            "obligation:documented-only": set(documented_row.model_dump(mode="json")),
        },
    )
    preview = build_pick_inventory_obligation_preview(
        fixture=fixture,
        fixture_path=__file__,
        team_code="MEM",
        existing_rows=[],
    )

    obligation_rows = build_pick_inventory_obligation_rows(fixture, preview)
    pick_rows, asset_rows = build_pick_and_asset_rows_for_obligations([ready_row])

    assert [row.obligation_id for row in obligation_rows] == ["obligation:ready"]
    assert obligation_rows[0].owner_team_code == "MEM"
    assert obligation_rows[0].original_team_code == "ORL"
    assert obligation_rows[0].source_labels == ["Example source"]
    assert len(pick_rows) == 1
    assert len(asset_rows) == 1
    assert asset_rows[0].pick_id == pick_rows[0].pick_id


def test_roster_snapshot_pick_rows_preserve_obligation_metadata() -> None:
    rows = project_pick_inventory_rows(
        snapshots=[
            PickInventorySnapshot(
                snapshot_id="snapshot:mem:2026-27:post_draft",
                snapshot_date="2026-07-01",
                snapshot_kind="post_draft",
                season="2026-27",
                team_code="MEM",
            )
        ],
        obligations=[make_obligation("obligation:ready", confidence="validated")],
        team_code="MEM",
        max_draft_year=2028,
    )
    snapshot_pick_rows = build_roster_snapshot_pick_rows(rows)
    incoming_row = next(row for row in snapshot_pick_rows if row.source_obligation_id == "obligation:ready")

    assert incoming_row.confidence == "validated"
    assert incoming_row.notes == "Curated test obligation."
    assert incoming_row.holding_status == "owned"


def test_pick_inventory_snapshot_dry_run_projects_rows_without_writing() -> None:
    result = build_pick_inventory_snapshot_load_result(
        database_url="unused",
        snapshots=[
            PickInventorySnapshot(
                snapshot_id="snapshot:mem:2026-27:post_draft",
                snapshot_date="2026-07-01",
                snapshot_kind="post_draft",
                season="2026-27",
                team_code="MEM",
            )
        ],
        obligations=[make_obligation("obligation:ready")],
        existing_snapshot_pick_rows=0,
        team_code="MEM",
        max_draft_year=2028,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.rows_written == 0
    assert result.projected_rows > 0
    assert result.picks_upserted > 0
    assert result.assets_upserted == result.picks_upserted
    assert any(row["source_obligation_id"] == "obligation:ready" for row in result.sample_rows)


def test_pick_inventory_snapshot_load_blocks_uncertain_loaded_obligations() -> None:
    result = build_pick_inventory_snapshot_load_result(
        database_url="unused",
        snapshots=[],
        obligations=[make_obligation("obligation:uncertain", confidence="uncertain")],
        existing_snapshot_pick_rows=0,
        team_code="MEM",
        max_draft_year=2028,
        dry_run=True,
    )

    assert result.blocked_obligations == 1
    assert result.projected_rows == 0
    assert "uncertain obligations cannot be projected" in result.warnings[0]
