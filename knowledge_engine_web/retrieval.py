"""Read-only retrieval over `core`'s SQLite FTS5 index and Evidence Records.

Reads the same `paper_search` FTS5 virtual table `core`'s
`knowledge_engine/database.py` creates and `knowledge_engine/search.py`'s
`SearchService` queries. FTS5 is candidate generation only: Ask then re-ranks
candidates by how much of the *actual submitted question* their source-linked
evidence covers and marks only sufficiently aligned candidates as direct
matches.

This module intentionally does not synthesize scientific claims. It does,
however, protect the Ask product from presenting a merely topical paper as if
it answered an outcome the source never studied.
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
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

# Candidate generation must be broader than the final visible result set.
# A narrow top-5 FTS OR query can easily miss the paper containing the rare,
# question-defining term. The second pass is what decides directness.
_RETRIEVAL_CANDIDATE_LIMIT = 200
_EVIDENCE_CANDIDATE_LIMIT = 500
_DIRECT_ALIGNMENT_THRESHOLD = 0.60
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
    direct_match: bool = False


def build_natural_language_fts_query(question: str) -> str:
    """Convert a natural-language question into a safe SQLite FTS query.

    Meaningful two-character terms are deliberately preserved. Scientific
    questions routinely contain short outcome/acronym tokens such as IQ, AI,
    BP, or HR. The previous three-character floor silently discarded `IQ`,
    turning e.g. "does semaglutide increase IQ?" into a broad semaglutide
    query and allowing unrelated cardiometabolic papers to look relevant.
    """

    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", question.lower()):
        if len(token) < 2 or token in _NATURAL_LANGUAGE_STOPWORDS:
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
    """Retrieve and relevance-qualify papers for a natural-language question.

    FTS is intentionally broad candidate generation. The final ranking uses
    rarity-weighted coverage of the submitted question and each returned
    `SearchResult` records whether it clears the direct-answer threshold.

    The caller may still expose below-threshold papers as explicitly labelled
    background, but must not present them as evidence that answers the question.
    """

    normalized_question = question.strip()
    if not normalized_question:
        return []
    fts_query = build_natural_language_fts_query(normalized_question)
    if not fts_query:
        return []

    if "paper_search" not in set(inspect(engine).get_table_names()):
        return []

    evidence_by_doi = (
        index_evidence_records_by_doi(evidence_path) if evidence_path is not None else {}
    )
    candidate_limit = max(
        limit,
        _EVIDENCE_CANDIDATE_LIMIT if evidence_by_doi else _RETRIEVAL_CANDIDATE_LIMIT,
    )
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
                replace(
                    candidate,
                    evidence_alignment_score=alignment,
                    direct_match=alignment >= _DIRECT_ALIGNMENT_THRESHOLD,
                ),
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
        if len(token) >= 2 and token not in _NATURAL_LANGUAGE_STOPWORDS
    }


def _token_idf_weights(connection: Connection, tokens: set[str]) -> dict[str, float]:
    """Return a smoothed inverse-document-frequency weight per token."""

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
