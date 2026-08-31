from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from knowledge_engine_ai.copilot.research_report import ResearchReport
from knowledge_engine_ai.copilot.research_report_integration import ResearchReportBuildResult
from knowledge_engine_ai.copilot.research_state import ResearchStateResult
from knowledge_engine_ai.copilot.run_research_question import ResearchQuestionResult

from knowledge_engine_web import ai_orchestration, research_jobs
from knowledge_engine_web.ai_orchestration import WebResearchResult
from knowledge_engine_web.config import Settings


def _report_settings() -> Settings:
    return cast(
        Settings,
        SimpleNamespace(
            llm_model="qwen2.5:1.5b",
            ollama_host="http://localhost:11434",
            ai_request_timeout_seconds=42.0,
        ),
    )


def test_report_projection_waits_for_releaseable_base_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    research = cast(
        ResearchQuestionResult,
        SimpleNamespace(narrative_releaseable=False),
    )

    def should_not_run(*args: object, **kwargs: object) -> ResearchReportBuildResult:
        raise AssertionError("structured report builder ran before the base release gate")

    monkeypatch.setattr(ai_orchestration, "build_research_report_for_result", should_not_run)

    result = ai_orchestration._build_research_report_projection(_report_settings(), research)

    assert not result.available
    assert result.error_code == "base_answer_not_releaseable"


def test_report_projection_uses_ai_typed_integration_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    research = cast(
        ResearchQuestionResult,
        SimpleNamespace(narrative_releaseable=True),
    )
    expected = ResearchReportBuildResult(
        report=None,
        error_code="research_report_generation_failed",
    )
    captured: dict[str, object] = {}

    class FakeLLM:
        def __init__(self, *, model: str, host: str) -> None:
            captured["model"] = model
            captured["host"] = host

    def fake_builder(
        result: ResearchQuestionResult,
        llm: object,
        *,
        timeout_seconds: float | None = None,
    ) -> ResearchReportBuildResult:
        captured["result"] = result
        captured["llm"] = llm
        captured["timeout_seconds"] = timeout_seconds
        return expected

    monkeypatch.setattr(ai_orchestration, "OllamaLLM", FakeLLM)
    monkeypatch.setattr(ai_orchestration, "build_research_report_for_result", fake_builder)

    result = ai_orchestration._build_research_report_projection(_report_settings(), research)

    assert result is expected
    assert captured["result"] is research
    assert captured["model"] == "qwen2.5:1.5b"
    assert captured["host"] == "http://localhost:11434"
    assert captured["timeout_seconds"] == 42.0


def test_report_projection_failure_preserves_verified_base_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    research = cast(
        ResearchQuestionResult,
        SimpleNamespace(narrative_releaseable=True),
    )

    class FakeLLM:
        def __init__(self, *, model: str, host: str) -> None:
            pass

    def fail_builder(*args: object, **kwargs: object) -> ResearchReportBuildResult:
        raise RuntimeError("private provider detail must not escape")

    monkeypatch.setattr(ai_orchestration, "OllamaLLM", FakeLLM)
    monkeypatch.setattr(ai_orchestration, "build_research_report_for_result", fail_builder)

    result = ai_orchestration._build_research_report_projection(_report_settings(), research)

    assert not result.available
    assert result.error_code == "research_report_integration_failed"


def test_async_job_payload_carries_structured_report_without_parsing_narrative() -> None:
    class FakeReport:
        def to_dict(self) -> dict[str, object]:
            return {
                "schema_version": 1,
                "bottom_line": "Structured bottom line [ev-1]",
                "conclusion_rows": [
                    {
                        "question_dimension": "one-year effect",
                        "conclusion": "Direct one-year evidence was not found.",
                        "certainty": "low",
                        "supporting_evidence_ids": ["ev-1"],
                        "contradicting_or_null_evidence_ids": ["ev-2"],
                        "directness": "indirect_context",
                        "missing_direct_evidence": "Direct approximately one-year evidence",
                    }
                ],
            }

    report = ResearchReportBuildResult(
        report=cast(ResearchReport, FakeReport()),
        error_code=None,
    )
    research = cast(
        ResearchQuestionResult,
        SimpleNamespace(
            session_id="session-123",
            question="question",
            workflow=SimpleNamespace(steps=()),
            narrative="Narrative text with no structured report semantics.",
            narrative_releaseable=True,
            synthesis_error=None,
            progress_report=None,
            conversion_funnel_report=None,
            verification=None,
            close_result=SimpleNamespace(status=SimpleNamespace(value="closed")),
        ),
    )
    research_state = cast(
        ResearchStateResult,
        SimpleNamespace(
            state=SimpleNamespace(value="verified"),
            reason="verified_grounded_answer",
        ),
    )
    result = WebResearchResult(
        research=research,
        research_state=research_state,
        research_report=report,
    )

    payload = research_jobs._presentation_payload(result)

    assert payload["narrative"] == "Narrative text with no structured report semantics."
    assert payload["research_report"] == {
        "available": True,
        "error_code": None,
        "report": {
            "schema_version": 1,
            "bottom_line": "Structured bottom line [ev-1]",
            "conclusion_rows": [
                {
                    "question_dimension": "one-year effect",
                    "conclusion": "Direct one-year evidence was not found.",
                    "certainty": "low",
                    "supporting_evidence_ids": ["ev-1"],
                    "contradicting_or_null_evidence_ids": ["ev-2"],
                    "directness": "indirect_context",
                    "missing_direct_evidence": "Direct approximately one-year evidence",
                }
            ],
        },
    }
