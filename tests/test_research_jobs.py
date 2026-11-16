import json
import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from knowledge_engine_ai.copilot.research_report import ResearchReport
from knowledge_engine_ai.copilot.run_research_question import OnlineResearchQuestionResult

from knowledge_engine_web import research_jobs
from knowledge_engine_web.ai_guardrails import AIAdmissionError
from knowledge_engine_web.ai_orchestration import AIOrchestrationError
from knowledge_engine_web.config import Settings
from knowledge_engine_web.observability import logger as request_logger


def _online_report(**overrides: object) -> ResearchReport:
    fields: dict[str, object] = {
        "schema_version": 1,
        "question": "A research question",
        "bottom_line": "1 of 1 claims have supporting citations from 1 of 1 sources.",
        "conclusion_rows": (),
        "narrative_sections": (),
        "missing_evidence": (),
        "direct_evidence_summary": "Directness was not assessed.",
        "indirect_evidence_summary": "Directness was not assessed.",
        "provider_coverage_completeness": "complete",
        "degraded_providers": (),
        "provider_statuses": (),
        "indexed_before_run_evidence_ids": (),
        "acquired_during_run_evidence_ids": ("online-ev-1",),
        "limitations": ("Deterministic projection of Core claims; no LLM synthesis.",),
        "session_id": "search-run-1",
        "research_state": "partial_answer",
    }
    fields.update(overrides)
    return ResearchReport(**fields)  # type: ignore[arg-type]


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


def test_execute_research_job_persists_admission_rejection_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WEB-GQR-5 failure drill: a provider admission rejection (e.g. rate limit)
    raised inside the background worker must leave a durable, pollable
    `failed` job carrying the caller-safe `visitor_message`, not just a log
    line -- `/ask/session/{id}` reads this row directly."""

    database_path = tmp_path / "research_sessions.sqlite3"
    settings = Settings(session_db_path=str(database_path))
    research_jobs.create_research_job(
        str(database_path),
        session_id="session-admission-rejected",
        research_question_id="question-admission-rejected",
        question="A research question",
    )

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AIAdmissionError(
            "rate_limit_reached",
            "Research Copilot has received too many requests recently. Please wait and try again.",
        )

    monkeypatch.setattr(research_jobs, "run_guarded_ai_orchestration", _fail)

    research_jobs._execute_research_job(
        settings, "A research question", "client-key", "session-admission-rejected", None
    )

    job = research_jobs.read_research_job(str(database_path), "session-admission-rejected")
    assert job is not None
    assert job.status == "failed"
    assert job.terminal
    assert job.result is None
    assert job.visitor_error == (
        "Research Copilot has received too many requests recently. Please wait and try again."
    )
    assert not research_jobs.is_research_job_active("session-admission-rejected")


def test_execute_research_job_persists_orchestration_error_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WEB-GQR-5 failure drill: a Core/provider orchestration failure (e.g. all
    providers unavailable, Core retrieval failure) must also leave a durable
    `failed` job rather than hanging the page's poll loop forever."""

    database_path = tmp_path / "research_sessions.sqlite3"
    settings = Settings(session_db_path=str(database_path))
    research_jobs.create_research_job(
        str(database_path),
        session_id="session-orchestration-failed",
        research_question_id="question-orchestration-failed",
        question="A research question",
    )

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AIOrchestrationError("Research Copilot could not complete this request.")

    monkeypatch.setattr(research_jobs, "run_guarded_ai_orchestration", _fail)

    research_jobs._execute_research_job(
        settings, "A research question", "client-key", "session-orchestration-failed", None
    )

    job = research_jobs.read_research_job(str(database_path), "session-orchestration-failed")
    assert job is not None
    assert job.status == "failed"
    assert job.terminal
    assert job.result is None
    assert job.visitor_error == "Research Copilot could not complete this request."
    assert not research_jobs.is_research_job_active("session-orchestration-failed")


