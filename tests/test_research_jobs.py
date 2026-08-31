import json
import sqlite3
from pathlib import Path

import pytest

from knowledge_engine_web import research_jobs


def test_job_lifecycle_is_durable_across_connections(tmp_path: Path) -> None:
    database_path = tmp_path / "research_sessions.sqlite3"

    queued = research_jobs.create_research_job(
        str(database_path),
        session_id="session-1",
        research_question_id="question-1",
        question="Does creatine improve maximal strength?",
    )

    assert queued.status == "queued"
    assert not queued.terminal

    research_jobs._mark_running(str(database_path), "session-1")
    running = research_jobs.read_research_job(str(database_path), "session-1")
    assert running is not None
    assert running.status == "running"
    assert not running.terminal

    payload = {
        "research_state": "researched_answer",
        "narrative_releaseable": True,
        "narrative": "A source-grounded answer.",
        "progress": {"progress_stage": "final_answer", "final": True},
    }
    research_jobs._mark_completed(str(database_path), "session-1", payload)

    # Read through a fresh connection, proving this is persisted state rather
    # than an in-memory executor result.
    completed = research_jobs.read_research_job(str(database_path), "session-1")
    assert completed is not None
    assert completed.status == "completed"
    assert completed.terminal
    assert completed.result == payload
    assert completed.visitor_error is None


def test_failed_job_persists_only_sanitized_visitor_message(tmp_path: Path) -> None:
    database_path = tmp_path / "research_sessions.sqlite3"
    research_jobs.create_research_job(
        str(database_path),
        session_id="session-failed",
        research_question_id="question-failed",
        question="A research question",
    )

    message = "Research mode could not complete this request."
    research_jobs._mark_failed(str(database_path), "session-failed", message)

    failed = research_jobs.read_research_job(str(database_path), "session-failed")
    assert failed is not None
    assert failed.status == "failed"
    assert failed.terminal
    assert failed.visitor_error == message
    assert failed.result is None


def test_duplicate_session_id_is_rejected(tmp_path: Path) -> None:
    database_path = tmp_path / "research_sessions.sqlite3"
    kwargs = {
        "session_id": "session-duplicate",
        "research_question_id": "question-duplicate",
        "question": "A research question",
    }
    research_jobs.create_research_job(str(database_path), **kwargs)

    with pytest.raises(research_jobs.DuplicateResearchJobError):
        research_jobs.create_research_job(str(database_path), **kwargs)


def test_job_table_coexists_with_ai_session_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "research_sessions.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE research_sessions (session_id TEXT PRIMARY KEY, status TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO research_sessions (session_id, status) VALUES ('ai-session', 'running')"
        )
        connection.commit()

    research_jobs.create_research_job(
        str(database_path),
        session_id="web-session",
        research_question_id="question-1",
        question="A research question",
    )

    with sqlite3.connect(database_path) as connection:
        ai_row = connection.execute(
            "SELECT session_id, status FROM research_sessions WHERE session_id = 'ai-session'"
        ).fetchone()
        web_row = connection.execute(
            "SELECT session_id, status FROM web_research_jobs WHERE session_id = 'web-session'"
        ).fetchone()

    assert ai_row == ("ai-session", "running")
    assert web_row == ("web-session", "queued")


def test_result_json_is_valid_json_in_storage(tmp_path: Path) -> None:
    database_path = tmp_path / "research_sessions.sqlite3"
    research_jobs.create_research_job(
        str(database_path),
        session_id="session-json",
        research_question_id="question-json",
        question="A research question",
    )
    research_jobs._mark_completed(
        str(database_path),
        "session-json",
        {"narrative": "Grounded", "citations": ["ev-1"]},
    )

    with sqlite3.connect(database_path) as connection:
        raw = connection.execute(
            "SELECT result_json FROM web_research_jobs WHERE session_id = 'session-json'"
        ).fetchone()

    assert raw is not None
    assert json.loads(raw[0]) == {"citations": ["ev-1"], "narrative": "Grounded"}
