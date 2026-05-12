from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


SourceEventType = Literal[
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
class ParsedAssetText:
    players: list[str]
    pick_texts: list[str]
    unmatched_chunks: list[str]


@dataclass(frozen=True)
class PrototypeSourceEvent:
    source_system: str
    source_record_id: str
    event_date: str
    event_type: SourceEventType
    label: str
    team_scope: str
    source_group_hint: str | None
    participants_in: list[str]
    participants_out: list[str]
    pick_text_in: list[str]
    pick_text_out: list[str]
    player_names_in: list[str]
    player_names_out: list[str]
    raw_note: str | None
    raw_payload: dict[str, object]


@dataclass(frozen=True)
class PrototypePlayer:
    player_id: str
    display_name: str
    nba_player_ref: str
    birth_date: str | None = None
    position_text: str | None = None


@dataclass(frozen=True)
class PrototypeRosterEntry:
    season: str
    team_id: str
    player_id: str
    display_name: str
    position_text: str | None = None
    birth_date: str | None = None


@dataclass(frozen=True)
class ParsedPickText:
    raw_text: str
    draft_year: int | None
    round_number: int | None
    original_team: str | None
    protection_text: str | None
    swap_text: str | None


ORDINAL_TO_ROUND = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
}


TEAM_HINTS = {
    "memphis": "MEM",
    "grizzlies": "MEM",
    "phoenix": "PHX",
    "suns": "PHX",
    "oklahoma city": "OKC",
    "thunder": "OKC",
    "golden state": "GSW",
    "warriors": "GSW",
    "indiana": "IND",
    "pacers": "IND",
    "denver": "DEN",
    "nuggets": "DEN",
    "houston": "HOU",
    "rockets": "HOU",
    "minnesota": "MIN",
    "timberwolves": "MIN",
    "cleveland": "CLE",
    "cavaliers": "CLE",
}


def normalize_bref_transaction_row(
    *,
    source_record_id: str,
    event_date: str,
    acquired_text: str,
    relinquished_text: str,
    note_text: str,
    team_scope: str = "memphis-grizzlies",
) -> PrototypeSourceEvent:
    acquired = parse_asset_text(acquired_text)
    relinquished = parse_asset_text(relinquished_text)
    event_type = infer_event_type(note_text=note_text, acquired_text=acquired_text, relinquished_text=relinquished_text)
    return PrototypeSourceEvent(
        source_system="basketball_reference",
        source_record_id=source_record_id,
        event_date=event_date,
        event_type=event_type,
        label=build_bref_label(event_type=event_type, acquired=acquired, relinquished=relinquished),
        team_scope=team_scope,
        source_group_hint=f"bref:{event_date}:{event_type}",
        participants_in=build_participants(acquired.players, acquired.pick_texts),
        participants_out=build_participants(relinquished.players, relinquished.pick_texts),
        pick_text_in=acquired.pick_texts,
        pick_text_out=relinquished.pick_texts,
        player_names_in=acquired.players,
        player_names_out=relinquished.players,
        raw_note=note_text or None,
        raw_payload={
            "event_date": event_date,
            "acquired_text": acquired_text,
            "relinquished_text": relinquished_text,
            "note_text": note_text,
            "unmatched_in": acquired.unmatched_chunks,
            "unmatched_out": relinquished.unmatched_chunks,
        },
    )


def normalize_common_all_players_row(row: dict[str, object]) -> PrototypePlayer:
    return PrototypePlayer(
        player_id=f"nba:{row['PERSON_ID']}",
        display_name=str(row["DISPLAY_FIRST_LAST"]),
        nba_player_ref=str(row["PERSON_ID"]),
    )


def normalize_common_team_roster_row(row: dict[str, object]) -> PrototypeRosterEntry:
    return PrototypeRosterEntry(
        season=str(row["SEASON"]),
        team_id=str(row["TeamID"]),
        player_id=f"nba:{row['PLAYER_ID']}",
        display_name=str(row["PLAYER"]),
        position_text=str(row["POSITION"]) if row.get("POSITION") else None,
        birth_date=str(row["BIRTH_DATE"]) if row.get("BIRTH_DATE") else None,
    )


