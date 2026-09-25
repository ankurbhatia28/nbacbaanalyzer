# CBA source document

`nba-cba-2023.pdf` is not committed — it is a public document and the repo does
not redistribute it.

Place the 2023 NBA/NBPA Collective Bargaining Agreement here as
`nba-cba-2023.pdf`. The parser in `packages/rag` expects 676 pages.

Note for the parser: this PDF's text layer has broken word boundaries
throughout — it yields `Generally Rec ognized`, `Tea m`, `w hose`. Normalization
is required before indexing or BM25 will miss a large share of query terms.