def test_execute_research_job_never_persists_a_raw_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unanticipated exception (local LLM crash, unhandled provider
    response, etc.) must still close the job as `failed` with the fixed,
    sanitized visitor message -- never the raw exception text, which could
    carry a path, provider response body, or secret."""

    database_path = tmp_path / "research_sessions.sqlite3"
    settings = Settings(session_db_path=str(database_path))
    research_jobs.create_research_job(
        str(database_path),
        session_id="session-unexpected-crash",
        research_question_id="question-unexpected-crash",
        question="A research question",
    )

    sensitive_detail = "Bearer sk-live-secret-token at /var/data/research_papers/private.json"

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(sensitive_detail)

    monkeypatch.setattr(research_jobs, "run_guarded_ai_orchestration", _fail)

    research_jobs._execute_research_job(
        settings, "A research question", "client-key", "session-unexpected-crash", None
    )

    job = research_jobs.read_research_job(str(database_path), "session-unexpected-crash")
    assert job is not None
    assert job.status == "failed"
    assert job.terminal
    assert job.result is None
    assert job.visitor_error == (
        "Research mode stopped unexpectedly. The durable session trace remains available."
    )
    assert sensitive_detail not in (job.visitor_error or "")
    assert not research_jobs.is_research_job_active("session-unexpected-crash")


def test_execute_research_job_falls_back_to_online_evidence_when_local_path_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner-approved 2026-10-25 architecture requires `/ask` to still answer when
    no local corpus/Ollama is configured, provided online evidence is enabled -- see
    `docs/research_report_v1.md`. A deployment whose local path already works must
    never reach this fallback (the other failure-drill tests above cover that)."""

    database_path = tmp_path / "research_sessions.sqlite3"
    settings = Settings(
        _env_file=None, session_db_path=str(database_path), online_evidence_enabled=True
    )
    research_jobs.create_research_job(
        str(database_path),
        session_id="session-online-fallback",
        research_question_id="question-online-fallback",
        question="A research question",
    )

    def _local_unavailable(*_args: object, **_kwargs: object) -> None:
        raise AIOrchestrationError("Research Copilot is unavailable on this deployment.")

    online_calls: list[dict[str, object]] = []

    def _online_answer(
        settings: object, question: str, **kwargs: object
    ) -> OnlineResearchQuestionResult:
        online_calls.append({"question": question, **kwargs})
        return OnlineResearchQuestionResult(
            question=question,
            report=_online_report(question=question),
            search_run_id="search-run-1",
            error_code=None,
        )

    monkeypatch.setattr(research_jobs, "run_guarded_ai_orchestration", _local_unavailable)
    monkeypatch.setattr(
        research_jobs,
        "evaluate_online_evidence_capability",
        lambda _settings: SimpleNamespace(available=True),
    )
    monkeypatch.setattr(research_jobs, "run_guarded_online_research_answer", _online_answer)

    research_jobs._execute_research_job(
        settings, "A research question", "client-key", "session-online-fallback", None
    )

    assert online_calls[0]["question"] == "A research question"
    assert online_calls[0]["client_key"] == "client-key"

    job = research_jobs.read_research_job(str(database_path), "session-online-fallback")
    assert job is not None
    assert job.status == "completed"
    assert job.terminal
    assert job.visitor_error is None
    assert job.result is not None
    assert job.result["evidence_source"] == "online_evidence_only"
    assert job.result["session_id"] == "session-online-fallback"
    assert job.result["research_state"] == "partial_answer"
    assert job.result["narrative_releaseable"] is False
    assert job.result["progress"] is None
    assert job.result["conversion_funnel"] is None
    assert job.result["close_gate"] is None
    assert job.result["research_report"]["available"] is True
    assert job.result["research_report"]["report"]["acquired_during_run_evidence_ids"] == [
        "online-ev-1"
    ]


def test_execute_research_job_online_fallback_is_skipped_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matches the existing failure-drill tests above: when online evidence is not
    enabled, a local-path failure must still surface the local path's own sanitized
    error, never attempting (or depending on) the online fallback."""

    database_path = tmp_path / "research_sessions.sqlite3"
    settings = Settings(session_db_path=str(database_path))
    research_jobs.create_research_job(
        str(database_path),
        session_id="session-no-fallback",
        research_question_id="question-no-fallback",
        question="A research question",
    )

    def _local_unavailable(*_args: object, **_kwargs: object) -> None:
        raise AIOrchestrationError("Research Copilot is unavailable on this deployment.")

    def _fail(*_args: object, **_kwargs: object) -> None:
        pytest.fail("the online fallback must not run when online evidence is disabled")

    monkeypatch.setattr(research_jobs, "run_guarded_ai_orchestration", _local_unavailable)
    monkeypatch.setattr(research_jobs, "run_guarded_online_research_answer", _fail)

    research_jobs._execute_research_job(
        settings, "A research question", "client-key", "session-no-fallback", None
    )

    job = research_jobs.read_research_job(str(database_path), "session-no-fallback")
    assert job is not None
    assert job.status == "failed"
    assert job.result is None
    assert job.visitor_error == "Research Copilot is unavailable on this deployment."


def test_online_presentation_payload_never_fabricates_local_session_fields() -> None:
    report = _online_report()
    payload = research_jobs._online_presentation_payload(
        "job-session-1",
        "A research question",
        OnlineResearchQuestionResult(
            question="A research question",
            report=report,
            search_run_id="search-run-1",
            error_code=None,
        ),
    )

    assert payload["session_id"] == "job-session-1"
    assert payload["evidence_source"] == "online_evidence_only"
    assert payload["online_search_run_id"] == "search-run-1"
    assert payload["narrative"] is None
    assert payload["narrative_releaseable"] is False
    assert payload["progress"] is None
    assert payload["conversion_funnel"] is None
    assert payload["close_gate"] is None
    assert payload["verification_clean"] is None
    assert payload["research_report"] == {
        "available": True,
        "error_code": None,
        "report": report.to_dict(),
    }
