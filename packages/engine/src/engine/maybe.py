"""
Tri-state values: known, absent, or unknown.

ADR-003. Three contract fields are not reliably available from any source:
trade kickers, no-trade clauses, and cash in trades. Defaulting them to zero or
False makes the engine quietly wrong -- a trade that is illegal because of a 15%
trade kicker would validate clean, with nothing indicating a guess was made.

`Maybe` makes that impossible to do by accident. It is deliberately not falsy:
`if contract.trade_kicker:` raises rather than silently treating unknown as no.
Reading a value out requires either proving it is known (`require`) or recording
an assumption (`assume`), and assumptions travel with the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class State(StrEnum):
    KNOWN = "known"
    ABSENT = "absent"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Assumption:
    """A guess the engine had to make, surfaced alongside any verdict."""

    field_name: str
    subject: str
    assumed: object
    reason: str

    def describe(self) -> str:
        return f"assuming {self.field_name} of {self.subject} is {self.assumed!r} ({self.reason})"


class UnknownValueError(Exception):
    """Raised when an unknown value is read without an explicit assumption."""


@dataclass(frozen=True, slots=True)
class Maybe[T]:
    state: State
    value: T | None = None

    # -- constructors ----------------------------------------------------
    @staticmethod
    def known(value: T) -> Maybe[T]:
        return Maybe(State.KNOWN, value)

    @staticmethod
    def absent() -> Maybe[T]:
        """The thing genuinely does not exist -- e.g. this contract has no kicker."""
        return Maybe(State.ABSENT, None)

    @staticmethod
    def unknown() -> Maybe[T]:
        """No source tells us. Not the same as absent."""
        return Maybe(State.UNKNOWN, None)

    # -- predicates ------------------------------------------------------
    @property
    def is_known(self) -> bool:
        return self.state is State.KNOWN

    @property
    def is_absent(self) -> bool:
        return self.state is State.ABSENT

    @property
    def is_unknown(self) -> bool:
        return self.state is State.UNKNOWN

    def __bool__(self) -> bool:
        raise TypeError(
            "Maybe has no truth value -- an unknown would read as False and silently "
            "become a wrong answer. Use .is_known / .is_absent / .is_unknown, or "
            ".require() / .assume()."
        )

    # -- reading ---------------------------------------------------------
    def require(self, subject: str = "value") -> T:
        """Read a known value. Raises on absent or unknown."""
        if self.state is not State.KNOWN:
            raise UnknownValueError(f"{subject} is {self.state.value}, not known")
        return self.value  # type: ignore[return-value]

    def or_absent(self, empty: T, subject: str = "value") -> T:
        """Read, treating a genuine absence as `empty`. Still raises on unknown."""
        if self.state is State.ABSENT:
            return empty
        return self.require(subject)

    def assume(
        self, default: T, subject: str, field_name: str, reason: str
    ) -> tuple[T, Assumption | None]:
        """
        Read a value, falling back to `default` when unknown and returning the
        Assumption that fallback creates. Callers must propagate it.
        """
        if self.state is State.KNOWN:
            return self.value, None  # type: ignore[return-value]
        if self.state is State.ABSENT:
            return default, None
        return default, Assumption(field_name, subject, default, reason)

    def __repr__(self) -> str:
        if self.state is State.KNOWN:
            return f"Known({self.value!r})"
        return str(self.state.value).capitalize() + "()"


@dataclass
class AssumptionLog:
    """Collects assumptions made while computing a verdict."""

    entries: list[Assumption] = field(default_factory=list)

    def add(self, assumption: Assumption | None) -> None:
        if assumption is not None:
            self.entries.append(assumption)

    def read[T](self, m: Maybe[T], default: T, subject: str, field_name: str, reason: str) -> T:
        value, assumption = m.assume(default, subject, field_name, reason)
        self.add(assumption)
        return value

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def is_empty(self) -> bool:
        return not self.entries
