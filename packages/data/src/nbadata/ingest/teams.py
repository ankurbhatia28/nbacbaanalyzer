"""Team key resolution. Basketball-Reference abbreviations are canonical."""

from __future__ import annotations

import re

# B-R spellings differ from the common ones in three places.
CANONICAL = {
    "BKN": "BRK",
    "CHA": "CHO",
    "PHX": "PHO",
    "NO": "NOP",
    "NY": "NYK",
    "GS": "GSW",
    "SA": "SAS",
    "UTAH": "UTA",
}


def canonical_team(code: str | None) -> str | None:
    if not code:
        return None
    up = code.strip().upper()
    return CANONICAL.get(up, up)


def from_slug(slug: str | None) -> str | None:
    """'milwaukee-bucks' or 'bucks' -> MIL, via the nickname."""
    if not slug:
        return None
    nickname = slug.strip().lower().replace("_", "-").split("-")[-1]
    return NICKNAME_TO_TRI.get(nickname)


def from_display(name: str | None) -> str | None:
    """'Milwaukee Bucks MIL' or 'Milwaukee Bucks' -> MIL."""
    if not name:
        return None
    tail = name.strip().split()[-1]
    if len(tail) == 3 and tail.isupper():
        return canonical_team(tail)
    words = re.sub(r"[^A-Za-z ]", " ", name).lower().split()
    for word in reversed(words):
        if word in NICKNAME_TO_TRI:
            return NICKNAME_TO_TRI[word]
    return None


NICKNAME_TO_TRI = {
    "hawks": "ATL",
    "celtics": "BOS",
    "nets": "BRK",
    "hornets": "CHO",
    "bulls": "CHI",
    "cavaliers": "CLE",
    "mavericks": "DAL",
    "nuggets": "DEN",
    "pistons": "DET",
    "warriors": "GSW",
    "rockets": "HOU",
    "pacers": "IND",
    "clippers": "LAC",
    "lakers": "LAL",
    "grizzlies": "MEM",
    "heat": "MIA",
    "bucks": "MIL",
    "timberwolves": "MIN",
    "pelicans": "NOP",
    "knicks": "NYK",
    "thunder": "OKC",
    "magic": "ORL",
    "76ers": "PHI",
    "sixers": "PHI",
    "suns": "PHO",
    "blazers": "POR",
    "trailblazers": "POR",
    "kings": "SAC",
    "spurs": "SAS",
    "raptors": "TOR",
    "jazz": "UTA",
    "wizards": "WAS",
}
