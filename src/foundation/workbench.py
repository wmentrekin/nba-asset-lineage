from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from foundation.prototypes import (
    ParsedPickText,
    PrototypeRosterEntry,
    PrototypePlayer,
    build_participants,
    collapse_whitespace,
    normalize_common_all_players_row,
    normalize_common_team_roster_row,
    parse_pick_text,
)


WorkbenchEventType = Literal[
    "trade",
    "draft",
    "waiver",
    "signing",
    "re_signing",
    "extension",
    "conversion",
    "release",
]


@dataclass(frozen=True)
class WorkbenchAssetParse:
    players: list[str]
    pick_texts: list[str]
    pick_details: list[ParsedPickText]
    unmatched_chunks: list[str]


@dataclass(frozen=True)
class WorkbenchSourceEvent:
    source_event_id: str
    source_system: str
    source_record_id: str
    event_date: str
    event_type: WorkbenchEventType
    label: str
    team_scope: str
    source_group_hint: str | None
    participants_in: list[str]
    participants_out: list[str]
    player_names_in: list[str]
    player_names_out: list[str]
    pick_text_in: list[str]
    pick_text_out: list[str]
    pick_details_in: list[ParsedPickText]
    pick_details_out: list[ParsedPickText]
    raw_note: str | None
    extraction_notes: list[str]
    raw_payload: dict[str, object]


@dataclass(frozen=True)
class WorkbenchRowResult:
    source_record_id: str
    event_date: str
    normalized_events: list[WorkbenchSourceEvent]
    row_notes: list[str]


@dataclass(frozen=True)
class WorkbenchSampleBundle:
    basketball_reference_examples: list[WorkbenchRowResult]
    common_all_players_example: PrototypePlayer
    common_team_roster_example: PrototypeRosterEntry


MEMPHIS_OUTBOUND_PATTERN = re.compile(
    r"the memphis grizzlies traded (?P<assets>.+?) to the (?P<team>.+)$",
    re.IGNORECASE,
)
MEMPHIS_INBOUND_PATTERN = re.compile(
    r"the (?P<team>.+?) traded (?P<assets>.+?) to the memphis grizzlies$",
    re.IGNORECASE,
)
DIRECT_TRADE_PATTERN = re.compile(
    r"traded (?P<out>.+?) to the (?P<team>.+?) for (?P<in>.+)$",
    re.IGNORECASE,
)

PICK_DETAIL_PATTERNS = [
    re.compile(r"\b\d{4}\s+(?:1st|2nd|first|second)[-\s]rd?\s+pick\b.*", re.IGNORECASE),
    re.compile(r"\b\d{4}\s+(?:1st|2nd|first|second)[-\s]round draft pick\b.*", re.IGNORECASE),
]


def run_sample_workbench() -> WorkbenchSampleBundle:
    sample_data = load_sample_fixture()
    examples = [
        normalize_bref_transaction_block(
            source_record_id=entry["source_record_id"],
            event_date=entry["event_date"],
            note_text=entry["note_text"],
        )
        for entry in sample_data["basketball_reference_examples"]
    ]

    player = normalize_common_all_players_row(sample_data["common_all_players_example"])
    roster = normalize_common_team_roster_row(sample_data["common_team_roster_example"])
    return WorkbenchSampleBundle(
        basketball_reference_examples=examples,
        common_all_players_example=player,
        common_team_roster_example=roster,
    )


def normalize_bref_transaction_block(
    *,
    source_record_id: str,
    event_date: str,
    note_text: str,
    team_scope: str = "memphis-grizzlies",
) -> WorkbenchRowResult:
    sentences = split_note_sentences(note_text)
    extracted_events: list[WorkbenchSourceEvent] = []
    row_notes: list[str] = []
    pending_pick_detail_sentences: list[str] = []

    for sentence in sentences:
        event_type = classify_sentence(sentence)
        if event_type is None:
            if looks_like_pick_detail_sentence(sentence):
                pending_pick_detail_sentences.append(sentence)
            else:
                row_notes.append(f"unclassified_sentence:{sentence}")
            continue

        event = normalize_sentence_to_event(
            source_record_id=source_record_id,
            event_date=event_date,
            sentence=sentence,
            ordinal=len(extracted_events) + 1,
            team_scope=team_scope,
        )
        extracted_events.append(event)

    if pending_pick_detail_sentences:
        append_pick_detail_sentences(extracted_events, pending_pick_detail_sentences, row_notes)

    if not extracted_events:
        row_notes.append("no_events_extracted")

    return WorkbenchRowResult(
        source_record_id=source_record_id,
        event_date=event_date,
        normalized_events=extracted_events,
        row_notes=row_notes,
    )


