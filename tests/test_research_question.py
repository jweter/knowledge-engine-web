from __future__ import annotations

from knowledge_engine_web.research_question import derive_research_question_id


def test_same_query_text_produces_the_same_id() -> None:
    first = derive_research_question_id("GLP-1 weight loss")
    second = derive_research_question_id("GLP-1 weight loss")

    assert first == second


def test_id_is_insensitive_to_case_and_surrounding_whitespace() -> None:
    canonical = derive_research_question_id("GLP-1 weight loss")

    assert derive_research_question_id("  glp-1 weight loss  ") == canonical
    assert derive_research_question_id("GLP-1 WEIGHT LOSS") == canonical


def test_id_is_insensitive_to_internal_whitespace_variation() -> None:
    canonical = derive_research_question_id("GLP-1 weight loss")

    assert derive_research_question_id("GLP-1   weight loss") == canonical
    assert derive_research_question_id("GLP-1\tweight\nloss") == canonical


def test_different_questions_produce_different_ids() -> None:
    assert derive_research_question_id("GLP-1 weight loss") != derive_research_question_id(
        "semaglutide cardiovascular outcomes"
    )


def test_id_has_a_stable_recognizable_prefix() -> None:
    assert derive_research_question_id("anything").startswith("rq-web-")
