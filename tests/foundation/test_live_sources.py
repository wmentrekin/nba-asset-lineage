import json
from pathlib import Path

import pytest

from foundation import live_sources
from foundation.ingest import (
    PlayerAliasRow,
    PlayerRow,
    RosterBaselinePlayerRow,
    SourceEventRow,
    filter_canonical_source_events,
)
from foundation.live_sources import (
    BREF_SIGN_AND_TRADE_CANONICAL_EXCLUSION_REASON,
    CURATED_DRAFT_PICK_DETAIL_CANONICAL_EXCLUSION_REASON,
    NBA_PLAYER_MOVEMENT_CANONICAL_EXCLUSION_REASON,
    DEFAULT_NBA_PLAYER_MOVEMENT_FIXTURE_PATH,
    DEFAULT_OFFICIAL_RELEASE_FIXTURE_PATH,
    build_curated_draft_pick_detail_source_rows,
    build_nba_roster_reference_rows,
    build_official_release_fixture_bundle,
    build_nba_player_movement_source_rows,
    build_nba_player_movement_preview_rows,
    build_official_release_source_rows,
    build_bref_draft_rows,
    build_bref_roster_rows,
    build_bref_source_rows,
    extract_official_article_metadata,
    extract_bref_draft_rows,
    extract_bref_roster_rows,
    extract_bref_transaction_blocks,
    extract_nba_dataset_rows,
    extract_nba_player_movement_rows,
    load_curated_draft_pick_detail_sources,
    preview_official_release_sources,
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


def test_build_bref_source_rows_excludes_same_day_sign_and_trade_contract_from_canonical() -> None:
    html = """
    <li>
    <span><span>July 8, 2023</span></span>
    <p><p class="transaction ">Signed <a href="/players/b/brookdi01.html">Dillon Brooks</a> to a multi-year contract.</p></p>
    <p><p class="transaction ">As part of a 5-team trade, the Memphis Grizzlies traded <a href="/players/b/brookdi01.html">Dillon Brooks</a> to the Houston Rockets; the Houston Rockets traded <a href="/players/c/chrisjo01.html">Josh Christopher</a> to the Memphis Grizzlies.</p></p>
    </li>
    """

    _source_records, source_events = build_bref_source_rows(team_code="MEM", season_end_year=2024, html=html)

    signing = next(event for event in source_events if event.event_type == "signing")
    trade = next(event for event in source_events if event.event_type == "trade")

    assert signing.normalized_payload["canonical_exclusion_reason"] == BREF_SIGN_AND_TRADE_CANONICAL_EXCLUSION_REASON
    assert "same_day_sign_and_trade_contract_excluded" in signing.normalized_payload["extraction_notes"]
    assert "canonical_exclusion_reason" not in trade.normalized_payload


def test_filter_canonical_source_events_excludes_explicit_canonical_exclusion_reason() -> None:
    filtered = filter_canonical_source_events(
        [
            SourceEventRow(
                source_event_id="bref:1",
                source_record_id="bref:1",
                event_date="2023-07-08",
                event_type="signing",
                label="Memphis signed Dillon Brooks",
                team_scope="MEM",
                normalized_payload={
                    "player_names_in": ["Dillon Brooks"],
                    "player_names_out": [],
                    "canonical_exclusion_reason": "bref_same_day_sign_and_trade_contract",
                },
            ),
            SourceEventRow(
                source_event_id="bref:2",
                source_record_id="bref:2",
                event_date="2023-07-08",
                event_type="trade",
                label="Memphis trades Dillon Brooks",
                team_scope="MEM",
                normalized_payload={
                    "player_names_in": ["Josh Christopher"],
                    "player_names_out": ["Dillon Brooks"],
                },
            ),
        ]
    )

    assert [event.source_event_id for event in filtered] == ["bref:2"]


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
    assert rows[0]["player_identifiers"] == {
        "player_id": "1641713",
        "player_name": "GG Jackson",
        "player_name_source": "payload",
    }
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
    assert event.normalized_payload["player_names_in"] == ["GG Jackson"]
    assert event.normalized_payload["player_names_out"] == []
    assert event.normalized_payload["raw_row"]["TRANSACTION_TYPE"] == "Trade"


def test_build_nba_player_movement_source_rows_infers_trade_direction_and_description_name() -> None:
    payload = {
        "transactions": [
            {
                "TRANSACTION_DATE": "2026-02-03T00:00:00",
                "TRANSACTION_TYPE": "Trade",
                "TRANSACTION_DESCRIPTION": "Utah Jazz received guard John Konchar from Memphis Grizzlies.",
                "TEAM_ID": 1610612762.0,
                "TEAM_SLUG": "jazz",
                "PLAYER_ID": 1629723.0,
                "PLAYER_SLUG": "john-konchar",
                "GroupSort": "Trade 2025022",
                "Additional_Sort": 1610612763.0,
            },
            {
                "TRANSACTION_DATE": "2026-02-03T00:00:00",
                "TRANSACTION_TYPE": "Trade",
                "TRANSACTION_DESCRIPTION": "Memphis Grizzlies received guard Walter Clayton Jr. from Utah Jazz.",
                "TEAM_ID": 1610612763.0,
                "TEAM_SLUG": "grizzlies",
                "PLAYER_ID": 1642383.0,
                "PLAYER_SLUG": "walter-clayton-jr",
                "GroupSort": "Trade 2025022",
                "Additional_Sort": 1610612762.0,
            },
        ]
    }

    _records, events = build_nba_player_movement_source_rows(
        payload,
        source_locator="fixture://nba-player-movement",
        fetched_at="2026-05-15T00:00:00+00:00",
    )

    assert len(events) == 2
    outbound_event = next(event for event in events if "John Konchar" in event.label)
    inbound_event = next(event for event in events if "Walter Clayton Jr." in event.label)

    assert outbound_event.normalized_payload["player_names_in"] == []
    assert outbound_event.normalized_payload["player_names_out"] == ["John Konchar"]
    assert outbound_event.normalized_payload["player_direction"] == "out"
    assert outbound_event.normalized_payload["player_identifiers"] == {
        "player_id": "1629723",
        "player_slug": "john-konchar",
        "player_name": "John Konchar",
        "player_name_source": "description",
    }

    assert inbound_event.normalized_payload["player_names_in"] == ["Walter Clayton Jr."]
    assert inbound_event.normalized_payload["player_names_out"] == []
    assert inbound_event.normalized_payload["player_direction"] == "in"
    assert inbound_event.normalized_payload["player_identifiers"] == {
        "player_id": "1642383",
        "player_slug": "walter-clayton-jr",
        "player_name": "Walter Clayton Jr.",
        "player_name_source": "description",
    }


def test_build_nba_player_movement_source_rows_falls_back_to_slug_name() -> None:
    payload = {
        "transactions": [
            {
                "TRANSACTION_DATE": "2026-04-10T00:00:00",
                "TRANSACTION_TYPE": "Signing",
                "TRANSACTION_DESCRIPTION": "Memphis Grizzlies signed to a 10-Day Contract.",
                "TEAM_ID": 1610612763.0,
                "TEAM_SLUG": "grizzlies",
                "PLAYER_ID": 1631246.0,
                "PLAYER_SLUG": "vince-williams-jr",
                "GroupSort": "Signing 1148495",
                "Additional_Sort": 0.0,
            }
        ]
    }

    rows = build_nba_player_movement_preview_rows(payload, source_locator="fixture://nba-player-movement")

    assert len(rows) == 1
    assert rows[0]["player_identifiers"] == {
        "player_id": "1631246",
        "player_slug": "vince-williams-jr",
        "player_name": "Vince Williams Jr.",
        "player_name_source": "slug",
    }
    assert rows[0]["normalized_payload"]["player_direction"] == "in"


def test_load_nba_player_movement_dry_run_does_not_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = {
        "status": "ok",
        "source_system": "nba_player_movement",
        "source_type": "transactions_json",
        "source_locator": "fixture://nba-player-movement",
        "writes_to_database": False,
        "source_records": 1,
        "source_events": 2,
        "source_record_ids": ["nba_player_movement:memphis"],
        "source_event_ids": ["nba_player_movement:a", "nba_player_movement:b"],
    }
    monkeypatch.setattr(live_sources, "preview_nba_player_movement_source_rows", lambda **kwargs: preview)
    monkeypatch.setattr(
        live_sources.psycopg,
        "connect",
        lambda *args, **kwargs: pytest.fail("dry-run should not open a write connection"),
    )

    result = live_sources.load_nba_player_movement(dry_run=True)

    assert result["dry_run"] is True
    assert result["writes_to_database"] is False
    assert result["source_events"] == 2


def test_load_nba_player_movement_execute_writes_source_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"transactions": [{"TRANSACTION_TYPE": "Signing"}]}
    source_records = [
        live_sources.SourceRecordRow(
            source_record_id="nba_player_movement:memphis",
            source_system="nba_player_movement",
            source_type="transactions_json",
            source_locator="fixture://nba-player-movement",
            fetched_at="2026-05-15T00:00:00+00:00",
            raw_payload={"rows": []},
        )
    ]
    source_events = [
        live_sources.SourceEventRow(
            source_event_id="nba_player_movement:test",
            source_record_id="nba_player_movement:memphis",
            event_date="2026-04-10",
            event_type="signing",
            label="Memphis Grizzlies signed Test Player.",
            team_scope="MEM",
            source_group_hint=None,
            normalized_payload={"corroboration_only": True},
        )
    ]
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def commit(self) -> None:
            calls.append("commit")

    monkeypatch.setattr(live_sources, "read_nba_player_movement_fixture", lambda path: payload)
    monkeypatch.setattr(
        live_sources,
        "build_nba_player_movement_source_rows",
        lambda *args, **kwargs: (source_records, source_events),
    )
    monkeypatch.setattr(live_sources, "insert_source_records", lambda connection, rows: calls.append(f"records:{len(rows)}"))
    monkeypatch.setattr(
        live_sources,
        "replace_source_events_for_record",
        lambda connection, source_record_id, rows: calls.append(f"replace:{source_record_id}:{len(rows)}"),
    )
    monkeypatch.setattr(live_sources, "insert_source_events", lambda connection, rows: calls.append(f"events:{len(rows)}"))
    monkeypatch.setattr(live_sources.psycopg, "connect", lambda *args, **kwargs: FakeConnection())

    result = live_sources.load_nba_player_movement(
        "postgresql://example",
        fixture_path=Path("fixture.json"),
        execute=True,
        dry_run=False,
    )

    assert calls == ["records:1", "replace:nba_player_movement:memphis:1", "events:1", "commit"]
    assert result["dry_run"] is False
    assert result["writes_to_database"] is True
    assert result["source_records"] == 1
    assert result["source_events"] == 1


