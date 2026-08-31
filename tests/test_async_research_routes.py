from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_engine_web import main, research_jobs
from knowledge_engine_web.ai_orchestration import AICapability
from knowledge_engine_web.main import app


def _enable_async_research(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    session_db = tmp_path / "research_sessions.sqlite3"
    monkeypatch.setenv("KE_WEB_DATABASE_URL", f"sqlite:///{tmp_path / 'knowledge.sqlite3'}")
    monkeypatch.setenv("KE_WEB_SESSION_DB_PATH", str(session_db))
    monkeypatch.setenv("KE_WEB_ASYNC_RESEARCH_ENABLED", "true")
    monkeypatch.setattr(
        main,
        "evaluate_ai_capability",
        lambda _settings: AICapability(available=True, session_storage_mode="local"),
    )
    monkeypatch.setattr(main, "answer_retrieval", lambda *_args, **_kwargs: [])
    return session_db


def test_async_ask_returns_immediately_with_pollable_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_db = _enable_async_research(tmp_path, monkeypatch)

    def fake_submit(settings: object, **kwargs: str) -> research_jobs.ResearchJobView:
        return research_jobs.create_research_job(
            str(session_db),
            session_id=kwargs["session_id"],
            research_question_id=kwargs["research_question_id"],
            question=kwargs["question"],
        )

    monkeypatch.setattr(main, "submit_research_job", fake_submit)

    response = TestClient(app).get(
        "/ask",
        params={"q": "Does Monster Energy raise blood pressure?", "synthesize": "1"},
    )

    assert response.status_code == 200
    assert "Research session running" in response.text
    match = re.search(r'data-session-id="([^"]+)"', response.text)
    assert match is not None
    session_id = match.group(1)

    status = TestClient(app).get(f"/ask/session/{session_id}")
    assert status.status_code == 200
    payload = status.json()
    assert payload["session_id"] == session_id
    assert payload["job_status"] == "queued"
    assert payload["terminal"] is False
    assert payload["result"] is None


def test_async_status_returns_durable_final_presentation_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_db = _enable_async_research(tmp_path, monkeypatch)
    session_id = "session-complete"
    research_jobs.create_research_job(
        str(session_db),
        session_id=session_id,
        research_question_id="monster-question",
        question="Does Monster Energy raise blood pressure?",
    )
    research_jobs._mark_completed(
        str(session_db),
        session_id,
        {
            "research_state": "researched_answer",
            "narrative_releaseable": True,
            "narrative": "Grounded answer",
            "progress": {
                "progress_stage": "final_answer",
                "final": True,
                "elapsed_ms": 1234,
                "indexed_evidence_record_ids": [],
                "newly_acquired_evidence_record_ids": ["ev-new"],
                "provider_degraded": False,
                "provider_statuses": [],
                "citations": [],
                "limitations": [],
            },
            "conversion_funnel": {
                "time_to_first_grounded_information_ms": 900,
                "time_to_final_report_ms": 1234,
            },
        },
    )

    response = TestClient(app).get(f"/ask/session/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["terminal"] is True
    assert payload["job_status"] == "completed"
    assert payload["result"]["narrative"] == "Grounded answer"
    assert payload["result"]["progress"]["newly_acquired_evidence_record_ids"] == ["ev-new"]


def test_refreshing_known_async_session_does_not_start_a_second_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_db = _enable_async_research(tmp_path, monkeypatch)
    session_id = "session-refresh"
    question = "Does Monster Energy raise blood pressure?"
    research_jobs.create_research_job(
        str(session_db),
        session_id=session_id,
        research_question_id="monster-question",
        question=question,
    )

    def fail_submit(*_args: object, **_kwargs: object) -> research_jobs.ResearchJobView:
        raise AssertionError("refresh must not submit a second research job")

    monkeypatch.setattr(main, "submit_research_job", fail_submit)

    response = TestClient(app).get(
        "/ask",
        params={"q": question, "synthesize": "1", "session_id": session_id},
    )

    assert response.status_code == 200
    assert session_id in response.text
    assert "Research session running" in response.text
