import pytest

import foundation.draft_prior_owner as draft_prior_owner
from foundation.draft_prior_owner import DraftPriorOwnerLineageRow
from foundation.draft_prior_owner import DraftSelectionForPriorOwnerLineage
from foundation.draft_prior_owner import build_draft_prior_owner_lineage_rows
from foundation.draft_prior_owner import build_own_pick_id
from foundation.draft_prior_owner import load_draft_prior_owner_lineage
from foundation.draft_prior_owner import preview_draft_prior_owner_lineage
from foundation.draft_resolution import PickCandidateForResolution
from foundation.pick_inventory import PickInventoryObligation


def make_selection(
    draft_selection_id: str = "draft:2024:9",
    *,
    pick_overall: int = 9,
    round_number: int = 1,
    pick_id: str | None = None,
) -> DraftSelectionForPriorOwnerLineage:
    return DraftSelectionForPriorOwnerLineage(
        draft_selection_id=draft_selection_id,
        draft_year=2024,
        pick_overall=pick_overall,
        round_number=round_number,
        team_code="MEM",
        player_id=f"player:{draft_selection_id.split(':')[-1]}",
        player_name="Test Player",
        pick_id=pick_id,
    )


def make_obligation(
    obligation_id: str,
    *,
    owner_team_code: str,
    original_team_code: str,
    direction: str,
    holding_status: str,
    round_number: int = 1,
) -> PickInventoryObligation:
    return PickInventoryObligation(
        obligation_id=obligation_id,
        effective_date="2024-06-20",
        perspective_team_code="MEM",
        owner_team_code=owner_team_code,
        original_team_code=original_team_code,
        draft_year=2024,
        round_number=round_number,
        direction=direction,  # type: ignore[arg-type]
        holding_status=holding_status,  # type: ignore[arg-type]
        obligation_type="traded_pick",
        source_urls=["https://example.com/source"],
        source_labels=["Example source"],
        retrieved_at="2026-05-27T00:00:00Z",
        confidence="curated",
        loadable=True,
    )


def test_draft_prior_owner_lineage_prefers_existing_non_slot_pick_link() -> None:
    rows = build_draft_prior_owner_lineage_rows(
        selections=[make_selection(pick_id="pick:inventory:mem:2024:r1:orl")],
        pick_candidates=[
            PickCandidateForResolution(
                pick_id="pick:inventory:mem:2024:r1:orl",
                asset_id="asset:pick:pick:inventory:mem:2024:r1:orl",
                draft_year=2024,
                round_number=1,
                original_team="ORL",
                raw_text="2024 round 1 ORL pick inventory row",
            )
        ],
        obligations=[],
    )

    assert len(rows) == 1
    assert rows[0].status == "resolved"
    assert rows[0].resolution_kind == "resolved_pick_original_team"
    assert rows[0].pick_id == "pick:inventory:mem:2024:r1:orl"
    assert rows[0].original_team_code == "ORL"
    assert rows[0].confidence == "high"


def test_draft_prior_owner_lineage_applies_curated_override_before_inventory_fallback() -> None:
    rows = build_draft_prior_owner_lineage_rows(
        selections=[make_selection("draft:2024:57", pick_overall=57, round_number=2)],
        pick_candidates=[],
        obligations=[],
        overrides=[
            draft_prior_owner.DraftPriorOwnerOverrideRow(
                draft_selection_id="draft:2024:57",
                draft_year=2024,
                round_number=2,
                pick_overall=57,
                team_code="MEM",
                original_team_code="OKC",
                source_locator="https://example.com/override",
                notes="Curated source-backed override.",
            )
        ],
    )

    assert rows[0].status == "resolved"
    assert rows[0].resolution_kind == "curated_override"
    assert rows[0].pick_id == "pick:inventory:mem:2024:r2:okc"
    assert rows[0].original_team_code == "OKC"
    assert rows[0].confidence == "high"


def test_draft_prior_owner_lineage_uses_single_controlled_inventory_candidate() -> None:
    rows = build_draft_prior_owner_lineage_rows(
        selections=[make_selection()],
        pick_candidates=[],
        obligations=[
            make_obligation(
                "obligation:outgoing:2024:mem",
                owner_team_code="UNKNOWN",
                original_team_code="MEM",
                direction="outgoing",
                holding_status="owed_out",
            ),
            make_obligation(
                "obligation:incoming:2024:orl",
                owner_team_code="MEM",
                original_team_code="ORL",
                direction="incoming",
                holding_status="owned",
            ),
        ],
    )

    assert rows[0].status == "resolved"
    assert rows[0].resolution_kind == "inventory_single_candidate"
    assert rows[0].pick_id == "pick:inventory:mem:2024:r1:orl"
    assert rows[0].source_obligation_id == "obligation:incoming:2024:orl"
    assert rows[0].original_team_code == "ORL"
    assert rows[0].confidence == "medium"