def test_extract_official_article_metadata_from_minimal_html() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Grizzlies complete trade with Pacers" />
        <meta property="og:description" content="Memphis trades Jay Huff." />
        <script type="application/ld+json">
          {"datePublished":"2025-07-06T13:15:00-05:00","dateModified":"2025-07-06T14:00:00-05:00"}
        </script>
      </head>
      <body>
        <article>
          <p>Memphis, Tenn. - The Memphis Grizzlies today announced the team acquired a future second round draft pick.</p>
        </article>
      </body>
    </html>
    """

    metadata = extract_official_article_metadata(html)

    assert metadata["title"] == "Grizzlies complete trade with Pacers"
    assert metadata["description"] == "Memphis trades Jay Huff."
    assert metadata["published_at"] == "2025-07-06T13:15:00-05:00"
    assert metadata["modified_at"] == "2025-07-06T14:00:00-05:00"
    assert "Memphis Grizzlies today announced" in str(metadata["article_text_excerpt"])
    assert metadata["html_sha1"]


def test_extract_official_article_metadata_strips_nul_bytes_from_excerpt() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Grizzlies sign David Johnson" />
      </head>
      <body>
        <article>
          <p>Memphis \x00 announced \x00 David Johnson.</p>
        </article>
      </body>
    </html>
    """

    metadata = extract_official_article_metadata(html)

    assert metadata["article_text_excerpt"] == "Memphis announced David Johnson."


