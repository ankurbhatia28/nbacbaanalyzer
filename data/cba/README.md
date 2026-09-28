# CBA source document

`nba-cba-2023.pdf` is not committed — it is a public document and the repo does
not redistribute it.

Place the 2023 NBA/NBPA Collective Bargaining Agreement here as
`nba-cba-2023.pdf`. The parser expects 676 pages, ~1.37M characters.

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
