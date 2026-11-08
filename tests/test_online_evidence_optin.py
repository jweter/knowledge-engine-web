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
    assert (
        body["source_status_summary"]["scope"]
        == "returned_sources_only_not_exhaustive_provider_coverage"
    )
    assert body["source_status_summary"]["source_count"] == 1
    assert body["source_status_summary"]["status_counts"] == {
        "retrieved": 0,
        "unavailable": 1,
        "not_permitted": 0,
        "failed": 0,
    }
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


def test_source_status_summary_preserves_mixed_provider_failures() -> None:
    evidence = ContentCheckedOnlineEvidence(
        question="What is known?",
        sources=(
            OnlineSource(
                "a",
                "https://example.org/a",
                "pubmed",
                "2026-11-02T12:00:00+00:00",
                "retrieved",
                "a" * 64,
                None,
                "A",
            ),
            OnlineSource(
                "b",
                "https://example.org/b",
                "pubmed",
                "2026-11-02T12:00:00+00:00",
                "unavailable",
                None,
                "offline",
                None,
            ),
            OnlineSource(
                "c",
                "https://example.org/c",
                "crossref",
                "2026-11-02T12:00:00+00:00",
                "failed",
                None,
                "timeout",
                None,
            ),
            OnlineSource(
                "d",
                "https://example.org/d",
                "openalex",
                "2026-11-02T12:00:00+00:00",
                "not_permitted",
                None,
                "policy",
                None,
            ),
        ),
        excerpts=(),
        claims=(),
    )
    summary = online.summarize_returned_online_sources(
        OnlineResearchEvidenceResult(evidence=evidence, search_run_id="run")
    )
    assert summary["source_count"] == 4
    assert summary["status_counts"] == {
        "retrieved": 1,
        "unavailable": 1,
        "not_permitted": 1,
        "failed": 1,
    }
    assert [item["provider"] for item in summary["providers"]] == [
        "crossref",
        "openalex",
        "pubmed",
    ]
    assert summary["providers"][2]["status_counts"]["unavailable"] == 1
    assert summary["providers"][2]["status_counts"]["retrieved"] == 1


def test_source_status_summary_does_not_invent_coverage_for_empty_result() -> None:
    evidence = ContentCheckedOnlineEvidence(
        question="What is known?",
        sources=(),
        excerpts=(),
        claims=(),
    )
    summary = online.summarize_returned_online_sources(
        OnlineResearchEvidenceResult(evidence=evidence, search_run_id="run")
    )
    assert summary["source_count"] == 0
    assert summary["providers"] == []
    assert all(value == 0 for value in summary["status_counts"].values())


def test_page_disabled_by_default_shows_unavailable_without_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "Settings", lambda: _settings())
    response = TestClient(main.app).get("/research/online")
    assert response.status_code == 200
    assert "not enabled on this deployment" in response.text
    assert "online-evidence-form" not in response.text


def test_page_enabled_labels_retrieval_only_and_loads_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "C:/fake/ke.exe")
    monkeypatch.setattr(main, "Settings", lambda: _settings(online_evidence_enabled=True))
    client = TestClient(main.app)
    response = client.get("/research/online")
    assert response.status_code == 200
    assert 'id="online-evidence-form"' in response.text
    assert "retrieval only" in response.text
    assert "/static/online_evidence.js" in response.text
    script = client.get("/static/online_evidence.js")
    assert script.status_code == 200
    # Rendered via textContent only; never innerHTML from provider-supplied data.
    assert "innerHTML" not in script.text


def test_route_includes_deterministic_report_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "Settings", lambda: _settings(online_evidence_enabled=True))
    monkeypatch.setattr(
        main,
        "evaluate_online_evidence_capability",
        lambda settings: online.OnlineEvidenceCapability(True),
    )
    monkeypatch.setattr(main, "run_guarded_online_evidence", lambda *a, **k: _result())
    client = TestClient(main.app)
    body = client.post("/research/online-evidence", json={"question": "What is known?"}).json()
    assert body["research_report_complete"] is False
    assert body["report_kind"] == "deterministic_projection_no_synthesis"
    report = body["report"]
    assert report["session_id"] == "run-verified"
    assert report["research_state"] == "insufficient_evidence"
    assert report["conclusion_rows"] == []
    assert any("src-unavailable unavailable" in m for m in report["missing_evidence"])
    assert "no LLM synthesis" in " ".join(report["limitations"])


def test_route_reports_measured_stages_without_inventing_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "Settings", lambda: _settings(online_evidence_enabled=True))
    monkeypatch.setattr(
        main,
        "evaluate_online_evidence_capability",
        lambda settings: online.OnlineEvidenceCapability(True),
    )
    monkeypatch.setattr(main, "run_guarded_online_evidence", lambda *a, **k: _result())
    body = (
        TestClient(main.app)
        .post("/research/online-evidence", json={"question": "What is known?"})
        .json()
    )
    assert [s["stage"] for s in body["stages"]] == [
        "discovery_retrieval_validation",
        "deterministic_analysis",
    ]
    assert all(s["status"] == "completed" and s["elapsed_ms"] >= 0 for s in body["stages"])


def test_route_marks_analysis_failed_closed_when_projection_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "Settings", lambda: _settings(online_evidence_enabled=True))
    monkeypatch.setattr(
        main,
        "evaluate_online_evidence_capability",
        lambda settings: online.OnlineEvidenceCapability(True),
    )
    monkeypatch.setattr(main, "run_guarded_online_evidence", lambda *a, **k: _result())

    def reject(*a: object, **k: object) -> object:
        raise ValueError("bad")

    monkeypatch.setattr(main, "build_online_research_report", reject)
    body = (
        TestClient(main.app)
        .post("/research/online-evidence", json={"question": "What is known?"})
        .json()
    )
    assert body["report"] is None
    assert body["stages"][1]["status"] == "failed_closed"
    assert body["evidence"]["sources"]


def test_page_has_run_stages_section(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "evaluate_online_evidence_capability",
        lambda settings: online.OnlineEvidenceCapability(True),
    )
    html = TestClient(main.app).get("/research/online").text
    assert 'id="online-evidence-stages"' in html
    assert "discarded when it ends" in html
