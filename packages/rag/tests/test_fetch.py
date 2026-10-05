"""
The CBA PDF is pinned by hash, not trusted by URL (D20).

No network: sources are file:// URLs to bytes written here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rag import fetch


def _source(tmp_path: Path, name: str, data: bytes) -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return path.as_uri()


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch) -> bytes:
    """Re-pin to known bytes, so the real 2.8 MB file is not needed."""
    data = b"%PDF the agreement"
    monkeypatch.setattr(fetch, "SHA256", fetch.digest(data))
    monkeypatch.setattr(fetch, "SIZE", len(data))
    return data


def test_a_copy_that_does_not_match_is_refused_and_the_next_one_used(
    tmp_path: Path, pinned: bytes
) -> None:
    revised = _source(tmp_path, "revised.pdf", b"%PDF a silently revised agreement")
    good = _source(tmp_path, "good.pdf", pinned)
    out = tmp_path / "cba" / "out.pdf"

    assert fetch.fetch(out, (revised, good)) == good
    assert out.read_bytes() == pinned


def test_no_matching_copy_fails_loudly_and_writes_nothing(tmp_path: Path, pinned: bytes) -> None:
    revised = _source(tmp_path, "revised.pdf", b"%PDF a silently revised agreement")
    out = tmp_path / "out.pdf"

    with pytest.raises(RuntimeError, match="not the pin"):
        fetch.fetch(out, (revised, (tmp_path / "missing.pdf").as_uri()))
    assert not out.exists()


def test_a_file_already_pinned_is_not_downloaded_again(tmp_path: Path, pinned: bytes) -> None:
    out = tmp_path / "out.pdf"
    out.write_bytes(pinned)
    assert fetch.fetch(out, ()) == "already present"
