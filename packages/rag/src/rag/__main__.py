"""
`python -m rag` -- build the retrieval artifact and report what went into it.

The index is a build artifact (ADR-004): produced here, shipped alongside the
code, opened read-only at runtime. Everything it needs is written in, so the
serving application never parses the PDF.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import index as ix
from .chunks import MAX_CHARS
from .chunks import build as build_chunks
from .crossrefs import build as build_graph
from .definitions import build as build_definitions
from .outline import DEFAULT_PDF, load

DEFAULT_OUT = Path("build") / "cba-index.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the CBA retrieval index.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--max-chars",
        type=int,
        default=MAX_CHARS,
        help="ceiling for one retrieval unit; settled by the 5.8 eval, not asserted",
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"no PDF at {args.pdf}")
        return 1

    outline = load(args.pdf)
    chunks = build_chunks(outline, max_chars=args.max_chars)
    definitions = build_definitions(outline)
    graph = build_graph(outline)
    ix.build(args.out, chunks, definitions, graph, outline)

    oversized = [c for c in chunks if c.oversized]
    print(f"{args.out}  {args.out.stat().st_size / 1e6:.1f}MB")
    print(f"  units        {len(outline.units):>6}  ({len(outline.unmatched)} unplaceable)")
    print(
        f"  chunks       {len(chunks):>6}  (ceiling {args.max_chars}, {len(oversized)} oversized)"
    )
    print(f"  definitions  {len(definitions.definitions):>6}  ({len(definitions.by_name)} names)")
    print(f"  references   {len(graph.references):>6}  ({len(graph.unresolved)} unresolved)")
    for chunk in oversized:
        print(f"    oversized: {chunk.label} ({chunk.char_count:,} chars, nothing to split on)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
