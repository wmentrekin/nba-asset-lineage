from foundation.ingest import RosterSnapshotValidationRow
from foundation.roster_validation import build_roster_snapshot_validation_rows_from_inputs


def test_build_roster_snapshot_validation_rows_matches_by_player_id_and_alias() -> None:
    rows = build_roster_snapshot_validation_rows_from_inputs(
        snapshots=[
            {
                "snapshot_id": "snapshot:mem:2023-24:season_opening",
                "snapshot_date": "2023-10-01",
                "snapshot_kind": "season_opening",
                "season": "2023-24",
                "team_code": "MEM",
                "players": [
                    {"player_id": "player:ja-morant", "display_name": "Ja Morant"},
                    {"player_id": "player:gregory-jackson-ii", "display_name": "Gregory Jackson II"},
                ],
            }
        ],
        references_by_season={
            ("MEM", "2023-24"): {
                "source_record_id": "nba_stats:common_team_roster:2023-24:1610612763",
                "player_count": 15,
                "player_ids": {"player:ja-morant"},
                "name_keys": {"gg jackson ii", "ggjacksonii", "ja morant", "jamorant"},
            }
        },
        alias_names_by_player_id={
            "player:gregory-jackson-ii": {"GG Jackson II"},
        },
    )

    assert rows == [
        RosterSnapshotValidationRow(
            snapshot_id="snapshot:mem:2023-24:season_opening",
            validation_status="season_reference_backed",
            reference_source_record_id="nba_stats:common_team_roster:2023-24:1610612763",
            snapshot_player_count=2,
            reference_player_count=15,
            matched_player_count=2,
            notes=(
                "Season-scoped NBA Stats CommonTeamRoster reference matched 2 of 2 snapshot players "
                "against 15 official roster rows. This validates season membership only and does not prove "
                "exact day-of-checkpoint official occupancy."
            ),
        )
    ]


def test_build_roster_snapshot_validation_rows_marks_missing_source_and_incomplete() -> None:
    rows = build_roster_snapshot_validation_rows_from_inputs(
        snapshots=[
            {
                "snapshot_id": "snapshot:mem:2021-22:post_draft",
                "snapshot_date": "2021-07-01",
                "snapshot_kind": "post_draft",
                "season": "2021-22",
                "team_code": "MEM",
                "players": [
                    {"player_id": "player:ja-morant", "display_name": "Ja Morant"},
                ],
            },
            {
                "snapshot_id": "snapshot:mem:2023-24:post_draft",
                "snapshot_date": "2023-07-01",
                "snapshot_kind": "post_draft",
                "season": "2023-24",
                "team_code": "MEM",
                "players": [
                    {"player_id": "player:ja-morant", "display_name": "Ja Morant"},
                    {"player_id": "player:unknown-prospect", "display_name": "Unknown Prospect"},
                ],
            },
        ],
        references_by_season={
            ("MEM", "2023-24"): {
                "source_record_id": "nba_stats:common_team_roster:2023-24:1610612763",
                "player_count": 14,
                "player_ids": {"player:ja-morant"},
                "name_keys": {"ja morant", "jamorant"},
            }
        },
        alias_names_by_player_id={},
    )

    assert rows[0].validation_status == "source_missing"
    assert rows[0].matched_player_count == 0
    assert rows[1].validation_status == "season_reference_incomplete"
    assert rows[1].matched_player_count == 1
    assert "Unknown Prospect" in str(rows[1].notes)
