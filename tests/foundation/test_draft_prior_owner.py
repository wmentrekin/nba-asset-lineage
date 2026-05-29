import pytest

import foundation.draft_prior_owner as draft_prior_owner
from foundation.draft_prior_owner import DraftPriorOwnerLineageRow
from foundation.draft_prior_owner import DraftSelectionForPriorOwnerLineage
from foundation.draft_prior_owner import build_draft_prior_owner_lineage_rows
from foundation.draft_prior_owner import build_draft_prior_owner_replay_proof
from foundation.draft_prior_owner import build_own_pick_id
from foundation.draft_prior_owner import load_draft_prior_owner_lineage
from foundation.draft_prior_owner import preview_draft_prior_owner_lineage
from foundation.draft_prior_owner import preview_draft_prior_owner_replay_proof
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
    effective_date: str = "2024-06-20",
) -> PickInventoryObligation:
    return PickInventoryObligation(
        obligation_id=obligation_id,
        effective_date=effective_date,
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


def test_draft_prior_owner_lineage_uses_selection_day_inventory_when_draft_date_trade_changes_control() -> None:
    selection_day = draft_prior_owner.resolve_draft_date(2024, 2)
    rows = build_draft_prior_owner_lineage_rows(
        selections=[make_selection("draft:2024:57", pick_overall=57, round_number=2)],
        pick_candidates=[],
        obligations=[
            make_obligation(
                "obligation:outgoing:2024:mem:r2",
                owner_team_code="UNKNOWN",
                original_team_code="MEM",
                direction="outgoing",
                holding_status="owed_out",
                round_number=2,
                effective_date=selection_day,
            ),
            make_obligation(
                "obligation:incoming:2024:okc:r2",
                owner_team_code="MEM",
                original_team_code="OKC",
                direction="incoming",
                holding_status="owned",
                round_number=2,
                effective_date=selection_day,
            ),
        ],
    )

    assert rows[0].status == "resolved"
    assert rows[0].resolution_kind == "inventory_single_candidate"
    assert rows[0].pick_id == "pick:inventory:mem:2024:r2:okc"
    assert rows[0].original_team_code == "OKC"
    assert "selection-day inventory" in rows[0].reason


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


def test_build_draft_prior_owner_replay_proof_summarizes_selection_day_and_override_residue() -> None:
    override = draft_prior_owner.DraftPriorOwnerOverrideRow(
        draft_selection_id="draft:2024:57",
        draft_year=2024,
        round_number=2,
        pick_overall=57,
        team_code="MEM",
        original_team_code="OKC",
        source_locator="https://example.com/override",
        notes="Curated source-backed override.",
    )
    rows = build_draft_prior_owner_lineage_rows(
        selections=[
            make_selection(pick_id="pick:inventory:mem:2024:r1:orl"),
            make_selection("draft:2024:39", pick_overall=39, round_number=2),
            make_selection("draft:2024:57", pick_overall=57, round_number=2),
        ],
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
        overrides=[override],
    )

    proof = build_draft_prior_owner_replay_proof(
        rows=rows,
        team_code="MEM",
        overrides=[override],
    )

    assert proof.replay_coverage.status == "complete"
    assert proof.replay_coverage.total_selections == 3
    assert proof.replay_coverage.selection_day_snapshot_ids == [
        "snapshot:prior-owner:mem:2024:r1:selection_day",
        "snapshot:prior-owner:mem:2024:r2:selection_day",
    ]
    assert proof.replay_coverage.pre_draft_snapshot_ids == [
        "snapshot:prior-owner:mem:2024:r1:pre_draft",
        "snapshot:prior-owner:mem:2024:r2:pre_draft",
    ]
    assert proof.override_reliance.status == "bounded"
    assert proof.override_reliance.remaining_rows == 1
    assert proof.override_reliance.rows[0].source_locator == "https://example.com/override"
    assert proof.closure_evidence.draft_selection_closure_status == "closed"
    assert proof.closure_evidence.checkpoint_replay_status == "mixed"
    assert proof.closure_evidence.selection_day_inventory_rows == 1
    assert proof.proof_rows[1].proof_source_kind == "selection_day_inventory"
    assert proof.proof_rows[1].checkpoint_replay_supported is True
    assert proof.proof_rows[2].override_source_locator == "https://example.com/override"
    assert any("same-day effective dates" in evidence for evidence in proof.closure_evidence.evidence)


def test_build_draft_prior_owner_replay_proof_marks_open_when_rows_remain_unresolved() -> None:
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

    proof = build_draft_prior_owner_replay_proof(rows=rows, team_code="MEM")

    assert proof.replay_coverage.status == "blocked"
    assert proof.replay_coverage.blocked_selection_ids == ["draft:2024:9"]
    assert proof.override_reliance.status == "blocked"
    assert proof.closure_evidence.draft_selection_closure_status == "open"
    assert proof.closure_evidence.checkpoint_replay_status == "open"
    assert proof.proof_rows[0].proof_source_kind == "unresolved"
    assert proof.proof_rows[0].draft_selection_closure_supported is False


def test_preview_draft_prior_owner_replay_proof_wraps_preview_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    preview_row = DraftPriorOwnerLineageRow(
        draft_prior_owner_lineage_id="draft-prior-owner-lineage:draft:2024:57",
        draft_selection_id="draft:2024:57",
        pick_id="pick:inventory:mem:2024:r2:okc",
        pick_asset_id="asset:pick:pick:inventory:mem:2024:r2:okc",
        player_id="player:test",
        draft_year=2024,
        round_number=2,
        pick_overall=57,
        team_code="MEM",
        owner_team_code="MEM",
        original_team_code="OKC",
        resolution_kind="curated_override",
        confidence="high",
        status="resolved",
        reason="curated override from https://example.com/override",
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
    monkeypatch.setattr(
        draft_prior_owner,
        "load_draft_prior_owner_override_fixture",
        lambda *args, **kwargs: draft_prior_owner.DraftPriorOwnerOverrideFixture(
            fixture_id="test-fixture",
            team_code="MEM",
            rows=[
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
        ),
    )

    proof = preview_draft_prior_owner_replay_proof("postgresql://example")

    assert proof.team_code == "MEM"
    assert proof.override_reliance.rows[0].source_locator == "https://example.com/override"
    assert proof.proof_rows[0].selection_day_snapshot_id == "snapshot:prior-owner:mem:2024:r2:selection_day"
    assert "test limitation" in proof.known_limitations
