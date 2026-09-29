"""
DSL -> SQL (task 2.6).

Deterministic, and every literal is a bound parameter. Identifiers never come
from the request: they are looked up in the catalog, so a field name the model
invents fails validation rather than reaching SQLite.
"""

from __future__ import annotations

from .catalog import Entity
from .dsl import Agg, Op, Query

_COMPARISON = {
    Op.EQ: "=",
    Op.NE: "!=",
    Op.GT: ">",
    Op.GTE: ">=",
    Op.LT: "<",
    Op.LTE: "<=",
}

_AGG_SQL = {
    Agg.COUNT: "COUNT({})",
    Agg.COUNT_DISTINCT: "COUNT(DISTINCT {})",
    Agg.SUM: "SUM({})",
    Agg.AVG: "AVG({})",
    Agg.MIN: "MIN({})",
    Agg.MAX: "MAX({})",
}


def compile_query(query: Query) -> tuple[str, list[object]]:
    entity: Entity = query.validate()
    params: list[object] = []

    select_parts = []
    for proj in query.select:
        if proj.field == "*" and proj.agg is Agg.COUNT:
            expr = "COUNT(*)"
        else:
            column = entity.field(proj.field)
            assert column is not None  # validate() guarantees this
            expr = _AGG_SQL[proj.agg].format(column.sql) if proj.agg else column.sql
        select_parts.append(f'{expr} AS "{proj.output_name}"')

    where_parts = []
    for flt in query.filters:
        column = entity.field(flt.field)
        assert column is not None
        if flt.op is Op.IS_NULL:
            where_parts.append(f"{column.sql} IS NULL")
        elif flt.op is Op.NOT_NULL:
            where_parts.append(f"{column.sql} IS NOT NULL")
        elif flt.op is Op.IN:
            values = list(flt.value)
            where_parts.append(f"{column.sql} IN ({', '.join('?' * len(values))})")
            params.extend(values)
        elif flt.op is Op.CONTAINS:
            where_parts.append(f"{column.sql} LIKE ?")
            params.append(f"%{flt.value}%")
        else:
            where_parts.append(f"{column.sql} {_COMPARISON[flt.op]} ?")
            params.append(flt.value)

    sql = f"SELECT {', '.join(select_parts)}\nFROM {entity.source_sql.strip()}"
    if where_parts:
        sql += "\nWHERE " + " AND ".join(where_parts)
    if query.group_by:
        columns = []
        for name in query.group_by:
            column = entity.field(name)
            assert column is not None
            columns.append(column.sql)
        sql += "\nGROUP BY " + ", ".join(columns)
    if query.order_by:
        ordered = []
        for order in query.order_by:
            column = entity.field(order.field)
            expr = column.sql if column else f'"{order.field}"'
            ordered.append(f"{expr} {'DESC' if order.descending else 'ASC'}")
        sql += "\nORDER BY " + ", ".join(ordered)
    sql += f"\nLIMIT {int(query.limit)}"
    return sql, params
