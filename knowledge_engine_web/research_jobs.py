"""Durable Web job projection for asynchronous Research Copilot runs.

WEB-GQR-4 moves Research mode off the `/ask` request/response cycle. The AI
layer's ``research_sessions`` / ``research_events`` tables remain the source of
truth for scientific workflow state. This module adds only the Web-owned job
metadata needed to return a session ID immediately, poll progress, and retain a
safe final presentation payload across refreshes and Render redeploys.

The worker is deliberately process-local and single-threaded. It converts the
existing synchronous, bounded AI call into an asynchronous Web request without
pretending to be a resumable distributed workflow engine. If the process is
restarted while a job is running, the durable AI session/events remain, but the
in-flight Python call cannot be resumed; callers can detect that condition via
``is_research_job_active`` and present it honestly.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowledge_engine_web.ai_guardrails import AIAdmissionError
from knowledge_engine_web.ai_orchestration import (
    AIOrchestrationError,
    WebResearchResult,
    result_reached_execution_limit,
    run_guarded_ai_orchestration,
)
from knowledge_engine_web.config import Settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_research_jobs (
    session_id TEXT PRIMARY KEY,
    research_question_id TEXT NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    visitor_error TEXT,
    result_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_web_research_jobs_question
    ON web_research_jobs(research_question_id, created_at);
"""

_TERMINAL_JOB_STATUSES = frozenset({"completed", "failed"})
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ke-web-research")
_ACTIVE_SESSION_IDS: set[str] = set()
_ACTIVE_LOCK = threading.Lock()


class DuplicateResearchJobError(RuntimeError):
    """A Web research job already exists for the requested session ID."""


@dataclass(frozen=True)
class ResearchJobView:
    """One durable Web-facing job record."""

    session_id: str
    research_question_id: str
    question: str
    status: str
    created_at: str
    updated_at: str
    visitor_error: str | None
    result: dict[str, Any] | None

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_JOB_STATUSES


