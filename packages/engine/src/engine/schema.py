"""
JSON Schema for the domain model (task 1.13).

One contract shared by the engine, the API, the web app and the eval fixtures,
and the basis for the agent's tool schemas in task 6.2. Emitted by walking the
dataclasses rather than maintained by hand, so it cannot drift from the types.

Maybe[T] is emitted as an explicit object with a `state` discriminator rather
than as a nullable value -- null would erase the distinction between "absent"
and "unknown", which is the distinction ADR-003 exists to preserve.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import types
import typing
from typing import Any

from . import (
    CapHold,
    Contract,
    ContractYear,
    DeadMoney,
    DraftPick,
    HardCapCeiling,
    Player,
    Protection,
    Season,
    Team,
    TeamState,
    TradeException,
    TradeRestriction,
)
from .maybe import Maybe

ROOT_TYPES = (
    Season,
    Team,
    Player,
    Contract,
    ContractYear,
    CapHold,
    DeadMoney,
    DraftPick,
    Protection,
    TradeException,
    TradeRestriction,
    HardCapCeiling,
    TeamState,
)

_PRIMITIVES: dict[Any, dict[str, Any]] = {
    int: {"type": "integer"},
    float: {"type": "number"},
    str: {"type": "string"},
    bool: {"type": "boolean"},
    datetime.date: {"type": "string", "format": "date"},
    type(None): {"type": "null"},
}


def _maybe_schema(inner: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "description": (
            "Tri-state value. 'absent' means the thing does not exist; 'unknown' "
            "means no source tells us. They are not interchangeable (ADR-003)."
        ),
        "properties": {
            "state": {"enum": ["known", "absent", "unknown"]},
            "value": {"anyOf": [inner, {"type": "null"}]},
        },
        "required": ["state"],
        "additionalProperties": False,
    }


def _schema_for(tp: Any, defs: dict[str, Any]) -> dict[str, Any]:
    if tp in _PRIMITIVES:
        return dict(_PRIMITIVES[tp])

    origin = typing.get_origin(tp)
    args = typing.get_args(tp)

    if origin is Maybe:
        return _maybe_schema(_schema_for(args[0], defs) if args else {})
    if origin in (types.UnionType, typing.Union):
        return {"anyOf": [_schema_for(a, defs) for a in args]}
    if origin in (list, tuple):
        if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": _schema_for(args[0], defs)}
        if origin is list:
            return {"type": "array", "items": _schema_for(args[0], defs) if args else {}}
        return {"type": "array"}
    if origin is dict:
        return {
            "type": "object",
            "additionalProperties": _schema_for(args[1], defs) if len(args) == 2 else {},
        }

    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        _register_enum(tp, defs)
        return {"$ref": f"#/$defs/{tp.__name__}"}
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        _register_dataclass(tp, defs)
        return {"$ref": f"#/$defs/{tp.__name__}"}
    return {}


def _register_enum(tp: type[enum.Enum], defs: dict[str, Any]) -> None:
    if tp.__name__ in defs:
        return
    defs[tp.__name__] = {"enum": [m.value for m in tp]}


def _register_dataclass(tp: Any, defs: dict[str, Any]) -> None:
    name: str = tp.__name__
    if name in defs:
        return
    defs[name] = {}  # reserve first, so self-references terminate
    hints = typing.get_type_hints(tp)
    props: dict[str, Any] = {}
    required: list[str] = []
    for f in dataclasses.fields(tp):
        props[f.name] = _schema_for(hints.get(f.name, Any), defs)
        has_default = (
            f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING
        )
        if not has_default:
            required.append(f.name)
    schema: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        schema["required"] = required
    if tp.__doc__:
        schema["description"] = " ".join(tp.__doc__.split())[:300]
    defs[name] = schema


def build_schema() -> dict[str, Any]:
    defs: dict[str, Any] = {}
    for tp in ROOT_TYPES:
        _register_dataclass(tp, defs)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/ankurbhatia28/nbacbaanalyzer/schema/domain.json",
        "title": "NBA CBA Analyzer domain model",
        "$defs": dict(sorted(defs.items())),
    }