def test_draft_prior_owner_lineage_falls_back_to_own_pick_baseline() -> None:
    rows = build_draft_prior_owner_lineage_rows(
        selections=[make_selection()],
        pick_candidates=[],
        obligations=[],
    )

    assert rows[0].status == "resolved"
    assert rows[0].resolution_kind == "team_default_fallback"
    assert rows[0].pick_id == build_own_pick_id("MEM", 2024, 1)
    assert rows[0].original_team_code == "MEM"
    assert rows[0].confidence == "low"


def test_draft_prior_owner_lineage_reports_ambiguous_multiple_controlled_candidates() -> None:
    rows = build_draft_prior_owner_lineage_rows(
        selections=[make_selection()],
        pick_candidates=[],
        obligations=[
            make_obligation(
                "obligation:outgoing:2024:mem",
                owner_team_code="UNKNOWN",
                original_team_code="MEM",
                direction="outgoing",
                holding_status="owed_out",
            ),
            make_obligation(
                "obligation:incoming:2024:orl",
                owner_team_code="MEM",
                original_team_code="ORL",
                direction="incoming",
                holding_status="owned",
            ),
            make_obligation(
                "obligation:incoming:2024:lal",
                owner_team_code="MEM",
                original_team_code="LAL",
                direction="incoming",
                holding_status="owned",
            ),
        ],
    )

    assert rows[0].status == "ambiguous"
    assert rows[0].resolution_kind is None
    assert rows[0].pick_id is None
    assert rows[0].candidate_pick_ids == [
        "pick:inventory:mem:2024:r1:lal",
        "pick:inventory:mem:2024:r1:orl",
    ]


def test_draft_prior_owner_lineage_does_not_reuse_single_candidate_for_multiple_same_round_selections() -> None:
    rows = build_draft_prior_owner_lineage_rows(
        selections=[
            make_selection("draft:2024:39", pick_overall=39, round_number=2),
            make_selection("draft:2024:57", pick_overall=57, round_number=2),
        ],
        pick_candidates=[],
        obligations=[
            make_obligation(
                "obligation:outgoing:2024:mem:r2",
                owner_team_code="UNKNOWN",
                original_team_code="MEM",
                direction="outgoing",
                holding_status="owed_out",
                round_number=2,
            ),
            make_obligation(
                "obligation:incoming:2024:atl:r2",
                owner_team_code="MEM",
                original_team_code="ATL",
                direction="incoming",
                holding_status="owned",
                round_number=2,
            ),
        ],
    )

    assert len(rows) == 2
    assert all(row.status == "ambiguous" for row in rows)
    assert all("multiple Memphis selections share this draft year and round" in row.reason for row in rows)


def test_preview_draft_prior_owner_lineage_summarizes_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        draft_prior_owner,
        "build_draft_prior_owner_lineage_rows_from_database",
        lambda *args, **kwargs: [
            DraftPriorOwnerLineageRow(
                draft_prior_owner_lineage_id="draft-prior-owner-lineage:draft:2024:9",
                draft_selection_id="draft:2024:9",
                pick_id="pick:inventory:mem:2024:r1:own",
                pick_asset_id="asset:pick:pick:inventory:mem:2024:r1:own",
                player_id="player:test",
                draft_year=2024,
                round_number=1,
                pick_overall=9,
                team_code="MEM",
                owner_team_code="MEM",
                original_team_code="MEM",
                resolution_kind="team_default_fallback",
                confidence="low",
                status="resolved",
                reason="test",
            )
        ],
    )

    preview = preview_draft_prior_owner_lineage("postgresql://example")

    assert preview.selections == 1
    assert preview.resolved == 1
    assert preview.ambiguous == 0
    assert preview.unmatched == 0


def test_load_draft_prior_owner_lineage_dry_run_uses_preview_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    preview_row = DraftPriorOwnerLineageRow(
        draft_prior_owner_lineage_id="draft-prior-owner-lineage:draft:2024:9",
        draft_selection_id="draft:2024:9",
        pick_id="pick:inventory:mem:2024:r1:own",
        pick_asset_id="asset:pick:pick:inventory:mem:2024:r1:own",
        player_id="player:test",
        draft_year=2024,
        round_number=1,
        pick_overall=9,
        team_code="MEM",
        owner_team_code="MEM",
        original_team_code="MEM",
        resolution_kind="team_default_fallback",
        confidence="low",
        status="resolved",
        reason="test",
    )
    monkeypatch.setattr(
        draft_prior_owner,
        "preview_draft_prior_owner_lineage",
        lambda *args, **kwargs: draft_prior_owner.DraftPriorOwnerLineagePreviewResult(
            team_code="MEM",
            selections=1,
            resolved=1,
            ambiguous=0,
            unmatched=0,
            rows=[preview_row],
            known_limitations=["test limitation"],
        ),
    )

    result = load_draft_prior_owner_lineage("postgresql://example", dry_run=True)

    assert result.dry_run is True
    assert result.ready_rows == 1
    assert result.blocked_rows == 0
    assert result.picks_inserted == 1
    assert result.assets_inserted == 1
    assert result.lineages_upserted == 1