def create_research_job(
    session_db_path: str,
    *,
    session_id: str,
    research_question_id: str,
    question: str,
) -> ResearchJobView:
    """Persist a queued job before any background execution starts."""

    now = _utc_now()
    connection = _new_connection(session_db_path)
    try:
        _ensure_schema(connection)
        try:
            connection.execute(
                """
                INSERT INTO web_research_jobs (
                    session_id, research_question_id, question, status,
                    created_at, updated_at, visitor_error, result_json
                ) VALUES (?, ?, ?, 'queued', ?, ?, NULL, NULL)
                """,
                (session_id, research_question_id, question, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateResearchJobError(
                f"A research job already exists for session {session_id!r}."
            ) from exc
        connection.commit()
    finally:
        connection.close()

    return ResearchJobView(
        session_id=session_id,
        research_question_id=research_question_id,
        question=question,
        status="queued",
        created_at=now,
        updated_at=now,
        visitor_error=None,
        result=None,
    )


def read_research_job(session_db_path: str, session_id: str) -> ResearchJobView | None:
    """Read a Web job without creating or mutating the job table."""

    database_path = Path(session_db_path)
    if not database_path.is_file():
        return None
    try:
        connection = sqlite3.connect(
            f"file:{database_path}?mode=ro",
            uri=True,
            timeout=5.0,
        )
    except sqlite3.DatabaseError:
        return None
    connection.row_factory = sqlite3.Row
    try:
        try:
            row = connection.execute(
                "SELECT * FROM web_research_jobs WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        except sqlite3.DatabaseError:
            return None
    finally:
        connection.close()
    if row is None:
        return None
    result_json = row["result_json"]
    result = json.loads(str(result_json)) if result_json else None
    return ResearchJobView(
        session_id=str(row["session_id"]),
        research_question_id=str(row["research_question_id"]),
        question=str(row["question"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        visitor_error=str(row["visitor_error"]) if row["visitor_error"] is not None else None,
        result=result,
    )


def submit_research_job(
    settings: Settings,
    *,
    question: str,
    client_key: str,
    session_id: str,
    research_question_id: str,
) -> ResearchJobView:
    """Create a durable queued job and execute the existing AI path in the background."""

    job = create_research_job(
        settings.session_db_path,
        session_id=session_id,
        research_question_id=research_question_id,
        question=question,
    )
    with _ACTIVE_LOCK:
        _ACTIVE_SESSION_IDS.add(session_id)
    try:
        _EXECUTOR.submit(
            _execute_research_job,
            settings,
            question,
            client_key,
            session_id,
        )
    except RuntimeError:
        with _ACTIVE_LOCK:
            _ACTIVE_SESSION_IDS.discard(session_id)
        _mark_failed(
            settings.session_db_path,
            session_id,
            "Research mode could not start its background worker. Please try again.",
        )
        raise
    return job


def is_research_job_active(session_id: str) -> bool:
    """Return whether this process still owns the in-flight worker for ``session_id``."""

    with _ACTIVE_LOCK:
        return session_id in _ACTIVE_SESSION_IDS


def _execute_research_job(
    settings: Settings,
    question: str,
    client_key: str,
    session_id: str,
) -> None:
    _mark_running(settings.session_db_path, session_id)
    try:
        result = run_guarded_ai_orchestration(
            settings,
            question,
            client_key=client_key,
            session_id=session_id,
        )
        _mark_completed(settings.session_db_path, session_id, _presentation_payload(result))
    except AIAdmissionError as exc:
        _mark_failed(settings.session_db_path, session_id, exc.visitor_message)
    except AIOrchestrationError as exc:
        _mark_failed(settings.session_db_path, session_id, str(exc))
    except Exception:
        # Never persist a raw exception, provider response, path, or secret into
        # a visitor-readable job record.
        _mark_failed(
            settings.session_db_path,
            session_id,
            "Research mode stopped unexpectedly. The durable session trace remains available.",
        )
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_SESSION_IDS.discard(session_id)


def _presentation_payload(result: WebResearchResult) -> dict[str, Any]:
    """Persist only safe, structured presentation facts from one completed run."""

    research = result.research
    progress = research.progress_report
    funnel = research.conversion_funnel_report
    verification = research.verification
    return {
        "session_id": result.session_id,
        "question": result.question,
        "research_state": result.research_state.state.value,
        "research_state_reason": result.research_state.reason,
        "narrative_releaseable": result.narrative_releaseable,
        "narrative": result.narrative if result.narrative_releaseable else None,
        "synthesis_failed": result.synthesis_error is not None,
        "execution_limit_reached": result_reached_execution_limit(result),
        "close_gate": result.close_result.status.value,
        "verification_clean": verification.is_clean if verification is not None else None,
        "progress": progress.to_dict() if progress is not None else None,
        "conversion_funnel": funnel.to_dict() if funnel is not None else None,
    }


def _mark_running(session_db_path: str, session_id: str) -> None:
    _update_job(session_db_path, session_id, status="running")


def _mark_completed(session_db_path: str, session_id: str, result: dict[str, Any]) -> None:
    _update_job(
        session_db_path,
        session_id,
        status="completed",
        visitor_error=None,
        result_json=json.dumps(result, sort_keys=True),
    )


def _mark_failed(session_db_path: str, session_id: str, visitor_error: str) -> None:
    _update_job(
        session_db_path,
        session_id,
        status="failed",
        visitor_error=visitor_error,
        result_json=None,
    )


def _update_job(
    session_db_path: str,
    session_id: str,
    *,
    status: str,
    visitor_error: str | None = None,
    result_json: str | None = None,
) -> None:
    connection = _new_connection(session_db_path)
    try:
        _ensure_schema(connection)
        connection.execute(
            """
            UPDATE web_research_jobs
            SET status = ?, updated_at = ?, visitor_error = ?, result_json = ?
            WHERE session_id = ?
            """,
            (status, _utc_now(), visitor_error, result_json, session_id),
        )
        connection.commit()
    finally:
        connection.close()


def _new_connection(session_db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(session_db_path, timeout=5.0)
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


# Narrow test seam for deterministic job-state tests without a real provider run.
ResearchRunner = Callable[..., WebResearchResult]


__all__ = [
    "DuplicateResearchJobError",
    "ResearchJobView",
    "create_research_job",
    "is_research_job_active",
    "read_research_job",
    "submit_research_job",
]
