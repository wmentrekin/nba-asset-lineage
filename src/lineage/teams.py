"""Static NBA team identity: person-movement feed team ids and names to tricodes."""

MEM = "MEM"

TEAM_ID_TO_TRICODE: dict[int, str] = {
    1610612737: "ATL",
    1610612738: "BOS",
    1610612739: "CLE",
    1610612740: "NOP",
    1610612741: "CHI",
    1610612742: "DAL",
    1610612743: "DEN",
    1610612744: "GSW",
    1610612745: "HOU",
    1610612746: "LAC",
    1610612747: "LAL",
    1610612748: "MIA",
    1610612749: "MIL",
    1610612750: "MIN",
    1610612751: "BKN",
    1610612752: "NYK",
    1610612753: "ORL",
    1610612754: "IND",
    1610612755: "PHI",
    1610612756: "PHX",
    1610612757: "POR",
    1610612758: "SAC",
    1610612759: "SAS",
    1610612760: "OKC",
    1610612761: "TOR",
    1610612762: "UTA",
    1610612763: "MEM",
    1610612764: "WAS",
    1610612765: "DET",
    1610612766: "CHA",
}

TEAM_NAME_TO_TRICODE: dict[str, str] = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "LA Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

TRICODES: frozenset[str] = frozenset(TEAM_ID_TO_TRICODE.values())

MEM_TEAM_ID = 1610612763


def tricode_for_id(team_id: int | float) -> str:
    """Return the tricode for an NBA feed TEAM_ID (feed numerics arrive as floats)."""
    key = int(team_id)
    try:
        return TEAM_ID_TO_TRICODE[key]
    except KeyError:
        raise ValueError(f"unknown NBA team id: {key}") from None


def tricode_for_name(full_name: str) -> str:
    """Return the tricode for a team's full name as it appears in feed descriptions."""
    try:
        return TEAM_NAME_TO_TRICODE[full_name]
    except KeyError:
        raise ValueError(f"unknown NBA team name: {full_name!r}") from None


def require_tricode(tricode: str) -> str:
    """Return `tricode` if it names a real team, else raise."""
    if tricode not in TRICODES:
        raise ValueError(f"unknown NBA team tricode: {tricode!r}")
    return tricode
