import json
from pathlib import Path

from foundation.live_sources import (
    NBA_PLAYER_MOVEMENT_CANONICAL_EXCLUSION_REASON,
    DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH,
    build_nba_player_movement_source_rows,
    build_nba_player_movement_preview_rows,
    build_bref_draft_rows,
    build_bref_roster_rows,
    build_bref_source_rows,
    extract_bref_draft_rows,
    extract_bref_roster_rows,
    extract_bref_transaction_blocks,
    extract_nba_dataset_rows,
    extract_nba_player_movement_rows,
    preview_nba_player_movement,
)
from foundation.sources import RECOGNIZED_SOURCE_SYSTEMS


def test_extract_bref_transaction_blocks_from_fixture_fragment() -> None:
    html = Path("tests/foundation/fixtures/bref_mem_2024_transactions_fragment.html").read_text(encoding="utf-8")
    blocks = extract_bref_transaction_blocks(html)
    assert len(blocks) == 3
    assert blocks[0]["event_date"] == "2023-07-11"
    assert blocks[1]["event_date"] == "2024-01-10"
    assert blocks[2]["event_date"] == "2024-01-10"


def test_build_bref_source_rows_from_fixture_fragment() -> None:
    html = Path("tests/foundation/fixtures/bref_mem_2024_transactions_fragment.html").read_text(encoding="utf-8")
    source_records, source_events = build_bref_source_rows(team_code="MEM", season_end_year=2024, html=html)
    assert len(source_records) == 3
    assert len(source_events) == 3
    assert source_events[0].event_type == "trade"
    assert source_events[1].event_type == "conversion"
    assert source_events[2].event_type == "waiver"


def test_extract_nba_dataset_rows_supports_result_sets_shape() -> None:
    payload = {
        "resultSets": [
            {
                "headers": ["PLAYER_ID", "PLAYER"],
                "rowSet": [[123, "Ja Morant"]],
            }
        ]
    }
    rows = extract_nba_dataset_rows(payload)
    assert rows == [{"PLAYER_ID": 123, "PLAYER": "Ja Morant"}]


def test_extract_nba_player_movement_rows_supports_checked_in_fixture() -> None:
    payload = DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH.read_text(encoding="utf-8")
    rows = extract_nba_player_movement_rows(json.loads(payload))
    assert len(rows) == 2
    assert rows[0]["TRANSACTION_TYPE"] == "Trade"
    assert rows[0]["TEAM_ABBREVIATION"] == "MEM"


def test_build_nba_player_movement_preview_rows_exposes_minimum_contract() -> None:
    payload = {
        "transactions": [
            {
                "transactionDate": "02/08/2024",
                "transactionType": "Trade",
                "transactionDescription": "Memphis Grizzlies acquired a fixture-only player.",
                "teamId": 1610612763,
                "teamAbbreviation": "MEM",
                "playerId": 1641713,
                "playerName": "GG Jackson",
            }
        ]
    }
    rows = build_nba_player_movement_preview_rows(payload, source_locator="fixture://nba-player-movement")
    assert len(rows) == 1
    assert rows[0]["date"] == "2024-02-08"
    assert rows[0]["transaction_type"] == "Trade"
    assert rows[0]["transaction_description"] == "Memphis Grizzlies acquired a fixture-only player."
    assert rows[0]["team_identifiers"] == {"team_id": "1610612763", "team_abbreviation": "MEM"}
    assert rows[0]["player_identifiers"] == {"player_id": "1641713", "player_name": "GG Jackson"}
    assert rows[0]["source_locator"] == "fixture://nba-player-movement#row=1"
    assert rows[0]["normalized_payload"]["normalized_event_type"] == "trade"
    assert rows[0]["normalized_payload"]["raw_row"] == payload["transactions"][0]
    assert rows[0]["source_system"] == "nba_player_movement"


def test_preview_nba_player_movement_is_fixture_only_and_schema_free() -> None:
    preview = preview_nba_player_movement()
    assert preview["status"] == "ok"
    assert preview["source_system"] == "nba_player_movement"
    assert preview["source_system"] in RECOGNIZED_SOURCE_SYSTEMS
    assert preview["fixture_only"] is True
    assert preview["writes_to_database"] is False
    assert preview["total_endpoint_rows"] == 2
    assert preview["memphis_row_count"] == 2
    assert preview["row_count"] == 2
    assert preview["date_range"] == {"start_date": "2024-01-10", "end_date": "2024-02-08"}
    assert preview["transaction_type_counts"] == {"Trade": 1, "Waive": 1}
    assert preview["preview_rows"][0]["date"] == "2024-02-08"
    assert preview["preview_rows"][0]["source_system_label"] == "nba_player_movement"


def test_nba_player_movement_memphis_filter_uses_id_slug_and_text_fallback() -> None:
    payload = {
        "transactions": [
            {"TRANSACTION_DATE": "2024-01-01", "Transaction_Type": "Signing", "TEAM_ID": 1610612763},
            {"TRANSACTION_DATE": "2024-01-02", "Transaction_Type": "Signing", "TEAM_SLUG": "grizzlies"},
            {
                "TRANSACTION_DATE": "2024-01-03",
                "Transaction_Type": "Signing",
                "TRANSACTION_DESCRIPTION": "The Memphis Grizzlies signed a sample player.",
            },
            {"TRANSACTION_DATE": "2024-01-04", "Transaction_Type": "Signing", "TEAM_ID": 1610612738},
        ]
    }
    rows = build_nba_player_movement_preview_rows(payload, source_locator="fixture://nba-player-movement")
    assert [row["date"] for row in rows] == ["2024-01-01", "2024-01-02", "2024-01-03"]