def normalize_sentence_to_event(
    *,
    source_record_id: str,
    event_date: str,
    sentence: str,
    ordinal: int,
    team_scope: str,
) -> WorkbenchSourceEvent:
    event_type = classify_sentence(sentence)
    if event_type is None:
        raise ValueError(f"Sentence is not classifiable: {sentence}")

    extraction_notes: list[str] = []
    inbound = WorkbenchAssetParse(players=[], pick_texts=[], pick_details=[], unmatched_chunks=[])
    outbound = WorkbenchAssetParse(players=[], pick_texts=[], pick_details=[], unmatched_chunks=[])

    if event_type == "trade":
        inbound, outbound, trade_notes = parse_trade_sentence(sentence)
        extraction_notes.extend(trade_notes)
    else:
        assets = parse_asset_clause(extract_primary_asset_clause(sentence, event_type))
        extraction_notes.extend([f"unmatched:{chunk}" for chunk in assets.unmatched_chunks])
        if event_type in {"signing", "re_signing", "extension", "conversion", "draft"}:
            inbound = assets
        else:
            outbound = assets

    label = build_workbench_label(event_type=event_type, inbound=inbound, outbound=outbound)
    source_group_hint = f"bref:{event_date}:trade-group" if event_type == "trade" else f"bref:{event_date}:{event_type}"

    return WorkbenchSourceEvent(
        source_event_id=f"{source_record_id}:{ordinal}",
        source_system="basketball_reference",
        source_record_id=source_record_id,
        event_date=event_date,
        event_type=event_type,
        label=label,
        team_scope=team_scope,
        source_group_hint=source_group_hint,
        participants_in=build_participants(inbound.players, inbound.pick_texts),
        participants_out=build_participants(outbound.players, outbound.pick_texts),
        player_names_in=inbound.players,
        player_names_out=outbound.players,
        pick_text_in=inbound.pick_texts,
        pick_text_out=outbound.pick_texts,
        pick_details_in=inbound.pick_details,
        pick_details_out=outbound.pick_details,
        raw_note=sentence,
        extraction_notes=extraction_notes,
        raw_payload={"sentence": sentence},
    )


def split_note_sentences(note_text: str) -> list[str]:
    normalized = collapse_whitespace(note_text)
    normalized = normalized.replace("Jr.", "Jr<PERIOD>").replace("Sr.", "Sr<PERIOD>")
    segments = re.split(r"(?<=\.)\s+", normalized)
    restored = [segment.replace("<PERIOD>", ".") for segment in segments]
    return [segment.strip(" ;.") for segment in restored if segment.strip(" ;.")]


def classify_sentence(sentence: str) -> WorkbenchEventType | None:
    lower = sentence.lower()
    if " traded " in lower or lower.startswith("traded ") or "as part of a" in lower:
        return "trade"
    if lower.startswith("drafted "):
        return "draft"
    if lower.startswith("re-signed ") or lower.startswith("re signed "):
        return "re_signing"
    if " extension" in lower or lower.startswith("extended "):
        return "extension"
    if lower.startswith("converted "):
        return "conversion"
    if lower.startswith("waived "):
        return "waiver"
    if lower.startswith("released "):
        return "release"
    if lower.startswith("signed "):
        return "signing"
    return None


def looks_like_pick_detail_sentence(sentence: str) -> bool:
    lower = sentence.lower()
    return "pick" in lower and any(token in lower for token in ["own", "via", "swap", "protected", "favorable", "convey"])


