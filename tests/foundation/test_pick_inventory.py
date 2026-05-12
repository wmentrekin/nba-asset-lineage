from foundation.pick_inventory import PickInventoryObligation
from foundation.pick_inventory import PickInventorySnapshot
from foundation.pick_inventory import build_own_pick_id
from foundation.pick_inventory import is_future_pick
from foundation.pick_inventory import project_pick_inventory_rows


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
