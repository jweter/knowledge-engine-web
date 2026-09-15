import json
import logging
import sqlite3
from pathlib import Path

import pytest

from knowledge_engine_web import research_jobs
from knowledge_engine_web.ai_guardrails import AIAdmissionError
from knowledge_engine_web.config import Settings
from knowledge_engine_web.observability import logger as request_logger


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


def test_request_id_round_trips_through_create_and_read(tmp_path: Path) -> None:
    """The inbound `X-Request-ID` a job was created under is durable and
    readable, so an operator can join the generic request log
    (`RequestObservabilityMiddleware`) with this Research session -- see
    `docs/INDUSTRY_REALITY_CHECK.md`'s observability gap #7.
    """
    database_path = tmp_path / "research_sessions.sqlite3"

    created = research_jobs.create_research_job(
        str(database_path),
        session_id="session-correlated",
        research_question_id="question-correlated",
        question="A research question",
        request_id="caller-request-id-1",
    )
    assert created.request_id == "caller-request-id-1"

    read_back = research_jobs.read_research_job(str(database_path), "session-correlated")
    assert read_back is not None
    assert read_back.request_id == "caller-request-id-1"


def test_omitted_request_id_defaults_to_none(tmp_path: Path) -> None:
    database_path = tmp_path / "research_sessions.sqlite3"

    created = research_jobs.create_research_job(
        str(database_path),
        session_id="session-uncorrelated",
        research_question_id="question-uncorrelated",
        question="A research question",
    )
    assert created.request_id is None

    read_back = research_jobs.read_research_job(str(database_path), "session-uncorrelated")
    assert read_back is not None
    assert read_back.request_id is None


def test_a_pre_existing_database_without_request_id_is_migrated_on_write(tmp_path: Path) -> None:
    """A database created before `request_id` existed lacks the column
    entirely (SQLite's `CREATE TABLE IF NOT EXISTS` never widens an existing
    table). The next write must add it transparently rather than erroring or
    silently dropping the new field.
    """
    database_path = tmp_path / "research_sessions.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE web_research_jobs (
                session_id TEXT PRIMARY KEY,
                research_question_id TEXT NOT NULL,
                question TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                visitor_error TEXT,
                result_json TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO web_research_jobs (
                session_id, research_question_id, question, status,
                created_at, updated_at, visitor_error, result_json
            ) VALUES ('legacy-session', 'legacy-question', 'A question', 'completed',
                      '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', NULL, NULL)
            """
        )
        connection.commit()

    # A pre-migration read must not blow up on the missing column.
    legacy = research_jobs.read_research_job(str(database_path), "legacy-session")
    assert legacy is not None
    assert legacy.request_id is None

    research_jobs.create_research_job(
        str(database_path),
        session_id="session-after-migration",
        research_question_id="question-after-migration",
        question="A research question",
        request_id="caller-request-id-2",
    )

    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(web_research_jobs)")}
    assert "request_id" in columns

    migrated_new_row = research_jobs.read_research_job(
        str(database_path), "session-after-migration"
    )
    assert migrated_new_row is not None
    assert migrated_new_row.request_id == "caller-request-id-2"

    still_readable_legacy_row = research_jobs.read_research_job(
        str(database_path), "legacy-session"
    )
    assert still_readable_legacy_row is not None
    assert still_readable_legacy_row.status == "completed"
    assert still_readable_legacy_row.request_id is None


def test_job_creation_logs_a_line_correlating_request_and_session_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    database_path = tmp_path / "research_sessions.sqlite3"

    with caplog.at_level(logging.INFO, logger=request_logger.name):
        research_jobs.create_research_job(
            str(database_path),
            session_id="session-logged",
            research_question_id="question-logged",
            question="A research question",
            request_id="caller-request-id-3",
        )

    messages = [record.message for record in caplog.records]
    assert any(
        "request_id=caller-request-id-3" in message
        and "research_session_id=session-logged" in message
        and "event=research_job_created" in message
        for message in messages
    )


def test_job_execution_logs_a_terminal_outcome_correlated_with_request_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    database_path = tmp_path / "research_sessions.sqlite3"
    settings = Settings(session_db_path=str(database_path))

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AIAdmissionError("rejected", "Research mode is unavailable right now.")

    monkeypatch.setattr(research_jobs, "run_guarded_ai_orchestration", _fail)

    with caplog.at_level(logging.INFO, logger=request_logger.name):
        research_jobs._execute_research_job(
            settings,
            "A research question",
            "client-key",
            "session-executed",
            "caller-request-id-4",
        )

    messages = [record.message for record in caplog.records]
    assert any(
        "request_id=caller-request-id-4" in message
        and "research_session_id=session-executed" in message
        and "event=research_job_failed" in message
        for message in messages
    )
