from pathlib import Path

from foundation.live_sources import build_bref_source_rows, extract_bref_transaction_blocks, extract_nba_dataset_rows


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
