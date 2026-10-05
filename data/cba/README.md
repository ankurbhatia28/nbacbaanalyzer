# CBA source document

`nba-cba-2023.pdf` is not committed — it is a public document and the repo does
not redistribute it. **Fetch it with `uv run python -m rag.fetch`**, which
downloads an official copy (NBA.com's, then the NBPA's) and keeps it only if its
sha256 matches the pin in `packages/rag/src/rag/fetch.py` (D20):

    bf178ca0f2d64f9dfe6fde095d3ae43d576b12e19ce7a679618d632584f7ab32  (2,850,534 bytes)

A copy that does not match is refused rather than used: a revised PDF would
move page numbers and citations under every eval. The parser expects 676 pages,
~1.37M characters.

## Extract with PyMuPDF, not pypdf

pypdf produces broken word boundaries throughout this document — `Generally Rec
ognized`, `Tea m`, `w hose`, `Sala ry`, `Contrac t`. PyMuPDF produces **zero**
occurrences of the same defects and runs ~5x faster. This is an extractor
artifact, not a property of the PDF, so no normalization pass is required.

## The document carries its own structure

`doc.get_toc()` returns a **2,412-entry bookmark outline**, 7 levels deep,
covering pages 1–671. It mirrors the legal hierarchy exactly:

| Level | Unit | Count |
|---|---|---|
| 1 | Article | 65 (42 are `Article N` headings) |
| 2 | Section | 288 |
| 3 | subsection | 938 |
| 4–7 | nested clauses | 1,121 |

So `Article VII, Section 8. Trade Rules` resolves to p. 284 without any
heuristic parsing. Chunk boundaries come from this tree, not from a character
count — see ADR-002's reasoning about verifiability applied to retrieval.
