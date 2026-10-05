"""
`python -m rag.fetch` -- download the CBA PDF and prove it is the right one (D20).

The PDF is not committed: it is a public document and the repository does not
redistribute it. But the retrieval index is built from it, so without it the
index was not reproducible from source, which ADR-004 claimed it was. This
closes that gap by pinning the file instead of carrying it.

**The hash is the contract, not the URL.** Two official copies are tried in
order -- NBA.com's, then the NBPA's -- and both were checked on 2026-10-05 to
be byte-identical to the file every measurement in this repository was taken
against. A copy that downloads but does not match is rejected, not used: a
silently revised PDF would move page numbers and citations under every eval
without anything saying so. If both copies change, the build fails loudly and
the pin has to be re-examined by a person.

Standard library only, so it runs before `uv sync` if it has to.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

from .outline import DEFAULT_PDF

SHA256 = "bf178ca0f2d64f9dfe6fde095d3ae43d576b12e19ce7a679618d632584f7ab32"
SIZE = 2_850_534

SOURCES = (
    "https://ak-static.cms.nba.com/wp-content/uploads/sites/4/2023/06/"
    "2023-NBA-Collective-Bargaining-Agreement.pdf",
    "https://imgix.cosmicjs.com/25da5eb0-15eb-11ee-b5b3-fbd321202bdf-"
    "Final-2023-NBA-Collective-Bargaining-Agreement-6-28-23.pdf",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def matches(path: Path) -> bool:
    """Whether the file at `path` is the pinned PDF."""
    return path.is_file() and path.stat().st_size == SIZE and digest(path.read_bytes()) == SHA256


def fetch(out: Path = DEFAULT_PDF, sources: tuple[str, ...] = SOURCES, timeout: float = 60) -> str:
    """
    Make `out` the pinned PDF, downloading only if it is not already.

    Returns where it came from. Raises `RuntimeError` naming every source and
    why it was refused when none yields the pinned file.
    """
    if matches(out):
        return "already present"
    failures = []
    for url in sources:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "nbacba-build"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
        except OSError as exc:
            failures.append(f"{url}: {exc}")
            continue
        if digest(data) != SHA256:
            failures.append(f"{url}: {len(data):,} bytes, sha256 {digest(data)} -- not the pin")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        partial = out.with_suffix(".part")
        partial.write_bytes(data)
        partial.replace(out)
        return url
    raise RuntimeError("no source gave the pinned CBA PDF:\n  " + "\n  ".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and verify the CBA PDF (D20).")
    parser.add_argument("--out", type=Path, default=DEFAULT_PDF)
    args = parser.parse_args()
    try:
        source = fetch(args.out)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"{args.out}  sha256 {SHA256[:12]}…  ({source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