def append_pick_detail_sentences(
    events: list[WorkbenchSourceEvent],
    detail_sentences: list[str],
    row_notes: list[str],
) -> None:
    if not events:
        row_notes.extend([f"orphan_pick_detail:{sentence}" for sentence in detail_sentences])
        return

    target_index = next((index for index in range(len(events) - 1, -1, -1) if events[index].event_type == "trade"), len(events) - 1)
    target = events[target_index]

    pick_matches: list[str] = []
    for sentence in detail_sentences:
        extracted = extract_pick_sentences(sentence)
        if extracted:
            pick_matches.extend(extracted)
        else:
            pick_matches.append(sentence)
    merged_in = list(target.pick_text_in)
    merged_out = list(target.pick_text_out)
    merged_detail_in = list(target.pick_details_in)
    merged_notes = list(target.extraction_notes)

    for pick_sentence in pick_matches:
        merged_in.append(pick_sentence)
        merged_detail_in.append(parse_pick_text(pick_sentence))
        merged_notes.append(f"pick_detail_attached:{pick_sentence}")

    events[target_index] = WorkbenchSourceEvent(
        source_event_id=target.source_event_id,
        source_system=target.source_system,
        source_record_id=target.source_record_id,
        event_date=target.event_date,
        event_type=target.event_type,
        label=target.label,
        team_scope=target.team_scope,
        source_group_hint=target.source_group_hint,
        participants_in=build_participants(target.player_names_in, merged_in),
        participants_out=build_participants(target.player_names_out, merged_out),
        player_names_in=target.player_names_in,
        player_names_out=target.player_names_out,
        pick_text_in=merged_in,
        pick_text_out=merged_out,
        pick_details_in=merged_detail_in,
        pick_details_out=target.pick_details_out,
        raw_note=target.raw_note,
        extraction_notes=merged_notes,
        raw_payload=target.raw_payload,
    )


def parse_trade_sentence(sentence: str) -> tuple[WorkbenchAssetParse, WorkbenchAssetParse, list[str]]:
    lower = sentence.lower()
    notes: list[str] = []
    inbound_players: list[str] = []
    outbound_players: list[str] = []
    inbound_picks: list[str] = []
    outbound_picks: list[str] = []
    unmatched: list[str] = []

    clauses = [clause.strip(" ;,.") for clause in re.split(r";\s*", sentence) if clause.strip(" ;,.")]
    for raw_clause in clauses:
        clause = raw_clause
        clause = re.sub(r"^as part of a \d+-team trade,\s*", "", clause, flags=re.IGNORECASE)
        clause = re.sub(r"^and the ", "the ", clause, flags=re.IGNORECASE)

        direct_match = DIRECT_TRADE_PATTERN.search(clause)

        outbound_match = MEMPHIS_OUTBOUND_PATTERN.search(clause)
        inbound_match = MEMPHIS_INBOUND_PATTERN.search(clause)

        if direct_match and clause.lower().startswith("traded "):
            out_assets = parse_asset_clause(direct_match.group("out"))
            in_assets = parse_asset_clause(direct_match.group("in"))
            outbound_players.extend(out_assets.players)
            outbound_picks.extend(out_assets.pick_texts)
            inbound_players.extend(in_assets.players)
            inbound_picks.extend(in_assets.pick_texts)
            unmatched.extend(out_assets.unmatched_chunks)
            unmatched.extend(in_assets.unmatched_chunks)
            continue

        if outbound_match:
            assets = parse_asset_clause(outbound_match.group("assets"))
            outbound_players.extend(assets.players)
            outbound_picks.extend(assets.pick_texts)
            unmatched.extend(assets.unmatched_chunks)
            continue

        if inbound_match:
            assets = parse_asset_clause(inbound_match.group("assets"))
            inbound_players.extend(assets.players)
            inbound_picks.extend(assets.pick_texts)
            unmatched.extend(assets.unmatched_chunks)
            continue

        if "trade exception" in lower:
            notes.append("trade_exception_ignored")
            continue

        notes.append(f"unparsed_trade_clause:{raw_clause}")

    inbound = WorkbenchAssetParse(
        players=inbound_players,
        pick_texts=inbound_picks,
        pick_details=[parse_pick_text(text) for text in inbound_picks],
        unmatched_chunks=unmatched,
    )
    outbound = WorkbenchAssetParse(
        players=outbound_players,
        pick_texts=outbound_picks,
        pick_details=[parse_pick_text(text) for text in outbound_picks],
        unmatched_chunks=[],
    )
    notes.extend([f"unmatched:{chunk}" for chunk in unmatched])
    return inbound, outbound, notes


