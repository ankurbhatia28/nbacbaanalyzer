"""
The definitions index (task 5.4).

Article I fixes the meaning of terms used everywhere else, so a passage read
without them supports a confident wrong answer — the failure this whole project
is arranged against.
"""

import pytest

from rag.chunks import build as build_chunks
from rag.definitions import UBIQUITOUS, build, definition_sections
from rag.outline import DEFAULT_PDF, load

pytestmark = pytest.mark.skipif(not DEFAULT_PDF.exists(), reason="CBA PDF not present")


@pytest.fixture(scope="module")
def outline():
    return load()


@pytest.fixture(scope="module")
def index(outline):
    return build(outline)


def test_definitions_are_found_outside_the_definitions_sections(outline, index):
    """
    Three Sections are titled "Definitions", but terms are also defined where
    they are needed -- "Force Majeure Event" at Art. XXXIX §5(a). Scanning only
    the titled Sections would miss those.
    """
    titled = {u.citation for u in definition_sections(outline)}
    assert titled == {"Art. I §1", "Art. VII §1", "Art. XXXIII §1"}
    force_majeure = index.by_name["Force Majeure Event"]
    assert force_majeure.citation == "Art. XXXIX §5(a)"
    assert force_majeure.citation.split("§")[0] not in titled


def test_the_index_covers_the_terms_phase_three_depends_on(index):
    """Every term the engine reasons about has to be explainable."""
    for term, citation in [
        ("Apron Team Salary", "Art. VII §2(e)(1)"),
        ("Traded Player", "Art. I §1(xxx)"),
        ("Replacement Player", "Art. I §1(ccc)"),
        ("Years of Service", "Art. I §1(iiii)"),
    ]:
        assert index.by_name[term].citation == citation


@pytest.mark.parametrize(
    ("name", "resolves_to"),
    [
        ("ETO", "Early Termination Option"),  # a parenthetical alias
        ("Early Termination Option", "Early Termination Option"),
        ("Contract", "Uniform Player Contract"),  # a (see "X") pointer
        ("Player Contract", "Uniform Player Contract"),
        ("Team", "Member"),
        ("final Audit Report", "Audit Report"),  # an "or" alias
    ],
)
def test_aliases_and_pointers_reach_the_real_definition(index, name, resolves_to):
    """
    Four shapes, all of which the first version of the parser missed: an "or"
    alias, a parenthetical "(or "ETO")", a bare cross-reference "(see "X")",
    and a comma-separated list of variants.
    """
    assert index.by_name[name].term == resolves_to


def test_the_awkwardly_worded_definitions_are_still_found(index):
    """
    Art. I §1(nn) opens "The term "negotiate" means", and §1(bbb) lists
    ""Renegotiation," "renegotiate," or "renegotiated" means" with the commas
    inside the quotes. Both broke the first parser.
    """
    assert index.by_name["negotiate"].citation == "Art. I §1(nn)"
    assert index.by_name["Renegotiation"].citation == "Art. I §1(bbb)"


def test_matching_is_case_sensitive(index):
    """
    The document's convention: a term is Capitalised where it carries its
    defined meaning. "the player" is not "the Player", and conflating them
    would attach a definition to every ordinary use of the word.
    """
    assert "Traded Player" in index.terms_in("acquired as a Traded Player")
    assert "Traded Player" not in index.terms_in("acquired as a traded player")


def test_a_term_nested_inside_a_longer_one_is_not_reported_twice(index):
    """
    "Apron Team Salary" contains "Team Salary", which is separately defined.
    Reporting both would label the passage with a term it does not use. A
    genuinely separate later occurrence is a different matter and still counts.
    """
    found = index.terms_in("the Apron Team Salary for such Salary Cap Year")
    assert "Apron Team Salary" in found
    assert "Team Salary" not in found
    assert "Team Salary" in index.terms_in("the Apron Team Salary exceeds its Team Salary")


def test_specificity_ranking_happens_in_relevant_to(index):
    """`terms_in` reports document order; the ranking is `relevant_to`'s job."""
    text = "the Team's Apron Team Salary for such Salary Cap Year"
    assert index.terms_in(text)[0] == "Team"
    assert index.relevant_to(text)[0].term == "Apron Team Salary"


def test_ubiquitous_terms_are_all_real_defined_names(index):
    """
    The suppression list must describe the document. An earlier version listed
    "Player" and "NBA", neither of which the CBA defines, so it claimed to
    filter terms it had never seen.
    """
    assert {name for name in UBIQUITOUS if name not in index.by_name} == set()


def test_ubiquitous_terms_are_not_attached_to_a_passage(index):
    """
    They match constantly and explain nothing, and every slot they take is one
    the term the passage actually turns on does not get.
    """
    attached = index.relevant_to("the Team and the Player under this Agreement")
    assert all(d.term not in UBIQUITOUS for d in attached)


def test_the_apron_passage_is_given_the_apron_definition(outline, index):
    """The test of whether any of this is useful."""
    chunk = next(c for c in build_chunks(outline) if c.citation == "Art. VII §2(e)(2)(i)")
    terms = [d.term for d in index.relevant_to(chunk.text)]
    assert "Apron Team Salary" in terms
    assert terms[0] == "Apron Team Salary", "the most specific term should lead"


def test_attachment_is_capped(index):
    long_text = "Apron Team Salary Traded Player Replacement Player Years of Service " * 5
    assert len(index.relevant_to(long_text, limit=2)) == 2
