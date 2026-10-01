"""
BM25 retrieval over SQLite FTS5 (task 5.6, decision D12).

BM25 first, and no model at inference. Legal text is dense with exact terms of
art -- "Apron Team Salary", "Expanded Traded Player Exception" -- and a question
about one of them contains the term verbatim, which is the case lexical search
wins. Embeddings are added only if 5.8 measures a gain that justifies the
cold-start and the bundle size, per D12: settled by measurement, not assertion.

The index is a **build artifact** (ADR-004). It is written once by `build` and
opened read-only by the serving application, which never writes to it.

One trap worth naming. FTS5's query syntax treats parentheses as grouping, so
the perfectly reasonable question "what does 6(j) say" is not a query that
returns nothing -- it is a *syntax error*. Every query therefore goes through
`escape_query`, which strips the operators and quotes each term. Passing user
text to MATCH unescaped is the same class of mistake as string-building SQL.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .chunks import Chunk
from .crossrefs import Graph
from .definitions import DefinitionIndex
from .outline import Outline

SCHEMA = """
CREATE TABLE chunks (
    id            INTEGER PRIMARY KEY,
    citation      TEXT NOT NULL,
    heading_path  TEXT NOT NULL,
    body          TEXT NOT NULL,
    indexed_text  TEXT NOT NULL,
    pdf_page      INTEGER NOT NULL,
    printed_page  INTEGER NOT NULL,
    last_pdf_page INTEGER NOT NULL,
    level         INTEGER NOT NULL,
    span_start    INTEGER NOT NULL DEFAULT 0,
    span_end      INTEGER NOT NULL DEFAULT 0,
    ordinal       INTEGER NOT NULL DEFAULT 1,
    oversized     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_chunks_citation ON chunks(citation);

-- External-content FTS5: the index points at `chunks` rather than holding a
-- second copy of 1.2MB of text.
-- Definitions and cross-references are written into the artifact too. The
-- serving application must not re-parse a 676-page PDF at startup, and
-- ADR-004 makes this file the whole of what gets shipped.
-- Which chunk holds each citable provision, computed by text containment at
-- build time. String-prefix fallback is not good enough: §2(e)(2)(ii) shares a
-- prefix with §2(e), whose own chunk is a 30-character heading, so a prefix
-- walk "succeeds" while returning nothing worth quoting.
CREATE TABLE citation_map (
    citation   TEXT PRIMARY KEY,
    chunk_id   INTEGER NOT NULL REFERENCES chunks(id),
    exact      INTEGER NOT NULL,
    unit_start INTEGER NOT NULL,
    unit_end   INTEGER NOT NULL
);

CREATE TABLE definitions (
    term     TEXT PRIMARY KEY,
    citation TEXT NOT NULL,
    body     TEXT NOT NULL,
    pdf_page INTEGER NOT NULL
);

CREATE TABLE definition_names (
    name TEXT PRIMARY KEY,
    term TEXT NOT NULL REFERENCES definitions(term)
);

CREATE TABLE crossrefs (
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    PRIMARY KEY (source, target)
);

CREATE INDEX idx_crossrefs_target ON crossrefs(target);

CREATE VIRTUAL TABLE chunk_fts USING fts5(
    indexed_text,
    content='chunks',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
"""

_TOKEN = re.compile(r"[\w$][\w$'.,-]*")
_STOP = frozenset({"the", "a", "an", "of", "and", "or", "to", "in", "is", "for", "what", "does"})


@dataclass(frozen=True, slots=True)
class Hit:
    """One retrieved passage and what it scored."""

    citation: str
    heading_path: str
    body: str
    pdf_page: int
    printed_page: int
    score: float
    ordinal: int = 1
    """BM25. SQLite returns it negated, so **lower is a better match**."""

    @property
    def label(self) -> str:
        """The citation as shown to a reader, disambiguated where it repeats."""
        return self.citation if self.ordinal == 1 else f"{self.citation} (passage {self.ordinal})"

    @property
    def rank(self) -> float:
        """Positive and increasing with relevance, for anyone who expects that."""
        return -self.score


def escape_query(text: str) -> str:
    """
    Turn arbitrary text into a safe FTS5 MATCH expression.

    Parentheses, quotes, `*`, `NEAR`, `AND`/`OR`/`NOT` are all operators. A
    question like "what does 6(j) say" raises a syntax error rather than
    returning nothing, so operators are stripped rather than escaped and every
    remaining term is quoted as a literal.

    Stop words are dropped only when something else survives: a query that is
    nothing but stop words should still run, even if it matches poorly.
    """
    tokens = [match.group(0).strip(".,'-") for match in _TOKEN.finditer(text)]
    tokens = [token for token in tokens if token]
    if not tokens:
        return '""'
    meaningful = [token for token in tokens if token.lower() not in _STOP]
    chosen = meaningful or tokens
    return " OR ".join(f'"{token}"' for token in chosen)


def build(
    path: Path | str,
    chunks: list[Chunk],
    definitions: DefinitionIndex | None = None,
    graph: Graph | None = None,
    outline: Outline | None = None,
) -> sqlite3.Connection:
    """
    Write the index. An existing file is replaced -- indexing is a rebuild.

    The FTS table is populated from `chunks` in one statement rather than row
    by row, which is both faster and the documented way to fill an
    external-content index.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO chunks (citation, heading_path, body, indexed_text, pdf_page, "
        "printed_page, last_pdf_page, level, span_start, span_end, ordinal, oversized) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                chunk.citation,
                chunk.heading_path,
                chunk.text,
                chunk.indexed_text,
                chunk.pdf_page,
                chunk.printed_page,
                chunk.last_pdf_page,
                chunk.level,
                chunk.start,
                chunk.end,
                chunk.ordinal,
                int(chunk.oversized),
            )
            for chunk in chunks
        ],
    )
    if outline is not None:
        conn.executemany(
            "INSERT OR IGNORE INTO citation_map (citation, chunk_id, exact, unit_start, "
            "unit_end) VALUES (?,?,?,?,?)",
            _citation_rows(outline, chunks),
        )
    if definitions is not None:
        conn.executemany(
            "INSERT INTO definitions (term, citation, body, pdf_page) VALUES (?,?,?,?)",
            [(d.term, d.citation, d.text, d.pdf_page) for d in definitions.definitions],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO definition_names (name, term) VALUES (?,?)",
            [(name, d.term) for name, d in definitions.by_name.items()],
        )
    if graph is not None:
        conn.executemany(
            "INSERT OR IGNORE INTO crossrefs (source, target) VALUES (?,?)",
            [(r.source, r.target) for r in graph.references],
        )
    conn.execute("INSERT INTO chunk_fts(chunk_fts) VALUES ('rebuild')")
    conn.commit()
    return conn