def test_build_nba_player_movement_source_rows_sets_deterministic_guarded_candidates() -> None:
    payload = json.loads(DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH.read_text(encoding="utf-8"))
    first_records, first_events = build_nba_player_movement_source_rows(
        payload,
        source_locator=str(DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH),
        fetched_at="2026-05-15T00:00:00+00:00",
    )
    second_records, second_events = build_nba_player_movement_source_rows(
        payload,
        source_locator=str(DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH),
        fetched_at="2026-05-15T00:00:00+00:00",
    )

    assert [row.source_record_id for row in first_records] == [row.source_record_id for row in second_records]
    assert [row.source_event_id for row in first_events] == [row.source_event_id for row in second_events]
    assert len(first_records) == 1
    assert len(first_events) == 2
    assert first_records[0].source_system == "nba_player_movement"
    assert first_records[0].source_type == "transactions_json"
    assert first_records[0].raw_payload["total_endpoint_rows"] == 2
    assert first_records[0].raw_payload["memphis_row_count"] == 2

    event = first_events[0]
    assert event.event_type == "trade"
    assert event.normalized_payload["raw_transaction_type"] == "Trade"
    assert event.normalized_payload["normalized_event_type"] == "trade"
    assert event.normalized_payload["corroboration_only"] is True
    assert event.normalized_payload["canonical_exclusion_reason"] == NBA_PLAYER_MOVEMENT_CANONICAL_EXCLUSION_REASON
    assert "loader compatibility only" in str(event.normalized_payload["normalization_note"])
    assert event.normalized_payload["raw_row"]["TRANSACTION_TYPE"] == "Trade"


def test_extract_bref_roster_rows_from_minimal_html() -> None:
    html = """
    <table id="roster">
      <tbody>
        <tr>
          <th data-stat="number">12</th>
          <td data-stat="player" data-append-csv="moranja01"><a href="/players/m/moranja01.html">Ja Morant</a></td>
          <td data-stat="pos">PG</td>
          <td data-stat="birth_date">August 10, 1999</td>
          <td data-stat="years_experience">4</td>
        </tr>
      </tbody>
    </table>
    """
    rows = extract_bref_roster_rows(html)
    assert rows == [
        {
            "number": "12",
            "player": "Ja Morant",
            "player_ref": "moranja01",
            "pos": "PG",
            "birth_date": "August 10, 1999",
            "years_experience": "4",
        }
    ]


def test_build_bref_roster_rows_builds_players_and_baseline_rows() -> None:
    html = """
    <table id="roster">
      <tbody>
        <tr>
          <th data-stat="number">22</th>
          <td data-stat="player" data-append-csv="banede01"><a href="/players/b/banede01.html">Desmond Bane</a></td>
          <td data-stat="pos">SG</td>
          <td data-stat="birth_date">June 25, 1998</td>
          <td data-stat="years_experience">3</td>
        </tr>
      </tbody>
    </table>
    """
    source_records, players, baseline_rows = build_bref_roster_rows(team_code="MEM", season_end_year=2024, html=html)
    assert len(source_records) == 1
    assert players[0].display_name == "Desmond Bane"
    assert baseline_rows[0].display_name == "Desmond Bane"
    assert baseline_rows[0].season == "2023-24"


def test_extract_bref_draft_rows_from_minimal_html() -> None:
    html = """
    <table id="stats">
      <tbody>
        <tr>
          <th data-stat="pick_overall">9</th>
          <td data-stat="round_number">1</td>
          <td data-stat="team_id">MEM</td>
          <td data-stat="player" data-append-csv="edeyza01"><a href="/players/e/edeyza01.html">Zach Edey</a></td>
        </tr>
      </tbody>
    </table>
    """
    rows = extract_bref_draft_rows(html)
    assert rows == [
        {
            "pick_overall": "9",
            "round_number": "1",
            "team_id": "MEM",
            "player": "Zach Edey",
            "player_ref": "edeyza01",
        }
    ]


def test_build_bref_draft_rows_builds_memphis_draft_selection() -> None:
    html = """
    <table id="stats">
      <tbody>
        <tr>
          <th data-stat="pick_overall">8</th>
          <td data-stat="round_number">1</td>
          <td data-stat="team_id">NOP</td>
          <td data-stat="player" data-append-csv="hayesja02">Jaxson Hayes</td>
        </tr>
        <tr>
          <th data-stat="pick_overall">9</th>
          <td data-stat="round_number">1</td>
          <td data-stat="team_id">MEM</td>
          <td data-stat="player" data-append-csv="moranja01">Ja Morant</td>
        </tr>
      </tbody>
    </table>
    """
    source_records, source_events, players, selections = build_bref_draft_rows(
        draft_year=2019,
        team_code="MEM",
        html=html,
    )
    assert len(source_records) == 1
    assert len(source_events) == 1
    assert [player.display_name for player in players] == ["Ja Morant"]
    assert source_events[0].source_event_id == "bref:draft:2019:pick:009"
    assert source_events[0].source_record_id == "bref:draft:2019"
    assert source_events[0].event_date == "2019-06-20"
    assert source_events[0].event_type == "draft"
    assert source_events[0].normalized_payload["draft_selection_id"] == "draft:2019:9"
    assert source_events[0].normalized_payload["player_names_in"] == ["Ja Morant"]
    assert selections[0].draft_selection_id == "draft:2019:9"
    assert selections[0].team_code == "MEM"
    assert selections[0].source_event_id == "bref:draft:2019:pick:009"
