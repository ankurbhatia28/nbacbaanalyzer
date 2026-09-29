"""
Name normalisation and entity resolution across ID spaces.

The six sources use three incompatible keys: Basketball-Reference ids
(`jokicni01`), NBA.com numeric ids (`1630228`), and bare display names
(Spotrac, SalarySwish). Joining them means normalising names.

That is normally dangerous. Here it is measurably safe: across 654 Fanspo and
689 Basketball-Reference players, normalisation produces **537 matches and zero
collisions** -- no normalised name maps to more than one id on either side. The
residue is nickname variants, which an explicit alias table handles rather than
fuzzy matching, so every mapping stays auditable.
"""

from __future__ import annotations

import re
import unicodedata

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?", re.IGNORECASE)
_NOISE = re.compile(r"[^a-z ]")

# Nickname variants the sources disagree on. Deliberately explicit: a fuzzy
# matcher would silently pair the wrong players, and there are only a handful.
ALIASES: dict[str, str] = {
    "nicolas claxton": "nic claxton",
    "herb jones": "herbert jones",
    "nahshon hyland": "bones hyland",
    "cameron christie": "cam christie",
    "jeenathan williams": "nate williams",
    "cameron thomas": "cam thomas",
    "cameron johnson": "cam johnson",
    "cameron payne": "cam payne",
    "kentavious caldwell pope": "kentavious caldwellpope",
    # Family-name-first rendering in one source, given-name-first in another.
    "hansen yang": "yang hansen",
    # Formal given name vs the name the player is listed under.
    "sviatoslav mykhailiuk": "svi mykhailiuk",
}


def normalise(name: str | None) -> str:
    """Casefold, strip accents, drop generational suffixes and punctuation."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = text.replace("'", "").replace(".", "")
    text = _SUFFIX.sub(" ", text)
    text = _NOISE.sub(" ", text.lower())
    canonical = " ".join(text.split())
    return ALIASES.get(canonical, canonical)
