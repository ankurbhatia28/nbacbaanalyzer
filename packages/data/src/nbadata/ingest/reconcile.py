"""
Cross-source disagreement reporting (task 2.3).

Ingest must pick one value per field, but picking silently buries the conflict.
Every resolved disagreement is recorded with the losing values, so a wrong
precedence ranking shows up as a report line rather than as a quietly wrong
answer months later.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from .precedence import Src, winner


@dataclass
class Disagreement:
    field_name: str
    subject: str
    chosen_source: Src
    chosen_value: object
    others: dict[str, object]


@dataclass
class Reconciler:
    disagreements: list[Disagreement] = field(default_factory=list)
    agreements: int = 0

    def resolve[T](
        self, field_name: str, subject: str, candidates: dict[Src, T | None]
    ) -> T | None:
        """Pick the winning value, recording the conflict if sources differ."""
        present = {s: v for s, v in candidates.items() if v is not None and v != ""}
        if not present:
            return None
        src = winner(field_name, set(present))
        if src is None:
            src = next(iter(present))
        chosen = present[src]

        distinct = {repr(v) for v in present.values()}
        if len(distinct) > 1:
            self.disagreements.append(
                Disagreement(
                    field_name,
                    subject,
                    src,
                    chosen,
                    {s.value: v for s, v in present.items() if s is not src},
                )
            )
        else:
            self.agreements += 1
        return chosen

    def write(self, conn: sqlite3.Connection) -> None:
        conn.executemany(
            "INSERT INTO disagreements (field, subject, chosen, chosen_value, others) "
            "VALUES (?,?,?,?,?)",
            [
                (
                    d.field_name,
                    d.subject,
                    d.chosen_source.value,
                    str(d.chosen_value),
                    json.dumps({k: str(v) for k, v in d.others.items()}),
                )
                for d in self.disagreements
            ],
        )

    @property
    def summary(self) -> dict[str, int]:
        by_field: dict[str, int] = {}
        for d in self.disagreements:
            by_field[d.field_name] = by_field.get(d.field_name, 0) + 1
        return {"agreements": self.agreements, "disagreements": len(self.disagreements), **by_field}