def _citation_rows(outline: Outline, chunks: list[Chunk]) -> list[tuple[str, int, int, int, int]]:
    """
    Map every citable provision to the smallest chunk whose text contains it.

    Containment, not string matching. A citation the engine uses may be finer
    than any chunk -- Art. VII §6(j)(1)(i) sits inside the chunk for §6(j)(1) --
    and the provision that *contains* a cited passage is the one worth quoting,
    whereas a citation-prefix ancestor can be an empty heading.

    First writer wins per citation, and chunks are considered smallest-first, so
    a provision is mapped to the tightest passage holding it.
    """
    ordered = sorted(enumerate(chunks, start=1), key=lambda pair: pair[1].end - pair[1].start)
    rows: list[tuple[str, int, int, int, int]] = []
    placed: set[str] = set()
    for unit in outline.units:
        if unit.article is None:
            continue
        citation = unit.citation
        if citation in placed:
            continue
        for chunk_id, chunk in ordered:
            if chunk.start <= unit.start < chunk.end:
                placed.add(citation)
                rows.append(
                    (
                        citation,
                        chunk_id,
                        int(chunk.citation == citation),
                        unit.start,
                        unit.subtree_end,
                    )
                )
                break
    return rows


def open_index(path: Path | str) -> sqlite3.Connection:
    """How the serving application opens it (ADR-004): read-only."""
    uri = f"file:{Path(path).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_hit(row: sqlite3.Row) -> Hit:
    return Hit(
        citation=row["citation"],
        heading_path=row["heading_path"],
        body=row["body"],
        pdf_page=row["pdf_page"],
        printed_page=row["printed_page"],
        score=row["score"],
        ordinal=row["ordinal"],
    )


