"""
The cross-reference graph (task 5.5).

The document is a network. Art. VII §6(j)(1)(i) opens "Subject to the rules set
forth in Section 2(e) above", and §2(e) holds the apron restrictions — so
retrieving the exception without the reference hands back a permission without
its precondition.
"""

import pytest

from rag.crossrefs import _EXTERNAL, _REFERENCE, build, references_in
from rag.outline import DEFAULT_PDF, load

pytestmark = pytest.mark.skipif(not DEFAULT_PDF.exists(), reason="CBA PDF not present")


@pytest.fixture(scope="module")
def outline():
    return load()


@pytest.fixture(scope="module")
def graph(outline):
    return build(outline)


def test_the_precondition_on_the_standard_tpe_is_an_edge(graph):
    """The reference the whole task exists for."""
    assert "Art. VII §2(e)" in graph.out["Art. VII §6(j)(1)(i)"]


def test_the_graph_is_substantial_and_mostly_resolves(graph):
    """
    1,217 edges resolve and 20 do not — about 1.6%. The remainder are kept for
    inspection: they are a measure of the parser, not noise to discard.
    """
    assert len(graph.references) > 1_000
    assert len(graph.unresolved) < 0.03 * len(graph.references)


def test_a_bare_section_reference_resolves_within_its_own_article(outline, graph):
    """
    "Section 6(j)" means Section 6(j) *of the Article it appears in*. The same
    string in two Articles points at two different provisions, which is why
    references are read per unit.
    """
    unit = outline.by_citation["Art. VII §6(e)"]
    found = references_in(outline, unit, "as provided in Section 2(e) above")
    assert [r.target for r in found] == ["Art. VII §2(e)"]
    assert found[0].explicit_article is False

    other = outline.by_citation["Art. XI §5"]
    found = references_in(outline, other, "as provided in Section 2(e) above")
    assert found == [] or not found[0].target.startswith("Art. VII")


def test_a_named_article_is_not_overridden_by_context(outline):
    unit = outline.by_citation["Art. XI §5"]
    found = references_in(outline, unit, "pursuant to Article VII, Section 6(j)")
    assert [r.target for r in found] == ["Art. VII §6(j)"]
    assert found[0].explicit_article is True


@pytest.mark.parametrize(
    "text",
    [
        "qualified under Section 401(a) of the Code",
        "Section 415(d)(2) of the Code",
        "Section 302(c)(5) of the Labor Management Relations Act of 1947",
    ],
)
def test_statutory_references_are_not_read_as_internal_ones(outline, text):
    """
    Article IV cites the Internal Revenue Code constantly. Read as internal
    references they produced 33 edges to provisions that do not exist — which
    is how they were found, since every one failed to resolve.
    """
    unit = outline.by_citation["Art. IV §1"]
    assert references_in(outline, unit, text) == []
    match = _REFERENCE.search(text)
    assert _EXTERNAL.match(text, match.end())


def test_a_provision_citing_itself_is_not_an_edge(outline):
    """A self-edge tells retrieval nothing."""
    unit = outline.by_citation["Art. VII §6(j)"]
    found = references_in(outline, unit, "for purposes of this Section 6(j)")
    assert found == []


def test_one_hop_expansion_keeps_the_seeds_first(graph):
    """
    The caller has to be able to tell a seed from an expansion, so order is
    preserved rather than the result being a set.
    """
    seeds = ["Art. VII §6(j)(1)(i)"]
    expanded = graph.expand(seeds, hops=1)
    assert expanded[0] == seeds[0]
    assert "Art. VII §2(e)" in expanded[1:]


def test_zero_hops_returns_only_the_seeds(graph):
    assert graph.expand(["Art. VII §6(j)"], hops=0) == ["Art. VII §6(j)"]


def test_expansion_does_not_revisit_or_duplicate(graph):
    expanded = graph.expand(["Art. VII §6(j)(1)(i)", "Art. VII §6(j)(1)(i)"], hops=2)
    assert len(expanded) == len(set(expanded))


def test_two_hops_reaches_further_than_one(graph):
    one = graph.expand(["Art. VII §6(j)(1)(i)"], hops=1)
    two = graph.expand(["Art. VII §6(j)(1)(i)"], hops=2)
    assert set(one) <= set(two)
    assert len(two) > len(one)


def test_the_graph_answers_who_relies_on_a_provision(graph):
    """
    The reverse direction: a restriction is often best explained by what
    depends on it. The exceptions in §6 all point back at §2(e).
    """
    callers = graph.cited_by("Art. VII §2(e)")
    assert len(callers) > 3
    assert any(c.startswith("Art. VII §6") for c in callers)


def test_an_unresolved_reference_is_kept_rather_than_edged(graph):
    """
    An edge to a provision that does not exist would send retrieval after
    nothing; discarding the reference would hide that the parser and the
    outline disagreed.
    """
    assert graph.unresolved
    for reference in graph.unresolved:
        assert reference.resolved is False
        assert reference.target not in graph.out.get(reference.source, set())
