from foundation.workbench import (
    classify_sentence,
    normalize_bref_transaction_block,
    parse_asset_clause,
    run_sample_workbench,
    split_note_sentences,
)


def test_classify_sentence_prefers_trade_over_pick_wording() -> None:
    sentence = (
        "As part of a 3-team trade, the Memphis Grizzlies traded David Roddy to the Phoenix Suns; "
        "and the Phoenix Suns traded Chimezie Metu, Yuta Watanabe and a 2026 1st round draft pick "
        "to the Memphis Grizzlies"
    )
    assert classify_sentence(sentence) == "trade"


def test_parse_asset_clause_extracts_players_and_pick_sentences() -> None:
    parsed = parse_asset_clause(
        "Chimezie Metu, Yuta Watanabe and a 2026 1st round draft pick to the Memphis Grizzlies"
    )
    assert parsed.players == ["Chimezie Metu", "Yuta Watanabe"]
    assert parsed.pick_texts == ["2026 1st round draft pick to the Memphis Grizzlies"]


def test_normalize_bref_transaction_block_splits_mixed_action_day() -> None:
    result = normalize_bref_transaction_block(
        source_record_id="bref:mem:test",
        event_date="2024-01-10",
        note_text=(
            "Converted Vince Williams Jr. from a two-way contract to a regular contract. "
            "Waived Bismack Biyombo."
        ),
    )
    assert len(result.normalized_events) == 2
    assert [event.event_type for event in result.normalized_events] == ["conversion", "waiver"]


def test_normalize_bref_transaction_block_keeps_trade_with_pick_detail_attachment() -> None:
    result = normalize_bref_transaction_block(
        source_record_id="bref:mem:test-trade",
        event_date="2024-02-08",
        note_text=(
            "As part of a 3-team trade, the Memphis Grizzlies traded David Roddy to the Phoenix Suns; "
            "the Memphis Grizzlies traded Vanja Marinkovic to the Brooklyn Nets; "
            "and the Phoenix Suns traded Chimezie Metu, Yuta Watanabe and a 2026 1st round draft pick "
            "to the Memphis Grizzlies. "
            "2026 1st-rd pick is a right to swap."
        ),
    )
    assert len(result.normalized_events) == 1
    event = result.normalized_events[0]
    assert event.event_type == "trade"
    assert event.player_names_in == ["Chimezie Metu", "Yuta Watanabe"]
    assert event.player_names_out == ["David Roddy", "Vanja Marinkovic"]
    assert any("right to swap" in text for text in event.pick_text_in)
    assert any(note.startswith("pick_detail_attached:") for note in event.extraction_notes)


def test_normalize_bref_transaction_block_extracts_prefixed_free_agent_signing_participant() -> None:
    result = normalize_bref_transaction_block(
        source_record_id="bref:mem:test-signing",
        event_date="2017-07-22",
        note_text="Signed free agent forward Troy Williams as a free agent.",
    )

    assert len(result.normalized_events) == 1
    event = result.normalized_events[0]
    assert event.event_type == "signing"
    assert event.player_names_in == ["Troy Williams"]
    assert event.label == "Memphis signed Troy Williams"


def test_normalize_bref_transaction_block_extracts_prefixed_waiver_participant() -> None:
    result = normalize_bref_transaction_block(
        source_record_id="bref:mem:test-waiver",
        event_date="2014-10-25",
        note_text="Waived guard DJ Stephens.",
    )

    assert len(result.normalized_events) == 1
    event = result.normalized_events[0]
    assert event.event_type == "waiver"
    assert event.player_names_out == ["DJ Stephens"]
    assert event.label == "Memphis waived DJ Stephens"


def test_split_note_sentences_keeps_repeated_initial_names_intact() -> None:
    sentences = split_note_sentences("Signed D.J. Stephens. Waived E.J. Singler. Signed P.J. Hairston.")

    assert sentences == ["Signed D.J. Stephens", "Waived E.J. Singler", "Signed P.J. Hairston"]


def test_normalize_bref_transaction_block_extracts_initialed_signings_and_waivers() -> None:
    result = normalize_bref_transaction_block(
        source_record_id="bref:mem:test-initials",
        event_date="2014-10-25",
        note_text="Signed D.J. Stephens. Waived E.J. Singler. Signed P.J. Hairston as a free agent.",
    )

    assert [event.event_type for event in result.normalized_events] == ["signing", "waiver", "signing"]
    assert result.normalized_events[0].player_names_in == ["D.J. Stephens"]
    assert result.normalized_events[1].player_names_out == ["E.J. Singler"]
    assert result.normalized_events[2].player_names_in == ["P.J. Hairston"]


def test_normalize_bref_transaction_block_extracts_unicode_signing_participant() -> None:
    result = normalize_bref_transaction_block(
        source_record_id="bref:mem:test-unicode-signing",
        event_date="2019-07-07",
        note_text="Signed Jonas Valančiūnas as a free agent.",
    )

    assert len(result.normalized_events) == 1
    event = result.normalized_events[0]
    assert event.event_type == "signing"
    assert event.player_names_in == ["Jonas Valančiūnas"]
    assert event.label == "Memphis signed Jonas Valančiūnas"


def test_run_sample_workbench_returns_all_examples() -> None:
    bundle = run_sample_workbench()
    assert len(bundle.basketball_reference_examples) == 3
    assert bundle.common_all_players_example.display_name == "Ja Morant"
