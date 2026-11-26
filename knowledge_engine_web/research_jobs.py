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
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowledge_engine_ai.copilot.research_report_integration import ResearchReportBuildResult
from knowledge_engine_ai.copilot.run_research_question import OnlineResearchQuestionResult
from knowledge_engine_ai.copilot.stage_updates import ResearchStageUpdate

from knowledge_engine_web.ai_guardrails import AIAdmissionError
from knowledge_engine_web.ai_orchestration import (
    AIOrchestrationError,
    WebResearchResult,
    result_reached_execution_limit,
    run_guarded_ai_orchestration,
    run_guarded_online_research_answer,
)
from knowledge_engine_web.config import Settings
from knowledge_engine_web.observability import logger as request_logger
from knowledge_engine_web.online_evidence_orchestration import evaluate_online_evidence_capability
from knowledge_engine_web.research_coverage_presentation import build_research_coverage_panel

_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_research_jobs (
    session_id TEXT PRIMARY KEY,
    research_question_id TEXT NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    visitor_error TEXT,
    result_json TEXT,
    request_id TEXT,
    current_stage_json TEXT
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
    request_id: str | None = None
    # Latest in-flight stage AI announced (`stage`, `sequence`, `elapsed_ms`, `detail`,
    # `recorded_at`); ``None`` before the first announcement or on a pre-migration row.
    current_stage: dict[str, Any] | None = None

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_JOB_STATUSES


def create_research_job(
    session_db_path: str,
    *,
    session_id: str,
    research_question_id: str,
    question: str,
    request_id: str | None = None,
) -> ResearchJobView:
    """Persist a queued job before any background execution starts.

    ``request_id`` carries the inbound HTTP correlation ID
    (`RequestObservabilityMiddleware`'s `X-Request-ID`, when the caller runs
    behind it) so an operator can join "which request started this Research
    session" across the generic request log and this durable job -- see
    `docs/INDUSTRY_REALITY_CHECK.md`'s observability gap #7.
    """

    now = _utc_now()
    connection = _new_connection(session_db_path)
    try:
        _ensure_schema(connection)
        try:
            connection.execute(
                """
                INSERT INTO web_research_jobs (
                    session_id, research_question_id, question, status,
                    created_at, updated_at, visitor_error, result_json, request_id
                ) VALUES (?, ?, ?, 'queued', ?, ?, NULL, NULL, ?)
                """,
                (session_id, research_question_id, question, now, now, request_id),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateResearchJobError(
                f"A research job already exists for session {session_id!r}."
            ) from exc
        connection.commit()
    finally:
        connection.close()

    request_logger.info(
        "request_id=%s research_session_id=%s event=research_job_created",
        request_id,
        session_id,
    )

    return ResearchJobView(
        session_id=session_id,
        research_question_id=research_question_id,
        question=question,
        status="queued",
        created_at=now,
        updated_at=now,
        visitor_error=None,
        result=None,
        request_id=request_id,
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
    # `request_id` was added after this table's original schema; a database
    # file created before that migration ran (and never since written to,
    # which is the only thing that triggers `_ensure_schema`) may still lack
    # the column, so read it defensively rather than assuming it is present.
    row_keys = row.keys()
    request_id = row["request_id"] if "request_id" in row_keys else None
    current_stage = _parse_stage(
        row["current_stage_json"] if "current_stage_json" in row_keys else None
    )
    return ResearchJobView(
        session_id=str(row["session_id"]),
        research_question_id=str(row["research_question_id"]),
        question=str(row["question"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        visitor_error=str(row["visitor_error"]) if row["visitor_error"] is not None else None,
        result=result,
        request_id=str(request_id) if request_id is not None else None,
        current_stage=current_stage,
    )


def submit_research_job(
    settings: Settings,
    *,
    question: str,
    client_key: str,
    session_id: str,
    research_question_id: str,
    request_id: str | None = None,
) -> ResearchJobView:
    """Create a durable queued job and execute the existing AI path in the background."""

    job = create_research_job(
        settings.session_db_path,
        session_id=session_id,
        research_question_id=research_question_id,
        question=question,
        request_id=request_id,
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
            request_id,
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
    request_id: str | None = None,
) -> None:
    _mark_running(settings.session_db_path, session_id)
    outcome = "failed"
    try:
        result = run_guarded_ai_orchestration(
            settings,
            question,
            client_key=client_key,
            session_id=session_id,
            on_stage=lambda update: _record_stage(settings.session_db_path, session_id, update),
        )
        _mark_completed(settings.session_db_path, session_id, _presentation_payload(result))
        outcome = "completed"
    except AIAdmissionError as exc:
        _mark_failed(settings.session_db_path, session_id, exc.visitor_message)
    except AIOrchestrationError as local_error:
        online_payload = _try_online_fallback(settings, question, client_key, session_id)
        if online_payload is not None:
            _mark_completed(settings.session_db_path, session_id, online_payload)
            outcome = "completed"
        else:
            _mark_failed(settings.session_db_path, session_id, str(local_error))
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
        request_logger.info(
            "request_id=%s research_session_id=%s event=research_job_%s",
            request_id,
            session_id,
            outcome,
        )


def _coverage_panel_payload(result: WebResearchResult) -> dict[str, Any] | None:
    """Serialize WEB-GQR-2's coverage panel for the durable async job payload.

    `build_research_coverage_panel` is the one place that already reshapes
    `DiscoveryAugmentationResult`/`GroundedCompletionResult` for rendering
    (see `research_coverage_presentation.py`); the synchronous `/ask` path
    passes the same two objects straight to it. Without this, a completed
    async job's persisted payload never carried `federated_discovery_error`,
    per-provider outcome/reason, acquisition-route errors/skipped reasons, or
    `extraction_error`/`reretrieval_error` -- a provider rate limit, an
    all-providers-unavailable discovery failure, a license-blocked
    acquisition route, or an extraction that produced no grounded evidence
    were silently dropped for every visitor on the async (default-deployment)
    path even though the synchronous coverage panel already rendered them.
    `asdict` is safe here: every field on `ResearchCoveragePanel` and its two
    nested row types is a `str`/`bool`/`int`/`None`/tuple of those, already
    JSON-serializable.
    """

    panel = build_research_coverage_panel(result.discovery, result.grounded_completion)
    return asdict(panel) if panel is not None else None


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
        "research_report": result.research_report.to_dict(),
        "synthesis_failed": result.synthesis_error is not None,
        "execution_limit_reached": result_reached_execution_limit(result),
        "close_gate": result.close_result.status.value,
        "verification_clean": verification.is_clean if verification is not None else None,
        "progress": progress.to_dict() if progress is not None else None,
        "conversion_funnel": funnel.to_dict() if funnel is not None else None,
        "coverage_panel": _coverage_panel_payload(result),
        "evidence_source": "local_corpus",
    }


def _try_online_fallback(
    settings: Settings,
    question: str,
    client_key: str,
    session_id: str,
) -> dict[str, Any] | None:
    """Attempt the owner-approved 2026-10-25 online-evidence-only `/ask` path.

    Only reached after the complete local-corpus/Ollama path has already raised
    `AIOrchestrationError` (see `_execute_research_job`): a deployment whose local path
    works never reaches this function, so its behavior is unchanged. Returns `None`
    rather than raising for every unavailable or failed outcome, so the caller always
    falls back to the local path's own already-sanitized error message instead of a
    second, possibly conflicting one.
    """

    if not evaluate_online_evidence_capability(settings).available:
        return None
    try:
        online_result = run_guarded_online_research_answer(
            settings, question, client_key=client_key
        )
        return _online_presentation_payload(session_id, question, online_result)
    except Exception:
        return None


def _online_presentation_payload(
    session_id: str,
    question: str,
    result: OnlineResearchQuestionResult,
) -> dict[str, Any]:
    """Persist the online-evidence-only presentation payload.

    `run_guarded_online_research_answer` raises `AIOrchestrationError` for every
    outcome where `result.report` would be `None` (invalid request, Core bridge
    failure, or rejected evidence), so `_try_online_fallback` never calls this with
    one. Unlike `_presentation_payload`, this path never runs AI's durable session
    store, Ollama, synthesis, verification, or close gate, so those fields are `None`
    here rather than fabricated placeholder values; `research_report` reuses the same
    `ResearchReportBuildResult` shape the local path produces, so existing Layer 1/
    Layer 2 rendering and Mobile Product Reality evidence counting need no changes to
    handle it.
    """

    report = result.report
    assert report is not None
    return {
        "session_id": session_id,
        "question": question,
        "research_state": report.research_state,
        "research_state_reason": (
            "Answered from on-demand online evidence retrieval; no local indexed "
            "corpus, Ollama, or synthesis model was used on this deployment."
        ),
        "narrative_releaseable": False,
        "narrative": None,
        "research_report": ResearchReportBuildResult(report=report, error_code=None).to_dict(),
        "synthesis_failed": False,
        "execution_limit_reached": False,
        "close_gate": None,
        "verification_clean": None,
        "progress": None,
        "conversion_funnel": None,
        "coverage_panel": None,
        "evidence_source": "online_evidence_only",
        "online_search_run_id": result.search_run_id,
    }


_MAX_STAGE_DETAIL_CHARS = 200


def _parse_stage(raw: object) -> dict[str, Any] | None:
    """Defensively decode a stored stage; anything malformed reads as no stage."""

    if not isinstance(raw, str) or not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _record_stage(session_db_path: str, session_id: str, update: ResearchStageUpdate) -> None:
    """Persist the stage AI just entered so pollers see what is running *now*.

    Observation only and best effort: it writes only while the job is still queued or
    running (a late update can never overwrite a terminal job), stores the stage name,
    sequence, elapsed time and a length-capped detail (counts/trigger text from AI, never
    a path or secret), and swallows storage errors so a failed write cannot affect the
    research itself.
    """

    payload = {
        "stage": update.stage.value,
        "sequence": update.sequence,
        "elapsed_ms": update.elapsed_ms,
        "detail": update.detail[:_MAX_STAGE_DETAIL_CHARS],
        "recorded_at": _utc_now(),
    }
    try:
        connection = _new_connection(session_db_path)
        try:
            _ensure_schema(connection)
            connection.execute(
                """
                UPDATE web_research_jobs
                SET current_stage_json = ?, updated_at = ?
                WHERE session_id = ? AND status IN ('queued', 'running')
                """,
                (json.dumps(payload, sort_keys=True), payload["recorded_at"], session_id),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        return


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
    # `request_id` was added to `web_research_jobs` after this table shipped.
    # `CREATE TABLE IF NOT EXISTS` above only creates the column for a brand
    # new database; a table an earlier deploy already created keeps its old
    # shape until migrated here. Idempotent and safe to run on every write.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(web_research_jobs)")}
    if "request_id" not in columns:
        connection.execute("ALTER TABLE web_research_jobs ADD COLUMN request_id TEXT")
    if "current_stage_json" not in columns:
        connection.execute("ALTER TABLE web_research_jobs ADD COLUMN current_stage_json TEXT")


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