def search(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[Hit]:
    """
    The passages best matching a question, best first.

    Scored on `indexed_text`, which carries the heading path as well as the
    body -- a subsection never repeats the heading it sits under, although that
    is how a reader would search for it.
    """
    match = escape_query(query)
    rows = conn.execute(
        """
        SELECT c.citation, c.heading_path, c.body, c.pdf_page, c.printed_page,
               c.ordinal, bm25(chunk_fts) AS score
        FROM chunk_fts
        JOIN chunks c ON c.id = chunk_fts.rowid
        WHERE chunk_fts MATCH ?
        ORDER BY score
        LIMIT ?
        """,
        (match, limit),
    ).fetchall()
    return [_row_to_hit(row) for row in rows]


def fetch(conn: sqlite3.Connection, citation: str, ordinal: int = 1) -> Hit | None:
    """
    One passage by citation, with no search involved.

    This is the deterministic half (task 5.7): a violation code names a
    citation, and the text comes back by lookup. The model quotes it; it never
    chooses it.
    """
    row = conn.execute(
        "SELECT citation, heading_path, body, pdf_page, printed_page, ordinal, 0.0 AS score "
        "FROM chunks WHERE citation = ? AND ordinal = ?",
        (citation, ordinal),
    ).fetchone()
    return _row_to_hit(row) if row else None


def count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
    return int(row["n"])


def targets_of(conn: sqlite3.Connection, citation: str) -> list[str]:
    """What this provision points at, read from the artifact."""
    rows = conn.execute(
        "SELECT target FROM crossrefs WHERE source = ? ORDER BY target", (citation,)
    ).fetchall()
    return [row["target"] for row in rows]


def sources_citing(conn: sqlite3.Connection, citation: str) -> list[str]:
    """What points *at* this provision."""
    rows = conn.execute(
        "SELECT source FROM crossrefs WHERE target = ? ORDER BY source", (citation,)
    ).fetchall()
    return [row["source"] for row in rows]


@dataclass(frozen=True, slots=True)
class StoredDefinition:
    term: str
    citation: str
    body: str
    pdf_page: int


def definition_for(conn: sqlite3.Connection, name: str) -> StoredDefinition | None:
    """
    One definition by any name it answers to, including aliases and pointers.

    Case-sensitive, matching how the terms are extracted: the document
    capitalises a term where it carries its defined meaning.
    """
    row = conn.execute(
        "SELECT d.term, d.citation, d.body, d.pdf_page FROM definition_names n "
        "JOIN definitions d ON d.term = n.term WHERE n.name = ?",
        (name,),
    ).fetchone()
    if row is None:
        return None
    return StoredDefinition(row["term"], row["citation"], row["body"], row["pdf_page"])


def all_definition_names(conn: sqlite3.Connection) -> list[str]:
    """Every name the index can explain, longest first for greedy matching."""
    rows = conn.execute("SELECT name FROM definition_names").fetchall()
    return sorted((row["name"] for row in rows), key=len, reverse=True)


_MARKER = re.compile(r"\(([A-Za-z0-9]{1,5})\)")


def fetch_nearest(conn: sqlite3.Connection, citation: str) -> tuple[Hit | None, str]:
    """
    A provision's text, falling back to the chunk that contains it.

    Chunks stop splitting once a passage fits the ceiling, so a citation the
    engine uses may not be a chunk of its own: Art. VII §2(e)(2)(i)(A) lives
    inside the chunk for §2(e)(2)(i). Returning nothing would leave a rule the
    engine enforces with no text to quote.

    The citation actually found comes back alongside, because the caller must
    not claim to be quoting (A) when it is holding (i).
    """
    if exact := fetch(conn, citation):
        return exact, citation
    row = conn.execute(
        "SELECT c.citation, c.heading_path, c.body, c.pdf_page, c.printed_page, c.ordinal, "
        "0.0 AS score FROM citation_map m JOIN chunks c ON c.id = m.chunk_id "
        "WHERE m.citation = ?",
        (citation,),
    ).fetchone()
    if row is not None:
        hit = _row_to_hit(row)
        return hit, hit.label
    markers = _MARKER.findall(citation)
    head = citation[: citation.index("(")] if "(" in citation else citation
    for drop in range(1, len(markers) + 1):
        kept = markers[: len(markers) - drop]
        candidate = head + "".join(f"({m})" for m in kept)
        if found := fetch(conn, candidate):
            return found, candidate
    return None, citation


def chunks_within(conn: sqlite3.Connection, citation: str, limit: int = 6) -> list[Hit]:
    """
    Every passage inside a cited provision, in document order.

    A citation naming a Section that was split resolves to that Section's
    preamble, which is often just its heading -- "(e) Operation of Apron
    Levels." is 30 characters. The provision's substance is in the subsections
    beneath it, so those come too.

    Capped, because Art. VII §1 covers 82,893 characters and nobody asked for
    a chapter.
    """
    rows = conn.execute(
        """
        SELECT c.citation, c.heading_path, c.body, c.pdf_page, c.printed_page, c.ordinal,
               0.0 AS score
        FROM citation_map m
        JOIN chunks c ON c.span_start >= m.unit_start AND c.span_start < m.unit_end
        WHERE m.citation = ?
        ORDER BY c.span_start
        LIMIT ?
        """,
        (citation, limit),
    ).fetchall()
    return [_row_to_hit(row) for row in rows]