def extract_primary_asset_clause(sentence: str, event_type: WorkbenchEventType) -> str:
    if event_type in {"signing", "re_signing"}:
        match = re.search(r"^(?:signed|re-signed|re signed)\s+(.+?)(?:\s+to\b|\s+for\b|$)", sentence, re.IGNORECASE)
        return match.group(1) if match else sentence
    if event_type == "extension":
        match = re.search(r"^(?:extended|contract extension for)\s+(.+?)(?:\s+to\b|\s+for\b|$)", sentence, re.IGNORECASE)
        return match.group(1) if match else sentence
    if event_type == "conversion":
        match = re.search(r"^converted\s+(.+?)\s+from\b", sentence, re.IGNORECASE)
        return match.group(1) if match else sentence
    if event_type in {"waiver", "release"}:
        match = re.search(r"^(?:waived|released)\s+(.+?)(?:$)", sentence, re.IGNORECASE)
        return match.group(1) if match else sentence
    if event_type == "draft":
        match = re.search(r"^drafted\s+(.+?)(?:\s+in\b|$)", sentence, re.IGNORECASE)
        return match.group(1) if match else sentence
    return sentence


def parse_asset_clause(text: str) -> WorkbenchAssetParse:
    cleaned = collapse_whitespace(text)
    pick_sentences = extract_pick_sentences(cleaned)
    remainder = cleaned
    for pick_text in pick_sentences:
        remainder = remainder.replace(pick_text, "")
    remainder = remainder.replace(" and ", ", ")
    name_chunks = [chunk.strip(" ,.") for chunk in remainder.split(",") if chunk.strip(" ,.")]

    players: list[str] = []
    unmatched_chunks: list[str] = []
    for chunk in name_chunks:
        if looks_like_person_name(chunk):
            players.append(chunk)
        elif chunk:
            unmatched_chunks.append(chunk)

    return WorkbenchAssetParse(
        players=players,
        pick_texts=pick_sentences,
        pick_details=[parse_pick_text(text) for text in pick_sentences],
        unmatched_chunks=unmatched_chunks,
    )


def extract_pick_sentences(text: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    for pattern in PICK_DETAIL_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), collapse_whitespace(match.group(0).strip(" .,"))))
    matches.sort(key=lambda item: item[0])

    deduped: list[str] = []
    for _, candidate in matches:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


def looks_like_person_name(text: str) -> bool:
    return bool(re.match(r"^[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,4}$", text))


def build_workbench_label(
    *,
    event_type: WorkbenchEventType,
    inbound: WorkbenchAssetParse,
    outbound: WorkbenchAssetParse,
) -> str:
    if event_type == "trade":
        return f"Memphis trade: in {summarize_assets(inbound)} / out {summarize_assets(outbound)}"
    if event_type == "signing":
        return f"Memphis signed {summarize_assets(inbound)}"
    if event_type == "re_signing":
        return f"Memphis re-signed {summarize_assets(inbound)}"
    if event_type == "extension":
        return f"Memphis extended {summarize_assets(inbound)}"
    if event_type == "conversion":
        return f"Memphis converted {summarize_assets(inbound)}"
    if event_type == "waiver":
        return f"Memphis waived {summarize_assets(outbound)}"
    if event_type == "draft":
        return f"Memphis drafted {summarize_assets(inbound)}"
    if event_type == "release":
        return f"Memphis released {summarize_assets(outbound)}"
    return f"Memphis {event_type}"


def summarize_assets(parsed: WorkbenchAssetParse) -> str:
    values = [*parsed.players, *parsed.pick_texts]
    return ", ".join(values) if values else "no tracked assets"


def serialize_sample_workbench() -> dict[str, object]:
    bundle = run_sample_workbench()
    return {
        "basketball_reference_examples": [
            {
                "source_record_id": row.source_record_id,
                "event_date": row.event_date,
                "row_notes": row.row_notes,
                "normalized_events": [
                    {
                        **asdict(event),
                        "pick_details_in": [asdict(detail) for detail in event.pick_details_in],
                        "pick_details_out": [asdict(detail) for detail in event.pick_details_out],
                    }
                    for event in row.normalized_events
                ],
            }
            for row in bundle.basketball_reference_examples
        ],
        "common_all_players_example": asdict(bundle.common_all_players_example),
        "common_team_roster_example": asdict(bundle.common_team_roster_example),
    }


def load_sample_fixture() -> dict[str, object]:
    fixture_path = Path("tests/foundation/fixtures/workbench_samples.json")
    return json.loads(fixture_path.read_text(encoding="utf-8"))
