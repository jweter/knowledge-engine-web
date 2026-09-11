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


def _complete_job_with_evidence(session_db: Path, session_id: str, question: str) -> None:
    research_jobs.create_research_job(
        str(session_db),
        session_id=session_id,
        research_question_id="monster-question",
        question=question,
    )
    research_jobs._mark_completed(
        str(session_db),
        session_id,
        {
            "research_state": "researched_answer",
            "narrative_releaseable": True,
            "narrative": "Grounded answer",
            "research_report": {
                "available": True,
                "error_code": None,
                "report": {
                    "indexed_before_run_evidence_ids": ["ev-1"],
                    "acquired_during_run_evidence_ids": ["ev-2"],
                },
            },
        },
    )


def test_mobile_review_status_reports_automated_evidence_before_any_human_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_db = _enable_async_research(tmp_path, monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "deployed-sha")
    session_id = "session-mobile-1"
    _complete_job_with_evidence(session_db, session_id, "Does Monster Energy raise blood pressure?")

    response = TestClient(app).get(f"/ask/session/{session_id}/mobile-review")

    assert response.status_code == 200
    payload = response.json()
    assert payload["web_commit"] == "deployed-sha"
    assert payload["response_state"] == "ANSWERED"
    assert payload["evidence_count"] == 2
    assert payload["provenance_traceable"] is True
    assert payload["automated_evidence_state"] == "EVIDENCE_PRESENT"
    assert payload["review"] == "UNREVIEWED"
    assert payload["remaining_acceptance_debt"] == ["human_mobile_safari_review"]
    assert "notes" not in payload


def test_mobile_review_status_404_for_unknown_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_async_research(tmp_path, monkeypatch)

    response = TestClient(app).get("/ask/session/does-not-exist/mobile-review")

    assert response.status_code == 404


def test_posting_a_mobile_review_records_and_returns_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_db = _enable_async_research(tmp_path, monkeypatch)
    session_id = "session-mobile-2"
    _complete_job_with_evidence(session_db, session_id, "Does Monster Energy raise blood pressure?")

    response = TestClient(app).post(
        f"/ask/session/{session_id}/mobile-review",
        json={"review": "PASS", "notes": "Confirmed on iPhone Safari."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review"] == "PASS"
    assert payload["remaining_acceptance_debt"] == []
    assert "notes" not in payload

    follow_up = TestClient(app).get(f"/ask/session/{session_id}/mobile-review")
    assert follow_up.json()["review"] == "PASS"


def test_posting_a_mobile_review_before_the_job_is_terminal_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_db = _enable_async_research(tmp_path, monkeypatch)
    session_id = "session-mobile-running"
    research_jobs.create_research_job(
        str(session_db),
        session_id=session_id,
        research_question_id="monster-question",
        question="Does Monster Energy raise blood pressure?",
    )

    response = TestClient(app).post(
        f"/ask/session/{session_id}/mobile-review",
        json={"review": "PASS"},
    )

    assert response.status_code == 409


def test_posting_an_invalid_review_value_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_db = _enable_async_research(tmp_path, monkeypatch)
    session_id = "session-mobile-3"
    _complete_job_with_evidence(session_db, session_id, "Does Monster Energy raise blood pressure?")

    response = TestClient(app).post(
        f"/ask/session/{session_id}/mobile-review",
        json={"review": "MAYBE"},
    )

    assert response.status_code == 400
