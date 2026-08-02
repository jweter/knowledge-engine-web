"""Read-only lexical retrieval over `core`'s SQLite FTS5 index.

Reads the same `paper_search` FTS5 virtual table `core`'s
`knowledge_engine/database.py` creates and `knowledge_engine/search.py`'s
`SearchService` queries -- ported here rather than imported, matching
`graph_reader.py`'s "read `core`'s database directly, never import
`knowledge_engine`" decision (`docs/web_design.md`). The FTS5 query
logic (`build_natural_language_fts_query`, the `bm25`/`snippet` SQL) is
copied verbatim from `core`'s `SearchService`, since it is the one
retrieval mechanism `core` has already built and this project is
deliberately staying a thin, honest read layer rather than reinventing
ranking. No new candidate-selection or scoring logic of its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import Engine, inspect, text

_NATURAL_LANGUAGE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "do",
    "does",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True)
class SearchResult:
    """One paper returned from a retrieval query."""

    paper_id: int
    title: str
    abstract: str | None
    publication_year: int | None
    doi: str | None
    score: float
    snippet: str
    matched_query: str


def build_natural_language_fts_query(question: str) -> str:
    """Convert a natural-language question into a safe SQLite FTS query.

    Identical to `core`'s `knowledge_engine.search.build_natural_language_fts_query`.
    """

    tokens = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", question.lower()):
        if len(token) < 3 or token in _NATURAL_LANGUAGE_STOPWORDS:
            continue
        if token not in tokens:
            tokens.append(token)
    return " OR ".join(tokens)


def answer_retrieval(engine: Engine, question: str, limit: int = 5) -> list[SearchResult]:
    """Retrieve papers relevant to a natural-language question.

    Retrieval only -- converts a question into a conservative FTS query
    and returns ranked papers, no scientific claim is synthesized. Returns
    an empty list for a blank question, an FTS-query-less question (e.g.
    only stopwords), or a database with no `paper_search` table yet
    (predates `core`'s FTS index, or a fixture database in tests) --
    never raises for any of those real, expected states.
    """

    normalized_question = question.strip()
    if not normalized_question:
        return []
    fts_query = build_natural_language_fts_query(normalized_question)
    if not fts_query:
        return []

    # A database predating `core`'s FTS index (or a fixture database in
    # tests without one) is a real, expected state, matching
    # `graph_reader.py`'s "missing table means empty, not an error" posture.
    if "paper_search" not in set(inspect(engine).get_table_names()):
        return []

    with engine.connect() as connection:
        result_rows = connection.execute(
            text("""
                SELECT
                    p.id,
                    p.title,
                    p.abstract,
                    p.publication_year,
                    p.doi,
                    bm25(paper_search, 5.0, 3.0, 1.0, 0.5) AS score,
                    snippet(paper_search, -1, '[', ']', ' ... ', 32) AS snippet
                FROM paper_search
                JOIN papers p ON p.id = paper_search.rowid
                WHERE paper_search MATCH :query
                ORDER BY score
                LIMIT :limit
                """),
            {"query": fts_query, "limit": limit},
        ).all()

    return [
        SearchResult(
            paper_id=int(row.id),
            title=str(row.title),
            abstract=row.abstract,
            publication_year=row.publication_year,
            doi=row.doi,
            score=float(row.score),
            snippet=str(row.snippet or ""),
            matched_query=fts_query,
        )
        for row in result_rows
    ]