def parse_pick_text(raw_text: str) -> ParsedPickText:
    text = collapse_whitespace(raw_text)
    lower = text.lower()

    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    round_match = re.search(r"\b(first|1st|second|2nd)(?:-round|-rd|\s+round)\b", lower)

    draft_year = int(year_match.group(0)) if year_match else None
    round_number = ORDINAL_TO_ROUND.get(round_match.group(1)) if round_match else None

    original_team = None
    via_match = re.search(r"\(via ([^)]+)\)", lower)
    if via_match:
        original_team = normalize_team_hint(via_match.group(1))
    elif "own" in lower or "memphis" in lower or "grizzlies" in lower:
        original_team = "MEM"

    protection_text = None
    protection_match = re.search(r"(top-\d+\s+protected)", lower)
    if protection_match:
        protection_text = protection_match.group(1)

    swap_text = None
    if "swap" in lower:
        swap_text = text
    else:
        favorability_match = re.search(r"(least favorable[^.;)]*|most favorable[^.;)]*|more favorable[^.;)]*)", lower)
        if favorability_match:
            swap_text = favorability_match.group(1)

    return ParsedPickText(
        raw_text=text,
        draft_year=draft_year,
        round_number=round_number,
        original_team=original_team,
        protection_text=protection_text,
        swap_text=swap_text,
    )


def parse_asset_text(raw_text: str) -> ParsedAssetText:
    if not raw_text or raw_text.strip() in {"—", "-", "None"}:
        return ParsedAssetText(players=[], pick_texts=[], unmatched_chunks=[])

    chunks = [collapse_whitespace(chunk) for chunk in split_chunks(raw_text)]
    players: list[str] = []
    pick_texts: list[str] = []
    unmatched_chunks: list[str] = []

    for chunk in chunks:
        if not chunk:
            continue
        if looks_like_pick(chunk):
            pick_texts.append(chunk)
            continue
        if looks_like_player_name(chunk):
            players.append(chunk)
            continue
        unmatched_chunks.append(chunk)

    return ParsedAssetText(players=players, pick_texts=pick_texts, unmatched_chunks=unmatched_chunks)


def infer_event_type(*, note_text: str, acquired_text: str, relinquished_text: str) -> SourceEventType:
    combined = collapse_whitespace(" ".join([note_text, acquired_text, relinquished_text])).lower()
    if "waiver" in combined or "waived" in combined:
        return "waiver"
    if "re-signed" in combined or "re signed" in combined:
        return "re_signing"
    if "extended" in combined or "extension" in combined:
        return "extension"
    if "converted" in combined or "conversion" in combined:
        return "conversion"
    if "released" in combined:
        return "release"
    if "draft" in combined:
        return "draft"
    if acquired_text and relinquished_text:
        return "trade"
    return "signing"


def build_bref_label(*, event_type: SourceEventType, acquired: ParsedAssetText, relinquished: ParsedAssetText) -> str:
    if event_type == "trade":
        return (
            f"Memphis acquired {summarize_assets(acquired)} "
            f"and relinquished {summarize_assets(relinquished)}"
        )
    if event_type == "waiver":
        return f"Memphis waived {summarize_assets(relinquished or acquired)}"
    if event_type == "signing":
        return f"Memphis signed {summarize_assets(acquired)}"
    if event_type == "draft":
        return f"Memphis draft event involving {summarize_assets(acquired if acquired.players or acquired.pick_texts else relinquished)}"
    return f"Memphis {event_type.replace('_', ' ')} event"


def summarize_assets(parsed: ParsedAssetText) -> str:
    assets = [*parsed.players, *parsed.pick_texts]
    return ", ".join(assets) if assets else "no tracked assets"


def build_participants(players: list[str], pick_texts: list[str]) -> list[str]:
    return [*[f"player_name:{player}" for player in players], *[f"pick_text:{text}" for text in pick_texts]]


def looks_like_pick(text: str) -> bool:
    lower = text.lower()
    return "pick" in lower or "round" in lower


def looks_like_player_name(text: str) -> bool:
    if "(" in text and ")" in text:
        return False
    return bool(re.match(r"^[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3}$", text))


def split_chunks(text: str) -> list[str]:
    normalized = text.replace(" and ", ", ")
    return re.split(r"\s*,\s*", normalized)


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_team_hint(text: str) -> str | None:
    lower = collapse_whitespace(text).lower()
    for hint, team_code in TEAM_HINTS.items():
        if hint in lower:
            return team_code
    return None