def test_build_official_release_source_rows_from_fixture_payload() -> None:
    payload = {
        "articles": [
            {
                "source_record_id": "nba_official:2025-02-06:wizards-acquire-smart",
                "source_system": "nba_official",
                "source_type": "transaction_page",
                "source_locator": "https://www.nba.com/news/2024-25-nba-trade-tracker?hidenav=true",
                "source_title": "Wizards acquire Smart from Grizzlies",
                "source_published_at": "2025-02-09T14:33:00-05:00",
                "source_excerpt": "Wizards receive Marcus Smart. Grizzlies receive Marvin Bagley III, Johnny Davis and two second-round picks.",
                "events": [
                    {
                        "event_date": "2025-02-06",
                        "event_type": "trade",
                        "label": "Wizards acquire Smart from Grizzlies",
                        "player_names_in": ["Marvin Bagley III", "Johnny Davis"],
                        "player_names_out": ["Marcus Smart"],
                        "pick_text_in": ["Two second-round picks"],
                        "pick_text_out": ["2025 first-round pick (via Grizzlies)"],
                    }
                ],
            }
        ]
    }

    source_records, source_events = build_official_release_source_rows(
        payload,
        fetched_at="2026-05-17T00:00:00+00:00",
    )

    assert len(source_records) == 1
    assert len(source_events) == 1
    assert source_records[0].source_system == "nba_official"
    assert source_records[0].source_type == "transaction_page"
    assert source_records[0].raw_payload["fetch_mode"] == "fixture_metadata"
    assert source_events[0].event_type == "trade"
    assert source_events[0].normalized_payload["corroboration_only"] is True
    assert source_events[0].normalized_payload["source_system"] == "nba_official"
    assert source_events[0].normalized_payload["player_names_in"] == ["Marvin Bagley III", "Johnny Davis"]
    assert source_events[0].normalized_payload["player_names_out"] == ["Marcus Smart"]


