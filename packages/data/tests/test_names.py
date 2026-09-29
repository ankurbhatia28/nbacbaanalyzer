"""Name normalisation is the cross-source join key, so it has to be predictable."""

import pytest

from nbadata.ingest.names import normalise


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Nikola Jokić", "nikola jokic"),  # accents stripped
        ("Jaren Jackson Jr.", "jaren jackson"),  # generational suffix dropped
        ("C.J. McCollum", "cj mccollum"),  # punctuation removed
        ("  Trae   Young ", "trae young"),  # whitespace collapsed
        ("Nicolas Claxton", "nic claxton"),  # alias applied
        ("Hansen Yang", "yang hansen"),  # name order differs by source
        ("", ""),
    ],
)
def test_normalise(raw, expected):
    assert normalise(raw) == expected


def test_normalise_handles_none():
    assert normalise(None) == ""


def test_aliases_are_idempotent():
    once = normalise("Nicolas Claxton")
    assert normalise(once) == once
