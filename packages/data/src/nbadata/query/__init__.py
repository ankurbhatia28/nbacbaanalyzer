"""
Structured query layer (ADR-002).

The model emits a typed `Query`; deterministic code validates it against a
fixed catalog and compiles it to parameterised SQL. Anything the catalog cannot
express is refused with the catalog attached, so the refusal is actionable and
each one is a candidate for extending the DSL (task 2.10).
"""

from .catalog import ENTITIES, Entity, Field, FieldType, describe_catalog
from .compile import compile_query
from .dsl import Agg, Filter, Op, Order, Projection, Query, QueryError
from .lookup import PlayerMatch, lookup_player
from .run import QueryResult, run

__all__ = [
    "ENTITIES",
    "Agg",
    "Entity",
    "Field",
    "FieldType",
    "Filter",
    "Op",
    "Order",
    "PlayerMatch",
    "Projection",
    "Query",
    "QueryError",
    "QueryResult",
    "compile_query",
    "describe_catalog",
    "lookup_player",
    "run",
]
