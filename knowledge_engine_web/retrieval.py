"""Read-only retrieval over `core`'s SQLite FTS5 index and Evidence Records.

Reads the same `paper_search` FTS5 virtual table `core`'s
`knowledge_engine/database.py` creates and `knowledge_engine/search.py`'s
`SearchService` queries -- ported here rather than imported, matching
`graph_reader.py`'s "read `core`'s database directly, never import
`knowledge_engine`" decision (`docs/web_design.md`). The FTS5 query
logic (`build_natural_language_fts_query`, the `bm25`/`snippet` SQL) is
copied verbatim from `core`'s `SearchService`. FTS5 remains candidate
generation; a deterministic second pass then re-ranks by how well each
candidate's text covers the question's *distinctive* terms, weighted by
each term's corpus-wide rarity (a smoothed IDF) so that words shared by
nearly every paper in a topically narrow corpus (e.g. "GLP-1",
"obesity" in a GLP-1 corpus) cannot drown out a question's actually
differentiating words (e.g. "height"). This applies whether or not
Evidence Records are configured; when they are, the same rarity
weighting is applied to Evidence Record field coverage instead of raw
title/abstract text. The reranker never uses Evidence Quality,
confidence, consensus, or an LLM.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy import Connection, Engine, inspect, text

from knowledge_engine_web.evidence_reader import (
    EvidenceRecordDetail,
    index_evidence_records_by_doi,
    normalize_doi,
)

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

_EVIDENCE_CANDIDATE_LIMIT = 500
_EVIDENCE_FIELD_WEIGHTS = {
    "research_question": 5.0,
    "claim_text": 3.0,
    "pico": 2.0,
    "result_summary": 1.0,
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
    evidence_alignment_score: float = 0.0


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


def answer_retrieval(
    engine: Engine,
    question: str,
    limit: int = 5,
    *,
    evidence_path: Path | None = None,
) -> list[SearchResult]:
    """Retrieve papers relevant to a natural-language question.

    Retrieval only -- converts a question into a conservative FTS query
    and returns ranked papers, no scientific claim is synthesized. Returns
    an empty list for a blank question, an FTS-query-less question (e.g.
    only stopwords), or a database with no `paper_search` table yet
    (predates `core`'s FTS index, or a fixture database in tests) --
    never raises for any of those real, expected states.

    FTS5's `bm25()` alone is not enough to differentiate questions in a
    topically narrow corpus: a term present in nearly every paper's title
    (e.g. "GLP-1" in a GLP-1-only corpus) can outweigh a question's one
    actually distinguishing word (e.g. "height"), so unrelated questions
    end up returning the same top papers. The second-pass rerank below
    weights each question token by its corpus-wide rarity (a smoothed
    IDF) before scoring coverage, so rare/distinguishing words count for
    more than words nearly every paper shares.
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

    evidence_by_doi = (
        index_evidence_records_by_doi(evidence_path) if evidence_path is not None else {}
    )
    candidate_limit = max(limit, _EVIDENCE_CANDIDATE_LIMIT) if evidence_by_doi else limit
    question_tokens = _retrieval_tokens(normalized_question)

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
            {"query": fts_query, "limit": candidate_limit},
        ).all()
        token_weights = _token_idf_weights(connection, question_tokens)

    candidates = [
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

    ranked: list[tuple[float, int, SearchResult]] = []
    for lexical_rank, candidate in enumerate(candidates):
        if evidence_by_doi:
            records = evidence_by_doi.get(normalize_doi(candidate.doi or ""), ())
            alignment = max(
                (_evidence_alignment(question_tokens, token_weights, record) for record in records),
                default=0.0,
            )
        else:
            alignment = _text_alignment(
                question_tokens, token_weights, f"{candidate.title} {candidate.abstract or ''}"
            )
        ranked.append(
            (
                alignment,
                lexical_rank,
                replace(candidate, evidence_alignment_score=alignment),
            )
        )
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:limit]]


def _retrieval_tokens(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", value.lower())
        if len(token) >= 3 and token not in _NATURAL_LANGUAGE_STOPWORDS
    }


def _token_idf_weights(connection: Connection, tokens: set[str]) -> dict[str, float]:
    """Return a smoothed inverse-document-frequency weight per token.

    A token nearly every paper in the corpus contains (e.g. "obesity" in
    a corpus that is entirely about obesity) gets a weight near zero; a
    token few papers contain (e.g. "height") gets a large weight. This is
    the standard smoothed-IDF form `log((N + 1) / (df + 1)) + 1`, which
    stays positive and finite even when a token matches every paper or no
    paper at all.
    """

    if not tokens:
        return {}
    total_papers = connection.execute(text("SELECT count(*) FROM paper_search")).scalar_one()
    weights: dict[str, float] = {}
    for token in tokens:
        document_frequency = connection.execute(
            text("SELECT count(*) FROM paper_search WHERE paper_search MATCH :token"),
            {"token": token},
        ).scalar_one()
        weights[token] = math.log((total_papers + 1) / (document_frequency + 1)) + 1
    return weights


def _weighted_token_coverage(
    question_tokens: set[str], token_weights: dict[str, float], text_tokens: set[str]
) -> float:
    """Return the fraction of the question's rarity-weighted token mass a text covers."""

    if not question_tokens:
        return 0.0
    total_weight = sum(token_weights.get(token, 1.0) for token in question_tokens)
    if total_weight <= 0:
        return 0.0
    matched_weight = sum(token_weights.get(token, 1.0) for token in question_tokens & text_tokens)
    return matched_weight / total_weight


def _text_alignment(
    question_tokens: set[str], token_weights: dict[str, float], value: str
) -> float:
    """Return rarity-weighted question-token coverage for raw title/abstract text."""

    return _weighted_token_coverage(question_tokens, token_weights, _retrieval_tokens(value))


def _evidence_alignment(
    question_tokens: set[str],
    token_weights: dict[str, float],
    evidence: EvidenceRecordDetail,
) -> float:
    """Return rarity-weighted question-token coverage for one stored Evidence Record."""

    if not question_tokens:
        return 0.0
    pico = " ".join(
        value
        for value in (
            evidence.population,
            evidence.intervention,
            evidence.comparator,
            evidence.outcome,
        )
        if isinstance(value, str)
    )
    fields = {
        "research_question": evidence.research_question,
        "claim_text": evidence.claim_text,
        "pico": pico,
        "result_summary": evidence.result_summary,
    }
    weighted_coverage = sum(
        _EVIDENCE_FIELD_WEIGHTS[field]
        * _weighted_token_coverage(question_tokens, token_weights, _retrieval_tokens(value))
        for field, value in fields.items()
    )
    return weighted_coverage / sum(_EVIDENCE_FIELD_WEIGHTS.values())
