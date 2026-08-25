from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, MetaData, Table, insert, text

from knowledge_engine_web.retrieval import answer_retrieval, build_natural_language_fts_query
from tests._fixtures import build_engine, create_papers_table


def _create_fts_table(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS paper_search
                USING fts5(
                    title,
                    abstract,
                    body_text,
                    raw_text,
                    tokenize='porter unicode61'
                )
                """
            )
        )


def _insert_paper(
    engine: Engine, *, paper_id: int, title: str, doi: str, abstract: str = ""
) -> None:
    metadata = MetaData()
    papers = Table("papers", metadata, autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(
            insert(papers).values(id=paper_id, title=title, doi=doi, abstract=abstract or None)
        )
        connection.execute(
            text(
                "INSERT INTO paper_search(rowid, title, abstract, body_text, raw_text) "
                "VALUES (:id, :title, :abstract, '', '')"
            ),
            {"id": paper_id, "title": title, "abstract": abstract},
        )


def test_short_scientific_term_is_not_deleted_from_question() -> None:
    query = build_natural_language_fts_query("does semaglutide increase IQ?")

    assert query == "semaglutide OR increase OR iq"


def test_merely_topical_semaglutide_paper_is_not_a_direct_iq_answer(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    create_papers_table(engine)
    _create_fts_table(engine)
    _insert_paper(
        engine,
        paper_id=1,
        title="Effects of Semaglutide on Cardiometabolic Risk in People with Obesity",
        doi="10.1000/cardiometabolic",
        abstract=(
            "Semaglutide treatment was associated with changes in body weight, waist circumference, "
            "HbA1c, blood pressure, and visceral fat."
        ),
    )

    results = answer_retrieval(engine, "does semaglutide increase IQ?", limit=5)

    assert len(results) == 1
    assert results[0].direct_match is False


def test_source_covering_requested_outcome_is_a_direct_answer_match(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    create_papers_table(engine)
    _create_fts_table(engine)
    _insert_paper(
        engine,
        paper_id=1,
        title="Semaglutide and cognitive outcomes",
        doi="10.1000/cognitive",
        abstract="A study evaluated whether semaglutide increased IQ scores in participants.",
    )

    results = answer_retrieval(engine, "does semaglutide increase IQ?", limit=5)

    assert len(results) == 1
    assert results[0].direct_match is True
    assert results[0].evidence_alignment_score >= 0.60
