"""Validation must refuse clearly and tell the model what would have worked."""

import pytest

from nbadata.query import Agg, Filter, Op, Order, Projection, Query, QueryError


def q(**kw):
    kw.setdefault("entity", "cap_holds")
    kw.setdefault("select", [Projection("team")])
    return Query(**kw)


def test_unknown_entity_lists_the_valid_ones():
    with pytest.raises(QueryError) as e:
        q(entity="salaries").validate()
    assert "cap_holds" in str(e.value)


def test_unknown_field_lists_the_valid_ones():
    with pytest.raises(QueryError) as e:
        q(select=[Projection("payroll")]).validate()
    assert "bird_rights" in str(e.value)


def test_sum_of_a_text_field_is_refused_with_numeric_alternatives():
    with pytest.raises(QueryError) as e:
        q(select=[Projection("bird_rights", Agg.SUM)]).validate()
    assert "numeric" in str(e.value)
    assert "amount" in str(e.value)


def test_mixing_aggregates_and_bare_columns_needs_group_by():
    with pytest.raises(QueryError, match="group_by"):
        q(select=[Projection("team"), Projection("amount", Agg.SUM)]).validate()


def test_grouping_makes_that_mix_valid():
    q(select=[Projection("team"), Projection("amount", Agg.SUM)], group_by=["team"]).validate()


def test_in_requires_a_list():
    with pytest.raises(QueryError, match="list"):
        q(filters=[Filter("team", Op.IN, "MIL")]).validate()


def test_null_operators_take_no_value():
    with pytest.raises(QueryError, match="takes no value"):
        q(filters=[Filter("team", Op.IS_NULL, "x")]).validate()
    q(filters=[Filter("team", Op.IS_NULL)]).validate()


def test_limit_is_bounded():
    with pytest.raises(QueryError, match="between 1 and 1000"):
        q(limit=5000).validate()


def test_order_by_may_reference_an_output_alias():
    q(
        select=[Projection("team"), Projection("*", Agg.COUNT, "n")],
        group_by=["team"],
        order_by=[Order("n", True)],
    ).validate()


def test_empty_select_is_refused():
    with pytest.raises(QueryError, match="select must not be empty"):
        q(select=[]).validate()
