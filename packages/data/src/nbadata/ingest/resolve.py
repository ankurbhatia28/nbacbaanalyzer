"""
One identity per player, assembled from whichever sources mention them.

Unresolved names are collected rather than dropped. A player who silently
vanishes during ingest is a data bug that surfaces much later as a wrong
answer; an explicit unresolved list is a bug that surfaces now.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .names import normalise


@dataclass
class PlayerIdentity:
    key: str  # normalised name -- the join key across sources
    display_name: str
    bbref_id: str | None = None
    nba_id: str | None = None
    seen_in: set[str] = field(default_factory=set)

    @property
    def preferred_id(self) -> str:
        """bbref id where we have one: it is stable and human-readable."""
        return self.bbref_id or self.nba_id or self.key


@dataclass
class ResolutionReport:
    identities: dict[str, PlayerIdentity] = field(default_factory=dict)
    unresolved: dict[str, set[str]] = field(default_factory=dict)  # name -> sources

    def observe(
        self,
        name: str,
        source: str,
        *,
        bbref_id: str | None = None,
        nba_id: str | None = None,
    ) -> PlayerIdentity | None:
        key = normalise(name)
        if not key:
            return None
        identity = self.identities.get(key)
        if identity is None:
            identity = PlayerIdentity(key=key, display_name=name)
            self.identities[key] = identity
        if bbref_id and not identity.bbref_id:
            identity.bbref_id = bbref_id
        if nba_id and not identity.nba_id:
            identity.nba_id = nba_id
        identity.seen_in.add(source)
        return identity

    def mark_unresolved(self, name: str, source: str) -> None:
        self.unresolved.setdefault(normalise(name) or name, set()).add(source)

    def finalise(self) -> None:
        """Anything seen only under a display name and never keyed is unresolved."""
        for key, identity in self.identities.items():
            if identity.bbref_id is None and identity.nba_id is None:
                self.unresolved.setdefault(key, set()).update(identity.seen_in)

    @property
    def summary(self) -> dict[str, int]:
        both = sum(1 for i in self.identities.values() if i.bbref_id and i.nba_id)
        return {
            "identities": len(self.identities),
            "with_bbref_id": sum(1 for i in self.identities.values() if i.bbref_id),
            "with_nba_id": sum(1 for i in self.identities.values() if i.nba_id),
            "cross_linked": both,
            "unresolved": len(self.unresolved),
        }
