"""Compilation is deterministic and every literal is bound, never interpolated."""

from nbadata.query import Agg, Filter, Op, Order, Projection, Query, compile_query


def test_values_are_parameterised_not_inlined():
    sql, params = compile_query(
        Query(
            entity="cap_holds",
            select=[Projection("player")],
            filters=[Filter("team", Op.EQ, "MIL")],
        )
    )
    assert "MIL" not in sql
    assert params == ["MIL"]


def test_injection_attempt_is_bound_as_a_value():
    nasty = "MIL'; DROP TABLE players; --"
    sql, params = compile_query(
        Query(
            entity="cap_holds",
            select=[Projection("player")],
            filters=[Filter("team", Op.EQ, nasty)],
        )
    )
    assert "DROP TABLE" not in sql
    assert params == [nasty]


def test_in_expands_to_one_placeholder_per_value():
    sql, params = compile_query(
        Query(
            entity="cap_holds",
            select=[Projection("player")],
            filters=[Filter("bird_rights", Op.IN, ["Bird", "Early Bird"])],
        )
    )
    assert "IN (?, ?)" in sql
    assert params == ["Bird", "Early Bird"]


def test_contains_becomes_a_bound_like():
    sql, params = compile_query(
        Query(
            entity="draft_picks",
            select=[Projection("year")],
            filters=[Filter("protection_text", Op.CONTAINS, "swap")],
        )
    )
    assert "LIKE ?" in sql
    assert params == ["%swap%"]


def test_aggregates_and_grouping_render():
    sql, _ = compile_query(
        Query(
            entity="cap_holds",
            select=[Projection("team"), Projection("amount", Agg.SUM, "total")],
            group_by=["team"],
            order_by=[Order("total", True)],
            limit=5,
        )
    )
    assert 'SUM(h.amount) AS "total"' in sql
    assert "GROUP BY" in sql
    assert "LIMIT 5" in sql


def test_count_star_is_allowed():
    sql, _ = compile_query(Query(entity="cap_holds", select=[Projection("*", Agg.COUNT, "n")]))
    assert 'COUNT(*) AS "n"' in sql