def test_preview_official_release_sources_is_fixture_only_and_schema_free(tmp_path: Path) -> None:
    fixture_path = tmp_path / "official_release_fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "articles": [
                    {
                        "source_record_id": "team_official:2025-07-06:trade-pacers",
                        "source_system": "team_official",
                        "source_type": "press_release_article",
                        "source_locator": "https://www.nba.com/grizzlies/news/grizzlies-complete-trade-with-pacers",
                        "source_title": "Grizzlies complete trade with Pacers",
                        "events": [
                            {
                                "event_date": "2025-07-06",
                                "event_type": "trade",
                                "label": "Grizzlies complete trade with Pacers",
                                "player_names_in": [],
                                "player_names_out": ["Jay Huff"],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    preview = preview_official_release_sources(fixture_path=fixture_path)

    assert preview["status"] == "ok"
    assert preview["writes_to_database"] is False
    assert preview["fixture_path"] == str(fixture_path)
    assert preview["source_records"] == 1
    assert preview["source_events"] == 1
    assert preview["source_systems"] == ["team_official"]


def test_preview_official_release_sources_aggregates_fragment_directory(tmp_path: Path) -> None:
    fixture_path = tmp_path / "official_release_fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "articles": [
                    {
                        "source_record_id": "team_official:2025-07-06:trade-pacers",
                        "source_system": "team_official",
                        "source_type": "press_release_article",
                        "source_locator": "https://www.nba.com/grizzlies/news/grizzlies-complete-trade-with-pacers",
                        "source_title": "Grizzlies complete trade with Pacers",
                        "events": [
                            {
                                "source_event_id": "team_official:2025-07-06:trade-pacers:event:1",
                                "event_date": "2025-07-06",
                                "event_type": "trade",
                                "player_names_out": ["Jay Huff"],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fragment_dir = tmp_path / "fragments"
    fragment_dir.mkdir()
    (fragment_dir / "10_second.json").write_text(
        json.dumps(
            [
                {
                    "source_record_id": "team_official:2024-01-10:waiver",
                    "source_system": "team_official",
                    "source_type": "press_release_article",
                    "source_locator": "https://www.nba.com/grizzlies/news/waiver",
                    "source_title": "Waiver update",
                    "events": [
                        {
                            "source_event_id": "team_official:2024-01-10:waiver:event:1",
                            "event_date": "2024-01-10",
                            "event_type": "waiver",
                            "player_names_out": ["Player C"],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    (fragment_dir / "02_first.json").write_text(
        json.dumps(
            [
                {
                    "source_record_id": "team_official:2026-09-06:camp-signing",
                    "source_system": "team_official",
                    "source_type": "press_release_article",
                    "source_locator": "https://www.nba.com/grizzlies/news/camp-signing",
                    "source_title": "Camp signing",
                    "events": [
                        {
                            "source_event_id": "team_official:2026-09-06:camp-signing:event:1",
                            "event_date": "2026-09-06",
                            "event_type": "signing",
                            "player_names_in": ["Player B"],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    preview = preview_official_release_sources(
        fixture_path=fixture_path,
        fixture_fragment_dir=fragment_dir,
    )

    assert preview["status"] == "ok"
    assert preview["fixture_path"] == str(fixture_path)
    assert preview["fixture_fragment_dir"] == str(fragment_dir)
    assert preview["source_records"] == 3
    assert preview["source_events"] == 3
    assert preview["source_record_ids"] == [
        "team_official:2025-07-06:trade-pacers",
        "team_official:2026-09-06:camp-signing",
        "team_official:2024-01-10:waiver",
    ]


def test_build_official_release_source_rows_resolve_fragment_html_fixture_paths(tmp_path: Path) -> None:
    fixture_path = tmp_path / "official_release_fixture.json"
    fixture_path.write_text(json.dumps({"articles": []}), encoding="utf-8")
    fragment_dir = tmp_path / "fragments"
    fragment_dir.mkdir()
    (fragment_dir / "article.html").write_text(
        """
        <html>
          <head>
            <meta property="og:title" content="Fragment HTML title" />
          </head>
          <body>
            <article>
              <p>Fragment html excerpt.</p>
            </article>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (fragment_dir / "01_fragment.json").write_text(
        json.dumps(
            {
                "articles": [
                    {
                        "source_record_id": "team_official:2025-07-07:fragment-html",
                        "source_system": "team_official",
                        "source_type": "press_release_article",
                        "source_locator": "https://www.nba.com/grizzlies/news/fragment-html",
                        "html_fixture_path": "article.html",
                        "events": [
                            {
                                "event_date": "2025-07-07",
                                "event_type": "trade",
                                "player_names_in": ["Player D"],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = build_official_release_fixture_bundle(
        fixture_path,
        fixture_fragment_dir=fragment_dir,
    )
    source_records, _source_events = build_official_release_source_rows(
        payload,
        fixture_base_path=fixture_path.parent,
    )

    assert len(source_records) == 1
    assert source_records[0].raw_payload["fetch_mode"] == "fixture_html"
    assert source_records[0].raw_payload["source_title"] == "Fragment HTML title"
    assert source_records[0].raw_payload["article_text_excerpt"] == "Fragment html excerpt."


def test_build_official_release_fixture_bundle_rejects_duplicate_source_record_ids(tmp_path: Path) -> None:
    fixture_path = tmp_path / "official_release_fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "articles": [
                    {
                        "source_record_id": "team_official:2025-07-06:trade-pacers",
                        "source_system": "team_official",
                        "source_type": "press_release_article",
                        "source_locator": "https://www.nba.com/grizzlies/news/grizzlies-complete-trade-with-pacers",
                        "events": [
                            {
                                "source_event_id": "base:event",
                                "event_date": "2025-07-06",
                                "event_type": "trade",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fragment_dir = tmp_path / "fragments"
    fragment_dir.mkdir()
    (fragment_dir / "a.json").write_text(
        json.dumps(
            {
                "articles": [
                    {
                        "source_record_id": "team_official:2025-07-06:trade-pacers",
                        "source_system": "team_official",
                        "source_type": "press_release_article",
                        "source_locator": "https://www.nba.com/grizzlies/news/duplicate",
                        "events": [
                            {
                                "source_event_id": "fragment:event",
                                "event_date": "2025-07-06",
                                "event_type": "trade",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate official release source_record_id"):
        build_official_release_fixture_bundle(
            fixture_path,
            fixture_fragment_dir=fragment_dir,
        )


def test_build_official_release_fixture_bundle_rejects_duplicate_explicit_source_event_ids(tmp_path: Path) -> None:
    fixture_path = tmp_path / "official_release_fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "articles": [
                    {
                        "source_record_id": "team_official:2025-07-06:trade-pacers",
                        "source_system": "team_official",
                        "source_type": "press_release_article",
                        "source_locator": "https://www.nba.com/grizzlies/news/grizzlies-complete-trade-with-pacers",
                        "events": [
                            {
                                "source_event_id": "duplicate:event",
                                "event_date": "2025-07-06",
                                "event_type": "trade",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fragment_dir = tmp_path / "fragments"
    fragment_dir.mkdir()
    (fragment_dir / "a.json").write_text(
        json.dumps(
            {
                "articles": [
                    {
                        "source_record_id": "team_official:2025-07-07:different-record",
                        "source_system": "team_official",
                        "source_type": "press_release_article",
                        "source_locator": "https://www.nba.com/grizzlies/news/duplicate-event",
                        "events": [
                            {
                                "source_event_id": "duplicate:event",
                                "event_date": "2025-07-07",
                                "event_type": "signing",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate official release explicit source_event_id"):
        build_official_release_fixture_bundle(
            fixture_path,
            fixture_fragment_dir=fragment_dir,
        )


def test_load_official_release_sources_execute_writes_source_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "articles": [
            {
                "source_record_id": "team_official:2025-07-06:trade-pacers",
                "source_system": "team_official",
                "source_type": "press_release_article",
                "source_locator": "https://www.nba.com/grizzlies/news/grizzlies-complete-trade-with-pacers",
                "events": [{"event_date": "2025-07-06", "event_type": "trade", "player_names_out": ["Jay Huff"]}],
            }
        ]
    }
    source_records = [
        live_sources.SourceRecordRow(
            source_record_id="team_official:2025-07-06:trade-pacers",
            source_system="team_official",
            source_type="press_release_article",
            source_locator="https://www.nba.com/grizzlies/news/grizzlies-complete-trade-with-pacers",
            fetched_at="2026-05-17T00:00:00+00:00",
            raw_payload={"fetch_mode": "fixture_metadata"},
        )
    ]
    source_events = [
        live_sources.SourceEventRow(
            source_event_id="team_official:2025-07-06:trade-pacers:event:test",
            source_record_id="team_official:2025-07-06:trade-pacers",
            event_date="2025-07-06",
            event_type="trade",
            label="Trade",
            team_scope="MEM",
            source_group_hint=None,
            normalized_payload={"corroboration_only": True},
        )
    ]
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def commit(self) -> None:
            calls.append("commit")

    monkeypatch.setattr(live_sources, "read_official_release_fixture", lambda path: payload)
    monkeypatch.setattr(
        live_sources,
        "build_official_release_source_rows",
        lambda *args, **kwargs: (source_records, source_events),
    )
    monkeypatch.setattr(live_sources, "insert_source_records", lambda connection, rows: calls.append(f"records:{len(rows)}"))
    monkeypatch.setattr(
        live_sources,
        "replace_source_events_for_records",
        lambda connection, source_record_ids, rows: calls.append(f"replace:{len(source_record_ids)}:{len(rows)}"),
    )
    monkeypatch.setattr(live_sources, "insert_source_events", lambda connection, rows: calls.append(f"events:{len(rows)}"))
    monkeypatch.setattr(live_sources.psycopg, "connect", lambda *args, **kwargs: FakeConnection())

    result = live_sources.load_official_release_sources(
        "postgresql://example",
        fixture_path=Path("fixture.json"),
        execute=True,
        dry_run=False,
    )

    assert calls == ["records:1", "replace:1:1", "events:1", "commit"]
    assert result["dry_run"] is False
    assert result["writes_to_database"] is True
    assert result["source_records"] == 1
    assert result["source_events"] == 1


def test_load_bref_source_events_replaces_stale_rows_per_source_record(monkeypatch: pytest.MonkeyPatch) -> None:
    source_records = [
        live_sources.SourceRecordRow(
            source_record_id="bref:mem:2024:2024-01-10:1",
            source_system="basketball_reference",
            source_type="team_transactions_page",
            source_locator="fixture://bref-transactions",
            fetched_at="2026-05-15T00:00:00+00:00",
            raw_payload={"note_text": "Signed free agent forward Troy Williams."},
        ),
        live_sources.SourceRecordRow(
            source_record_id="bref:mem:2024:2024-01-10:2",
            source_system="basketball_reference",
            source_type="team_transactions_page",
            source_locator="fixture://bref-transactions",
            fetched_at="2026-05-15T00:00:00+00:00",
            raw_payload={"note_text": "Unparsed source row."},
        ),
    ]


def test_load_bref_source_events_replaces_stale_rows_per_source_record(monkeypatch: pytest.MonkeyPatch) -> None:
    source_records = [
        live_sources.SourceRecordRow(
            source_record_id="bref:mem:2024:2024-01-10:1",
            source_system="basketball_reference",
            source_type="team_transactions_page",
            source_locator="fixture://bref-transactions",
            fetched_at="2026-05-15T00:00:00+00:00",
            raw_payload={"note_text": "Signed free agent forward Troy Williams."},
        ),
        live_sources.SourceRecordRow(
            source_record_id="bref:mem:2024:2024-01-10:2",
            source_system="basketball_reference",
            source_type="team_transactions_page",
            source_locator="fixture://bref-transactions",
            fetched_at="2026-05-15T00:00:00+00:00",
            raw_payload={"note_text": "Unparsed source row."},
        ),
    ]
    source_events = [
        live_sources.SourceEventRow(
            source_event_id="bref:mem:2024:2024-01-10:1:1",
            source_record_id="bref:mem:2024:2024-01-10:1",
            event_date="2024-01-10",
            event_type="signing",
            label="Memphis signed Troy Williams",
            team_scope="MEM",
            source_group_hint="bref:2024-01-10:signing",
            normalized_payload={"player_names_in": ["Troy Williams"]},
        )
    ]
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def commit(self) -> None:
            calls.append("commit")

    monkeypatch.setattr(live_sources, "fetch_bref_transactions_html", lambda **kwargs: "<html />")
    monkeypatch.setattr(
        live_sources,
        "build_bref_source_rows",
        lambda *args, **kwargs: (source_records, source_events),
    )
    monkeypatch.setattr(live_sources, "insert_source_records", lambda connection, rows: calls.append(f"records:{len(rows)}"))
    monkeypatch.setattr(
        live_sources,
        "replace_source_events_for_record",
        lambda connection, source_record_id, rows: calls.append(f"replace:{source_record_id}:{len(rows)}"),
    )
    monkeypatch.setattr(live_sources, "insert_source_events", lambda connection, rows: calls.append(f"events:{len(rows)}"))
    monkeypatch.setattr(live_sources.psycopg, "connect", lambda *args, **kwargs: FakeConnection())

    result = live_sources.load_bref_source_events("postgresql://example", team_code="MEM", season_end_year=2024)

    assert calls == [
        "records:2",
        "replace:bref:mem:2024:2024-01-10:1:1",
        "replace:bref:mem:2024:2024-01-10:2:0",
        "events:1",
        "commit",
    ]
    assert result["source_records"] == 2
    assert result["source_events"] == 1


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


def test_build_nba_roster_reference_rows_resolves_repo_local_ids_without_writing_nba_ids() -> None:
    payload = {
        "resultSets": [
            {
                "headers": ["TeamID", "SEASON", "PLAYER", "POSITION", "BIRTH_DATE", "PLAYER_ID", "EXP"],
                "rowSet": [
                    [1610612763, "2023-24", "Ja Morant", "G", "AUG 10, 1999", 1629630, "5"],
                    [1610612763, "2023-24", "GG Jackson II", "F", "DEC 17, 2004", 1641713, "R"],
                    [1610612763, "2023-24", "New Exhibit 10", "G", None, 1999999, "0"],
                ],
            }
        ]
    }
    identity_lookup = live_sources.build_roster_reference_identity_lookup_from_rows(
        players=[
            PlayerRow(
                player_id="player:ja-morant",
                display_name="Ja Morant",
                nba_player_ref="moranja01",
            )
        ],
        baseline_players=[
            RosterBaselinePlayerRow(
                season="2023-24",
                team_code="MEM",
                player_id="player:gregory-jackson-ii",
                display_name="Gregory Jackson II",
                source_record_id="bref:mem:2024:roster",
                roster_order=12,
                nba_player_ref="jacksgg01",
            )
        ],
        aliases=[
            PlayerAliasRow(
                alias_id="alias:gg-jackson-ii",
                player_id="player:gregory-jackson-ii",
                source_system="manual",
                alias_name="GG Jackson II",
                normalized_alias_name="gg jackson ii",
                is_manual=True,
            )
        ],
    )

    source_records, baseline_rows, identity_resolution = build_nba_roster_reference_rows(
        roster_payload=payload,
        season="2023-24",
        team_id=1610612763,
        team_code="MEM",
        identity_lookup=identity_lookup,
        fetched_at="2026-05-21T00:00:00+00:00",
    )

    assert len(source_records) == 1
    assert [row.player_id for row in baseline_rows] == [
        "player:ja-morant",
        "player:gregory-jackson-ii",
        "player:new-exhibit-10",
    ]
    assert [row.nba_player_ref for row in baseline_rows] == ["moranja01", "jacksgg01", None]
    assert [row.years_experience for row in baseline_rows] == [5, 0, 0]
    assert identity_resolution == {
        "matched_player": 1,
        "matched_alias": 1,
        "generated_slug": 1,
    }
    assert source_records[0].raw_payload["identity_resolution_summary"] == identity_resolution
    assert source_records[0].raw_payload["roster_rows"][0]["PLAYER_ID"] == 1629630
    assert source_records[0].raw_payload["roster_rows"][0]["resolved_player_id"] == "player:ja-morant"


def test_load_nba_roster_reference_writes_source_records_and_roster_baselines_only(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "resultSets": [
            {
                "headers": ["TeamID", "SEASON", "PLAYER", "POSITION", "BIRTH_DATE", "PLAYER_ID", "EXP"],
                "rowSet": [
                    [1610612763, "2023-24", "Ja Morant", "G", "AUG 10, 1999", 1629630, "5"],
                    [1610612763, "2023-24", "Marcus Smart", "G", "MAR 06, 1994", 203935, "10"],
                ],
            }
        ]
    }
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def commit(self) -> None:
            calls.append("commit")

    monkeypatch.setattr(live_sources, "fetch_nba_stats_json", lambda *args, **kwargs: payload)
    monkeypatch.setattr(
        live_sources,
        "load_players_from_database",
        lambda database_url: [
            PlayerRow(player_id="player:ja-morant", display_name="Ja Morant", nba_player_ref="moranja01"),
            PlayerRow(player_id="player:marcus-smart", display_name="Marcus Smart", nba_player_ref="smartma01"),
        ],
    )
    monkeypatch.setattr(live_sources, "load_roster_baseline_players_from_database", lambda database_url: [])
    monkeypatch.setattr(live_sources, "load_player_aliases_from_database", lambda database_url: [])
    monkeypatch.setattr(live_sources, "insert_source_records", lambda connection, rows: calls.append(f"records:{len(rows)}"))
    monkeypatch.setattr(
        live_sources,
        "upsert_roster_baseline_players",
        lambda connection, rows: calls.append(f"baseline:{len(rows)}"),
    )

    def fail_upsert_players(*args: object, **kwargs: object) -> None:
        raise AssertionError("upsert_players should not be called by load_nba_roster_reference")

    monkeypatch.setattr(live_sources, "upsert_players", fail_upsert_players)
    monkeypatch.setattr(live_sources.psycopg, "connect", lambda *args, **kwargs: FakeConnection())

    result = live_sources.load_nba_roster_reference(
        "postgresql://example",
        season="2023-24",
        team_id=1610612763,
        team_code="MEM",
    )

    assert calls == ["records:1", "baseline:2", "commit"]
    assert result["source_records"] == 1
    assert result["baseline_rows"] == 2
    assert result["identity_resolution"] == {"matched_player": 2}


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


def test_build_curated_draft_pick_detail_source_rows_from_selection_truth() -> None:
    selections = [
        {
            "draft_selection_id": "draft:2019:2",
            "draft_year": 2019,
            "pick_overall": 2,
            "round_number": 1,
            "team_code": "MEM",
            "player_id": "player:ja-morant",
            "player_name": "Ja Morant",
            "source_event_id": "bref:draft:2019:pick:002",
            "event_date": "2019-06-20",
            "source_event_label": "Memphis drafts Ja Morant at No. 2",
        }
    ]

    source_records, source_events = build_curated_draft_pick_detail_source_rows(
        selections,
        team_code="MEM",
        fetched_at="2026-05-20T00:00:00+00:00",
    )

    assert len(source_records) == 1
    assert len(source_events) == 1
    assert source_records[0].source_system == "curated_fixture"
    assert source_records[0].source_type == "draft_pick_detail_projection"
    assert source_records[0].raw_payload["generation_mode"] == "loaded_draft_selection_projection"
    assert source_records[0].raw_payload["selection_ids"] == ["draft:2019:2"]

    event = source_events[0]
    assert event.source_record_id == source_records[0].source_record_id
    assert event.source_event_id == "curated_fixture:mem:draft_pick_detail:generated_v1:draft:2019:pick:002"
    assert event.event_type == "draft"
    assert event.event_date == "2019-06-20"
    assert event.source_group_hint is None
    assert event.normalized_payload["corroboration_only"] is True
    assert event.normalized_payload["canonical_exclusion_reason"] == CURATED_DRAFT_PICK_DETAIL_CANONICAL_EXCLUSION_REASON
    assert event.normalized_payload["draft_selection_id"] == "draft:2019:2"
    assert event.normalized_payload["player_names_in"] == ["Ja Morant"]
    assert event.normalized_payload["pick_text_in"] == ["2019 Memphis No. 2 overall pick"]
    assert event.normalized_payload["pick_details_in"] == [
        {
            "raw_text": "2019 Memphis No. 2 overall pick",
            "draft_selection_id": "draft:2019:2",
            "draft_year": 2019,
            "pick_overall": 2,
            "round_number": 1,
            "team_code": "MEM",
            "player_id": "player:ja-morant",
            "player_name": "Ja Morant",
        }
    ]


def test_load_curated_draft_pick_detail_sources_dry_run_does_not_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = {
        "status": "ok",
        "writes_to_database": False,
        "team_code": "MEM",
        "selection_rows": 1,
        "source_records": 1,
        "source_events": 1,
        "source_record_ids": ["curated_fixture:mem:draft_pick_detail:generated_v1"],
        "source_event_ids": ["curated_fixture:mem:draft_pick_detail:generated_v1:draft:2019:pick:002"],
    }
    monkeypatch.setattr(live_sources, "preview_curated_draft_pick_detail_sources", lambda *args, **kwargs: preview)
    monkeypatch.setattr(
        live_sources.psycopg,
        "connect",
        lambda *args, **kwargs: pytest.fail("dry-run should not open a write connection"),
    )

    result = load_curated_draft_pick_detail_sources("postgresql://example", team_code="MEM", dry_run=True)

    assert result["dry_run"] is True
    assert result["writes_to_database"] is False
    assert result["source_events"] == 1


def test_load_curated_draft_pick_detail_sources_execute_writes_source_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    selections = [
        {
            "draft_selection_id": "draft:2019:2",
            "draft_year": 2019,
            "pick_overall": 2,
            "round_number": 1,
            "team_code": "MEM",
            "player_id": "player:ja-morant",
            "player_name": "Ja Morant",
            "source_event_id": "bref:draft:2019:pick:002",
            "event_date": "2019-06-20",
            "source_event_label": "Memphis drafts Ja Morant at No. 2",
        }
    ]
    source_records = [
        live_sources.SourceRecordRow(
            source_record_id="curated_fixture:mem:draft_pick_detail:generated_v1",
            source_system="curated_fixture",
            source_type="draft_pick_detail_projection",
            source_locator="generated://foundation/draft_selection/mem/draft-pick-detail-v1",
            fetched_at="2026-05-20T00:00:00+00:00",
            raw_payload={"selection_ids": ["draft:2019:2"]},
        )
    ]
    source_events = [
        live_sources.SourceEventRow(
            source_event_id="curated_fixture:mem:draft_pick_detail:generated_v1:draft:2019:pick:002",
            source_record_id="curated_fixture:mem:draft_pick_detail:generated_v1",
            event_date="2019-06-20",
            event_type="draft",
            label="Curated draft pick detail for Memphis selecting Ja Morant at No. 2",
            team_scope="MEM",
            source_group_hint="draft:2019",
            normalized_payload={"corroboration_only": True},
        )
    ]
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def commit(self) -> None:
            calls.append("commit")

    monkeypatch.setattr(live_sources, "load_draft_pick_detail_seed_rows", lambda *args, **kwargs: selections)
    monkeypatch.setattr(
        live_sources,
        "build_curated_draft_pick_detail_source_rows",
        lambda *args, **kwargs: (source_records, source_events),
    )
    monkeypatch.setattr(live_sources, "insert_source_records", lambda connection, rows: calls.append(f"records:{len(rows)}"))
    monkeypatch.setattr(
        live_sources,
        "replace_source_events_for_record",
        lambda connection, source_record_id, rows: calls.append(f"replace:{source_record_id}:{len(rows)}"),
    )
    monkeypatch.setattr(live_sources, "insert_source_events", lambda connection, rows: calls.append(f"events:{len(rows)}"))
    monkeypatch.setattr(live_sources.psycopg, "connect", lambda *args, **kwargs: FakeConnection())

    result = load_curated_draft_pick_detail_sources(
        "postgresql://example",
        team_code="MEM",
        execute=True,
        dry_run=False,
    )

    assert calls == [
        "records:1",
        "replace:curated_fixture:mem:draft_pick_detail:generated_v1:1",
        "events:1",
        "commit",
    ]
    assert result["dry_run"] is False
    assert result["writes_to_database"] is True
    assert result["selection_rows"] == 1
    assert result["source_records"] == 1
    assert result["source_events"] == 1
