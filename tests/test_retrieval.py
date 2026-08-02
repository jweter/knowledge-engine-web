from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, MetaData, Table, insert, text

from knowledge_engine_web.retrieval import (
    SearchResult,
    answer_retrieval,
    build_natural_language_fts_query,
)
from tests._fixtures import build_engine, create_papers_table


def _create_fts_table(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS paper_search
                USING fts5(
                    title,
                    abstract,
                    body_text,
                    raw_text,
                    tokenize='porter unicode61'
                )
                """)
        )


def _insert_paper(
    engine: Engine, *, paper_id: int, title: str, doi: str, abstract: str = ""
) -> None:
    metadata = MetaData()
    papers = Table("papers", metadata, autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(insert(papers).values(id=paper_id, title=title, doi=doi))
        connection.execute(
            text(
                "INSERT INTO paper_search(rowid, title, abstract, body_text, raw_text) "
                "VALUES (:id, :title, :abstract, '', '')"
            ),
            {"id": paper_id, "title": title, "abstract": abstract},
        )


def test_build_natural_language_fts_query_drops_stopwords_and_short_tokens() -> None:
    query = build_natural_language_fts_query("does semaglutide reduce body weight")

    assert query == "semaglutide OR reduce OR body OR weight"


def test_build_natural_language_fts_query_returns_empty_for_only_stopwords() -> None:
    assert build_natural_language_fts_query("is a the of") == ""


def test_answer_retrieval_returns_an_empty_list_for_a_blank_question(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)

    assert answer_retrieval(engine, "   ") == []


def test_answer_retrieval_returns_an_empty_list_when_no_fts_table_exists_yet(
    tmp_path: Path,
) -> None:
    engine = build_engine(tmp_path)
    create_papers_table(engine)

    assert answer_retrieval(engine, "does semaglutide reduce body weight") == []


def test_answer_retrieval_matches_an_indexed_paper(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    create_papers_table(engine)
    _create_fts_table(engine)
    _insert_paper(
        engine,
        paper_id=1,
        title="A Trial of Semaglutide for Body Weight Reduction",
        doi="10.1000/example",
        abstract="Semaglutide reduced body weight versus placebo.",
    )

    results = answer_retrieval(engine, "does semaglutide reduce body weight")

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, SearchResult)
    assert result.paper_id == 1
    assert result.doi == "10.1000/example"
    assert result.matched_query == "semaglutide OR reduce OR body OR weight"


def test_answer_retrieval_respects_limit(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    create_papers_table(engine)
    _create_fts_table(engine)
    for paper_id in range(1, 4):
        _insert_paper(
            engine,
            paper_id=paper_id,
            title=f"Semaglutide paper {paper_id}",
            doi=f"10.1000/example-{paper_id}",
        )

    results = answer_retrieval(engine, "semaglutide", limit=2)

    assert len(results) == 2


def test_answer_retrieval_finds_nothing_for_an_unmatched_question(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    create_papers_table(engine)
    _create_fts_table(engine)
    _insert_paper(engine, paper_id=1, title="Semaglutide paper", doi="10.1000/example")

    assert answer_retrieval(engine, "does metformin reduce blood glucose") == []
