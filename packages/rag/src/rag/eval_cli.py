"""
`python -m rag.eval_cli` -- score retrieval against the golden questions (5.8).

Reports the aggregate, the split by how a question is phrased (which is where
the finding is), and optionally the chunk-ceiling sweep.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import index as ix
from .chunks import MAX_CHARS
from .chunks import build as build_chunks
from .crossrefs import build as build_graph
from .definitions import build as build_definitions
from .evals import Kind, all_questions, render_sweep, score, sweep
from .outline import DEFAULT_PDF, load


def main() -> int:
    parser = argparse.ArgumentParser(description="Score CBA retrieval.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS)
    parser.add_argument("--sweep", action="store_true", help="also sweep the chunk ceiling")
    parser.add_argument(
        "--min-recall",
        type=float,
        default=0.0,
        help="fail if recall@10 falls below this, for use as a regression gate",
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"no PDF at {args.pdf}")
        return 1

    outline = load(args.pdf)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "eval.db"
        ix.build(
            path,
            build_chunks(outline, max_chars=args.max_chars),
            build_definitions(outline),
            build_graph(outline),
            outline,
        )
        conn = ix.open_index(path)
        report = score(conn, all_questions(conn))
        report.max_chars = args.max_chars
        print(report.render())

        if args.sweep:
            print("\nchunk ceiling sweep:")
            print(render_sweep(sweep(outline)))

    print(
        "\nReading this honestly: BM25 does reasonably when the query carries the term of "
        f"art ({report.subset(Kind.TERM).recall_at(3):.0%} recall@3) and poorly when it does "
        f"not ({report.subset(Kind.PARAPHRASE).recall_at(3):.0%}). The bottleneck is "
        "vocabulary, not ranking -- see 5.8 in the build plan."
    )

    if report.recall_at(10) < args.min_recall:
        print(f"\nrecall@10 {report.recall_at(10):.1%} is below the {args.min_recall:.1%} gate")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
