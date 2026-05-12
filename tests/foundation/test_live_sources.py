from pathlib import Path

from foundation.live_sources import (
    build_bref_draft_rows,
    build_bref_roster_rows,
    build_bref_source_rows,
    extract_bref_draft_rows,
    extract_bref_roster_rows,
    extract_bref_transaction_blocks,
    extract_nba_dataset_rows,
)


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
    source_records, players, selections = build_bref_draft_rows(draft_year=2019, team_code="MEM", html=html)
    assert len(source_records) == 1
    assert [player.display_name for player in players] == ["Ja Morant"]
    assert selections[0].draft_selection_id == "draft:2019:9"
    assert selections[0].team_code == "MEM"
