from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from knowledge_engine_ai.copilot.discovery_policy import FederatedDiscoveryPolicy
from knowledge_engine_ai.copilot.grounded_completion import GroundedCompletionPolicy

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
        research_papers_dir=str(tmp_path / "research-papers"),
        session_db_path=str(tmp_path / "sessions.sqlite3"),
        ke_executable=sys.executable,
        federated_discovery_ledger_root=str(ledger),
        federated_openalex_api_key="oa-test",
        federated_semantic_scholar_api_key="s2-test",
    )


def test_web_research_mode_enables_complete_bounded_research_for_every_question(
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

    discovery_policy = cast(FederatedDiscoveryPolicy, captured["discovery_policy"])
    assert discovery_policy.ledger_root == Path(settings.federated_discovery_ledger_root)
    assert discovery_policy.enable_federated_discovery is True
    assert discovery_policy.enable_acquisition_plan is True
    assert discovery_policy.openalex_api_key == "oa-test"
    assert discovery_policy.semantic_scholar_api_key == "s2-test"
    assert discovery_policy.ke_executable == sys.executable

    completion_policy = cast(GroundedCompletionPolicy, captured["grounded_completion_policy"])
    assert completion_policy.ledger_root == discovery_policy.ledger_root
    assert completion_policy.papers_dir == Path(settings.research_papers_dir)
    assert completion_policy.grounding_model == "qwen2.5:1.5b"


def test_general_question_policy_keeps_indexed_evidence_first(tmp_path: Path) -> None:
    settings = _ready_settings(tmp_path)
    policy = ai_orchestration._build_discovery_policy(settings, sys.executable)

    # The AI layer owns the deterministic coverage-gap trigger. Web opts
    # Research mode into discovery + acquisition planning, but neither is
    # allowed to bypass local retrieval or turn candidates directly into evidence.
    assert policy.min_evidence_record_coverage > 0
    assert policy.discovery_limit_per_provider <= 100
    assert policy.discovery_max_execution_seconds > 0
    assert policy.enable_acquisition_plan is True


def test_general_question_ai_capability_rejects_invalid_persistent_discovery_ledger(
    tmp_path: Path,
) -> None:
    settings = _ready_settings(tmp_path)
    persistent_root = tmp_path / "persistent"
    persistent_root.mkdir()
    outside_ledger = tmp_path / "outside" / "federated-runs"
    outside_ledger.parent.mkdir()
    settings = Settings(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "discovery_ledger_storage_mode": "persistent",
                "discovery_ledger_persistent_root": str(persistent_root),
                "federated_discovery_ledger_root": str(outside_ledger),
            }
        ),
    )

    capability = ai_orchestration.evaluate_ai_capability(settings)

    assert not capability.available
    assert capability.reason_code == "persistent_ledger_path_invalid"


def test_ask_template_maps_every_stable_gqr_state_to_visitor_messaging() -> None:
    template = (
        Path(__file__).parents[1] / "knowledge_engine_web" / "templates" / "ask.html"
    ).read_text(encoding="utf-8")

    for state in (
        "indexed_answer",
        "research_required",
        "researching",
        "partial_answer",
        "researched_answer",
        "insufficient_evidence",
        "provider_degraded",
        "blocked",
    ):
        assert f"research_state == '{state}'" in template

    assert "Newly acquired" in template
    assert "post-research original-question re-retrieval" in template
    assert "copilot_result.research_state.reason" in template
    assert "copilot_result.research_state.grounded_completion_attempted" in template
    assert "copilot_result.research_state.promoted_evidence_record_count" in template
    assert "copilot_result.research_state.used_reretrieved_evidence" in template
