"""Web's online evidence preview is independently guarded and never a report."""

from __future__ import annotations

import shutil
from typing import Any

import pytest
from fastapi.testclient import TestClient
from knowledge_engine_ai.copilot.online_evidence_adapter import (
    ContentCheckedOnlineEvidence,
    OnlineSource,
)
from knowledge_engine_ai.ke_client import KeCommandError, OnlineResearchEvidenceResult

from knowledge_engine_web import main
from knowledge_engine_web import online_evidence_orchestration as online
from knowledge_engine_web.ai_guardrails import AIAdmissionError, AIRequestGuard
from knowledge_engine_web.config import Settings


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def _result() -> OnlineResearchEvidenceResult:
    return OnlineResearchEvidenceResult(
        evidence=ContentCheckedOnlineEvidence(
            question="What is known?",
            sources=(
                OnlineSource(
                    "src-unavailable",
                    "https://example.org/unavailable",
                    "pubmed",
                    "2026-11-02T12:00:00+00:00",
                    "unavailable",
                    None,
                    "provider unavailable",
                    None,
                ),
            ),
            excerpts=(),
            claims=(),
        ),
        search_run_id="run-verified",
    )


def test_disabled_preview_never_invokes_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(online, "online_research_evidence", lambda *a, **k: pytest.fail("called"))
    with pytest.raises(online.OnlineEvidenceOrchestrationError, match="unavailable"):
        online.run_guarded_online_evidence(_settings(), "Question", client_key="visitor")


def test_enabled_preview_does_not_require_corpus_or_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "C:/fake/ke.exe")
    calls: list[dict[str, object]] = []

    def fake_retrieve(question: str, **kwargs: object) -> OnlineResearchEvidenceResult:
        calls.append({"question": question, **kwargs})
        return _result()

    monkeypatch.setattr(online, "online_research_evidence", fake_retrieve)
    settings = _settings(
        online_evidence_enabled=True,
        database_url="sqlite:///missing-corpus.sqlite3",
        llm_model=None,
        sources_path=None,
        evidence_records_path=None,
    )
    result = online.run_guarded_online_evidence(
        settings, "  What is known?  ", client_key="visitor", guard=AIRequestGuard()
    )
    assert result.search_run_id == "run-verified"
    assert result.evidence.sources[0].status == "unavailable"
    assert calls[0]["question"] == "What is known?"
    assert calls[0]["max_sources"] == 3
    assert calls[0]["execution_budget"] is not None


def test_failed_provider_response_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "C:/fake/ke.exe")

    def broken(*args: object, **kwargs: object) -> OnlineResearchEvidenceResult:
        raise KeCommandError("secret provider body and local path")

    monkeypatch.setattr(online, "online_research_evidence", broken)
    with pytest.raises(online.OnlineEvidenceOrchestrationError) as exc:
        online.run_guarded_online_evidence(
            _settings(online_evidence_enabled=True), "Question", client_key="visitor"
        )
    assert "secret" not in str(exc.value)


def test_online_evidence_guard_has_own_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "C:/fake/ke.exe")
    monkeypatch.setattr(online, "online_research_evidence", lambda *a, **k: _result())
    guard = AIRequestGuard()
    settings = _settings(online_evidence_enabled=True, online_evidence_rate_limit_requests=1)
    online.run_guarded_online_evidence(settings, "Question", client_key="visitor", guard=guard)
    with pytest.raises(AIAdmissionError, match="too many requests"):
        online.run_guarded_online_evidence(settings, "Question", client_key="visitor", guard=guard)


def test_route_disabled_by_default_and_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "Settings", lambda: _settings())
    monkeypatch.setattr(main, "run_guarded_online_evidence", lambda *a, **k: pytest.fail("called"))
    response = TestClient(main.app).post(
        "/research/online-evidence", json={"question": "What is known?"}
    )
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


def test_route_preserves_unavailable_source_without_inventing_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "Settings", lambda: _settings(online_evidence_enabled=True))
    monkeypatch.setattr(
        main,
        "evaluate_online_evidence_capability",
        lambda settings: online.OnlineEvidenceCapability(True),
    )
    monkeypatch.setattr(main, "run_guarded_online_evidence", lambda *a, **k: _result())
    response = TestClient(main.app).post(
        "/research/online-evidence", json={"question": "What is known?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["research_report_complete"] is False
    assert body["status"] == "content_checked_retrieval_only"
    assert body["search_run_id"] == "run-verified"
    assert body["evidence"]["sources"][0]["status"] == "unavailable"
    assert body["evidence"]["sources"][0]["failure_reason"] == "provider unavailable"
    assert body["evidence"]["claims"] == []


@pytest.mark.parametrize(
    ("reason_code", "expected"),
    [
        ("concurrency_limit_reached", "busy processing requests"),
        ("rate_limit_reached", "too many requests"),
        ("unexpected_reason", "cannot accept this request"),
    ],
)
def test_route_admission_error_uses_json_specific_sanitized_message(
    monkeypatch: pytest.MonkeyPatch, reason_code: str, expected: str
) -> None:
    monkeypatch.setattr(main, "Settings", lambda: _settings(online_evidence_enabled=True))
    monkeypatch.setattr(
        main,
        "evaluate_online_evidence_capability",
        lambda settings: online.OnlineEvidenceCapability(True),
    )

    def reject(*args: object, **kwargs: object) -> None:
        raise AIAdmissionError(
            reason_code,
            "SECRET: Deterministic retrieval results are still shown below.",
        )

    monkeypatch.setattr(main, "run_guarded_online_evidence", reject)
    response = TestClient(main.app).post(
        "/research/online-evidence", json={"question": "What is known?"}
    )
    assert response.status_code == 429
    detail = response.json()["detail"]
    assert expected in detail
    assert "SECRET" not in detail
    assert "shown below" not in detail


def test_route_rejects_blank_input_without_running_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "Settings", lambda: _settings(online_evidence_enabled=True))
    monkeypatch.setattr(
        main,
        "evaluate_online_evidence_capability",
        lambda settings: online.OnlineEvidenceCapability(True),
    )
    monkeypatch.setattr(main, "run_guarded_online_evidence", lambda *a, **k: pytest.fail("called"))
    response = TestClient(main.app).post("/research/online-evidence", json={"question": "   "})
    assert response.status_code == 422
