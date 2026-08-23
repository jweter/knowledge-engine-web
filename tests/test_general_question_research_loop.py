from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from knowledge_engine_web import ai_orchestration
from knowledge_engine_web.ai_orchestration import run_ai_orchestration
from knowledge_engine_web.config import Settings


def _ready_settings(tmp_path: Path) -> Settings:
    sources = tmp_path / "sources.csv"
    evidence = tmp_path / "evidence.jsonl"
    sources.write_text("source_id,title\n", encoding="utf-8")
    evidence.write_text("", encoding="utf-8")
    ledger = tmp_path / "federated-runs"
    return Settings(
        _env_file=None,
        llm_model="qwen2.5:1.5b",
        sources_path=str(sources),
        evidence_records_path=str(evidence),
        session_db_path=str(tmp_path / "sessions.sqlite3"),
        ke_executable=sys.executable,
        federated_discovery_ledger_root=str(ledger),
        federated_openalex_api_key="oa-test",
        federated_semantic_scholar_api_key="s2-test",
    )


def test_web_research_copilot_enables_bounded_discovery_policy_for_every_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _ready_settings(tmp_path)
    captured: dict[str, object] = {}
    expected = SimpleNamespace(session_id="session-general-question")

    class FakeLLM:
        def __init__(self, *, model: str, host: str) -> None:
            captured["model"] = model
            captured["host"] = host

    def fake_run(question: str, **kwargs: object) -> object:
        captured["question"] = question
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(ai_orchestration, "OllamaLLM", FakeLLM)
    monkeypatch.setattr(ai_orchestration, "run_research_question", fake_run)

    result = run_ai_orchestration(settings, "Does creatine improve maximal strength?")

    assert result.session_id == expected.session_id
    assert captured["question"] == "Does creatine improve maximal strength?"
    policy = captured["discovery_policy"]
    assert policy is not None
    assert policy.ledger_root == Path(settings.federated_discovery_ledger_root)
    assert policy.enable_federated_discovery is True
    assert policy.openalex_api_key == "oa-test"
    assert policy.semantic_scholar_api_key == "s2-test"
    assert policy.ke_executable == sys.executable


def test_general_question_policy_keeps_indexed_evidence_first(tmp_path: Path) -> None:
    settings = _ready_settings(tmp_path)
    policy = ai_orchestration._build_discovery_policy(settings, sys.executable)

    # The AI layer owns the deterministic coverage-gap trigger. Web only opts
    # the Research Copilot into that bounded policy; it does not bypass local
    # retrieval or turn discovery candidates directly into evidence.
    assert policy.min_evidence_record_coverage > 0
    assert policy.discovery_limit_per_provider <= 100
    assert policy.discovery_max_execution_seconds > 0
