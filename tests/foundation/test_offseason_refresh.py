from pathlib import Path

from foundation.offseason_refresh import (
    DEFAULT_RECONCILIATION_PATH,
    NBA_PLAYER_MOVEMENT_SCOPE,
    load_official_promotion_manifest,
)


def test_official_2026_reconciliation_is_a_closed_seven_event_promotion_set() -> None:
    promotions = load_official_promotion_manifest(DEFAULT_RECONCILIATION_PATH)

    assert len(promotions) == 7
    assert {item["source_event_id"] for item in promotions} == {
        "team_official:2026-06-24:lopez-stirtz-okc-detroit-draft-trade",
        "nba_official:2026-06-29:morant-grant-murray-trade",
        "nba_official:2026-07-08:stewart-six-team-trade",
        "nba_official:2026-07-08:quinten-post-signing",
        "nba_official:2026-07-13:cameron-boozer-signing",
        "nba_official:2026-07-25:kentavious-caldwell-pope-waiver",
        "team_official:2026-07-27:kentavious-caldwell-pope-buyout",
    }


def test_nba_movement_scope_is_the_locked_endpoint_not_a_memphis_claim() -> None:
    assert NBA_PLAYER_MOVEMENT_SCOPE == {
        "endpoint_url": "https://stats.nba.com/js/data/playermovement/NBA_Player_Movement.json"
    }
