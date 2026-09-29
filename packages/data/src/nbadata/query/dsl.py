"""
The query DSL (tasks 2.5, 2.7).

A typed object the model emits and deterministic code compiles. The model never
writes SQL, never picks a table, never writes a join.

Validation errors are written for a model to act on: they name what was wrong
*and* what was allowed, so a bounded retry has something to work with. A bare
"invalid field" tells the model nothing and burns a turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .catalog import ENTITIES, Entity, FieldType


class Op(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    CONTAINS = "contains"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"


class Agg(StrEnum):
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


NO_VALUE_OPS = {Op.IS_NULL, Op.NOT_NULL}
NUMERIC_ONLY_AGGS = {Agg.SUM, Agg.AVG}


class QueryError(ValueError):
    """Carries what was wrong and what would have been valid."""

    def __init__(self, message: str, *, allowed: list[str] | None = None) -> None:
        self.allowed = allowed or []
        if self.allowed:
            shown = ", ".join(sorted(self.allowed)[:40])
            message = f"{message}. Allowed: {shown}"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class Filter:
    field: str
    op: Op
    value: Any = None


@dataclass(frozen=True, slots=True)
class Projection:
    """A selected column, optionally aggregated."""

    field: str
    agg: Agg | None = None
    alias: str | None = None

    @property
    def output_name(self) -> str:
        if self.alias:
            return self.alias
        return f"{self.agg.value}_{self.field}" if self.agg else self.field


@dataclass(frozen=True, slots=True)
class Order:
    field: str
    descending: bool = False


@dataclass
class Query:
    entity: str
    select: list[Projection] = field(default_factory=list)
    filters: list[Filter] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    order_by: list[Order] = field(default_factory=list)
    limit: int = 100

    def validate(self) -> Entity:
        ent = ENTITIES.get(self.entity)
        if ent is None:
            raise QueryError(f"unknown entity {self.entity!r}", allowed=list(ENTITIES))
        if not self.select:
            raise QueryError(
                f"select must not be empty for entity {self.entity!r}", allowed=ent.field_names
            )
        if not 1 <= self.limit <= 1000:
            raise QueryError(f"limit must be between 1 and 1000, got {self.limit}")

        names = set(ent.field_names)
        for proj in self.select:
            if proj.field == "*" and proj.agg is Agg.COUNT:
                continue
            fld = ent.field(proj.field)
            if fld is None:
                raise QueryError(
                    f"unknown field {proj.field!r} on {self.entity!r}", allowed=sorted(names)
                )
            if proj.agg in NUMERIC_ONLY_AGGS and fld.type not in (
                FieldType.INTEGER,
                FieldType.REAL,
            ):
                raise QueryError(
                    f"{proj.agg.value} needs a numeric field; {proj.field!r} is {fld.type.value}",
                    allowed=[
                        f.name for f in ent.fields if f.type in (FieldType.INTEGER, FieldType.REAL)
                    ],
                )
        for flt in self.filters:
            if ent.field(flt.field) is None:
                raise QueryError(
                    f"unknown filter field {flt.field!r} on {self.entity!r}",
                    allowed=sorted(names),
                )
            if flt.op in NO_VALUE_OPS and flt.value is not None:
                raise QueryError(f"{flt.op.value} takes no value")
            if flt.op not in NO_VALUE_OPS and flt.value is None:
                raise QueryError(f"{flt.op.value} requires a value")
            if flt.op is Op.IN and not isinstance(flt.value, (list, tuple)):
                raise QueryError("'in' requires a list of values")
        for name in self.group_by:
            if ent.field(name) is None:
                raise QueryError(f"unknown group_by field {name!r}", allowed=sorted(names))
        for order in self.order_by:
            known_outputs = {p.output_name for p in self.select}
            if order.field not in names and order.field not in known_outputs:
                raise QueryError(
                    f"unknown order_by field {order.field!r}",
                    allowed=sorted(names | known_outputs),
                )

        # Aggregation without grouping collapses the result, which is rarely
        # what the question meant if bare columns were also selected.
        aggregated = [p for p in self.select if p.agg]
        bare = [p for p in self.select if not p.agg]
        if aggregated and bare and not self.group_by:
            raise QueryError(
                "mixing aggregated and non-aggregated fields requires group_by",
                allowed=[p.field for p in bare],
            )
        return ent
