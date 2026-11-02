"""Pin the existing Web Ask corpus/model prerequisites before online-only migration."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_engine_web import main
from knowledge_engine_web.ai_orchestration import evaluate_ai_capability
from knowledge_engine_web.config import Settings


def test_default_ask_without_model_or_corpus_still_uses_indexed_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The current Ask route cannot silently become an online-only answer."""
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'unused.sqlite3'}",
        llm_model=None,
        sources_path=None,
        evidence_records_path=None,
    )
    assert evaluate_ai_capability(settings).reason_code == "model_not_configured"
    monkeypatch.setattr(main, "Settings", lambda: settings)
    indexed_engine = object()
    observed: list[tuple[object, str]] = []
    monkeypatch.setattr(main, "_engine", lambda: indexed_engine)

    def indexed_retrieval(engine: object, question: str, **kwargs: object) -> list[object]:
        observed.append((engine, question))
        return []

    monkeypatch.setattr(main, "answer_retrieval", indexed_retrieval)
    monkeypatch.setattr(
        main,
        "run_guarded_ai_orchestration",
        lambda *args, **kwargs: pytest.fail("Unavailable Research must not run"),
    )
    monkeypatch.setattr(
        main,
        "submit_research_job",
        lambda *args, **kwargs: pytest.fail("Unavailable Research must not start"),
    )

    response = TestClient(main.app).get("/ask", params={"q": "one online question"})
    assert response.status_code == 200
    assert observed == [(indexed_engine, "one online question")]
    assert "Broader Research is unavailable" in response.text
    assert "Indexed retrieval results are shown below" in response.text


def test_research_requires_both_local_corpus_paths_after_model_is_set(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "sources.csv"
    sources.write_text("source_id,title\n", encoding="utf-8")
    without_sources = Settings(
        _env_file=None,
        llm_model="local-test-model",
        sources_path=None,
        evidence_records_path=None,
    )
    assert evaluate_ai_capability(without_sources).reason_code == "sources_unavailable"

    without_evidence = Settings(
        _env_file=None,
        llm_model="local-test-model",
        sources_path=str(sources),
        evidence_records_path=None,
    )
    assert evaluate_ai_capability(without_evidence).reason_code == "evidence_unavailable"
