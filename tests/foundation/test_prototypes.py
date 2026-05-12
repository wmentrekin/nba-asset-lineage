from foundation.prototypes import (
    infer_event_type,
    normalize_bref_transaction_row,
    normalize_common_all_players_row,
    normalize_common_team_roster_row,
    parse_asset_text,
    parse_pick_text,
)


def test_parse_asset_text_splits_players_and_pick_text() -> None:
    parsed = parse_asset_text("Marcus Smart, 2028 first-round pick (via Phoenix), Jake LaRavia")
    assert parsed.players == ["Marcus Smart", "Jake LaRavia"]
    assert parsed.pick_texts == ["2028 first-round pick (via Phoenix)"]
    assert parsed.unmatched_chunks == []


def test_parse_pick_text_handles_basic_protection_text() -> None:
    parsed = parse_pick_text("2028 first-round pick (via Phoenix), top-10 protected")
    assert parsed.draft_year == 2028
    assert parsed.round_number == 1
    assert parsed.original_team == "PHX"
    assert parsed.protection_text == "top-10 protected"


def test_parse_pick_text_handles_favorability_swap_style_language() -> None:
    parsed = parse_pick_text("2026 second-round pick (least favorable Denver or Golden State)")
    assert parsed.draft_year == 2026
    assert parsed.round_number == 2
    assert parsed.swap_text == "least favorable denver or golden state"


def test_parse_pick_text_handles_shorthand_round_and_more_favorable_language() -> None:
    parsed = parse_pick_text("2025 2nd-rd pick is more favorable of HOU, OKC; became HOU pick")
    assert parsed.draft_year == 2025
    assert parsed.round_number == 2
    assert parsed.swap_text == "more favorable of hou, okc"


def test_normalize_bref_trade_row_builds_expected_shape() -> None:
    event = normalize_bref_transaction_row(
        source_record_id="bref:mem:2026",
        event_date="2026-02-05",
        acquired_text="Marcus Smart, 2028 first-round pick (via Phoenix)",
        relinquished_text="Luke Kennard, Jake LaRavia",
        note_text="Trade with Phoenix",
    )
    assert event.event_type == "trade"
    assert event.player_names_in == ["Marcus Smart"]
    assert event.player_names_out == ["Luke Kennard", "Jake LaRavia"]
    assert event.pick_text_in == ["2028 first-round pick (via Phoenix)"]
    assert event.source_group_hint == "bref:2026-02-05:trade"


def test_normalize_bref_signing_row_builds_expected_shape() -> None:
    event = normalize_bref_transaction_row(
        source_record_id="bref:mem:2025",
        event_date="2025-07-06",
        acquired_text="Cam Spencer",
        relinquished_text="",
        note_text="Signed free agent guard Cam Spencer",
    )
    assert event.event_type == "signing"
    assert event.player_names_in == ["Cam Spencer"]
    assert event.player_names_out == []


def test_infer_event_type_separates_re_signing_and_extension() -> None:
    assert infer_event_type(note_text="Re-signed Santi Aldama", acquired_text="Santi Aldama", relinquished_text="") == "re_signing"
    assert infer_event_type(note_text="Contract extension for Jaren Jackson Jr.", acquired_text="Jaren Jackson Jr.", relinquished_text="") == "extension"


def test_normalize_common_all_players_row() -> None:
    player = normalize_common_all_players_row(
        {
            "PERSON_ID": 1629630,
            "DISPLAY_FIRST_LAST": "Ja Morant",
        }
    )
    assert player.player_id == "nba:1629630"
    assert player.display_name == "Ja Morant"
    assert player.nba_player_ref == "1629630"


def test_normalize_common_team_roster_row() -> None:
    roster_entry = normalize_common_team_roster_row(
        {
            "TeamID": 1610612763,
            "SEASON": "2023-24",
            "PLAYER": "Ja Morant",
            "POSITION": "G",
            "BIRTH_DATE": "AUG 10, 1999",
            "PLAYER_ID": 1629630,
        }
    )
    assert roster_entry.team_id == "1610612763"
    assert roster_entry.season == "2023-24"
    assert roster_entry.player_id == "nba:1629630"
    assert roster_entry.position_text == "G"
