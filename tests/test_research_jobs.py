import json
import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from knowledge_engine_ai.copilot.discovery_policy import DiscoveryAugmentationResult
from knowledge_engine_ai.copilot.grounded_completion import (
    AcquisitionRouteResult,
    GroundedCompletionResult,
)
from knowledge_engine_ai.copilot.progress_report import ResearchProgressStage
from knowledge_engine_ai.copilot.research_report import ResearchReport
from knowledge_engine_ai.copilot.run_research_question import OnlineResearchQuestionResult
from knowledge_engine_ai.copilot.stage_updates import ResearchStageUpdate
from knowledge_engine_ai.ke_client import FederatedDiscoveryResult, FederatedProviderStatus

from knowledge_engine_web import research_jobs
from knowledge_engine_web.ai_guardrails import AIAdmissionError
from knowledge_engine_web.ai_orchestration import AIOrchestrationError, WebResearchResult
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


def _federated_discovery(**overrides: object) -> FederatedDiscoveryResult:
    fields: dict[str, object] = {
        "search_run_id": "search-run-1",
        "query_text": "a research question",
        "completeness": "partial",
        "provider_statuses": (),
        "candidates": (),
        "provider_disagreements": None,
        "search_run_created_at": None,
    }
    fields.update(overrides)
    return FederatedDiscoveryResult(**fields)  # type: ignore[arg-type]


def _discovery(**overrides: object) -> DiscoveryAugmentationResult:
    fields: dict[str, object] = {
        "triggered": True,
        "trigger_reason": "indexed_coverage_below_minimum",
        "evidence_record_coverage": 0,
        "federated_discovery": _federated_discovery(),
        "federated_discovery_error": None,
        "federated_discovery_attempted": True,
    }
    fields.update(overrides)
    return DiscoveryAugmentationResult(**fields)  # type: ignore[arg-type]


class TestCoveragePanelPayloadFailureDrills:
    """WEB-GQR-5 failure drills: proves `_coverage_panel_payload` (consumed by the
    async job's durable presentation payload, see `_presentation_payload` below)
    actually surfaces each named failure signal rather than silently dropping it.
    Before this module gained `_coverage_panel_payload`, none of these facts
    reached a completed async job's persisted `result` at all -- only the
    synchronous `/ask` path ever built a coverage panel (see
    `research_coverage_presentation.py`)."""

    def test_provider_rate_limit_is_visible_without_failing_the_whole_run(self) -> None:
        result = cast(
            WebResearchResult,
            SimpleNamespace(
                discovery=_discovery(
                    federated_discovery=_federated_discovery(
                        completeness="partial",
                        provider_statuses=(
                            FederatedProviderStatus(
                                provider="semantic_scholar",
                                outcome="rate_limited",
                                attempted=True,
                                result_count=0,
                                reason="HTTP 429 from Semantic Scholar",
                            ),
                            FederatedProviderStatus(
                                provider="openalex",
                                outcome="success",
                                attempted=True,
                                result_count=4,
                                reason=None,
                            ),
                        ),
                    )
                ),
                grounded_completion=None,
            ),
        )

        panel = research_jobs._coverage_panel_payload(result)

        assert panel is not None
        assert panel["federated_discovery_error"] is None
        rows = {row["provider"]: row for row in panel["provider_rows"]}
        assert rows["semantic_scholar"]["label"] == "rate limited"
        assert rows["semantic_scholar"]["reason"] == "HTTP 429 from Semantic Scholar"
        assert rows["openalex"]["label"] == "searched"

    def test_one_provider_unavailable_reports_partial_completeness(self) -> None:
        result = cast(
            WebResearchResult,
            SimpleNamespace(
                discovery=_discovery(
                    federated_discovery=_federated_discovery(
                        completeness="partial",
                        provider_statuses=(
                            FederatedProviderStatus(
                                provider="europe_pmc",
                                outcome="unavailable",
                                attempted=True,
                                result_count=0,
                                reason="connection timed out",
                            ),
                        ),
                    )
                ),
                grounded_completion=None,
            ),
        )

        panel = research_jobs._coverage_panel_payload(result)

        assert panel is not None
        assert panel["completeness"] == "partial"
        row = panel["provider_rows"][0]
        assert row["label"] == "unavailable"
        assert row["reason"] == "connection timed out"

    def test_all_providers_unavailable_surfaces_the_whole_discovery_call_failure(self) -> None:
        result = cast(
            WebResearchResult,
            SimpleNamespace(
                discovery=_discovery(
                    federated_discovery=None,
                    federated_discovery_error="Core federated-discover CLI returned no response",
                ),
                grounded_completion=None,
            ),
        )

        panel = research_jobs._coverage_panel_payload(result)

        assert panel is not None
        assert panel["federated_discovery_error"] == (
            "Core federated-discover CLI returned no response"
        )
        assert panel["provider_rows"] == ()

    def test_source_inaccessible_or_license_unavailable_acquisition_route_is_not_hidden(
        self,
    ) -> None:
        result = cast(
            WebResearchResult,
            SimpleNamespace(
                discovery=_discovery(),
                grounded_completion=GroundedCompletionResult(
                    attempted=True,
                    search_run_id="search-run-1",
                    research_question_id="question-1",
                    acquisition_routes=(
                        AcquisitionRouteResult(
                            route="unpaywall",
                            candidate_ids=("cand-1",),
                            attempted=True,
                            error="license restricted: no open-access full text available",
                        ),
                        AcquisitionRouteResult(
                            route="pmc_oa",
                            candidate_ids=("cand-2",),
                            attempted=False,
                            skipped_reason="source inaccessible: PMC OA FTP unreachable",
                        ),
                    ),
                ),
            ),
        )

        panel = research_jobs._coverage_panel_payload(result)

        assert panel is not None
        routes = {row["route"]: row for row in panel["acquisition_routes"]}
        assert routes["unpaywall"]["error"] == (
            "license restricted: no open-access full text available"
        )
        assert routes["pmc_oa"]["skipped_reason"] == ("source inaccessible: PMC OA FTP unreachable")

    def test_extraction_producing_no_grounded_evidence_record_is_visible(self) -> None:
        result = cast(
            WebResearchResult,
            SimpleNamespace(
                discovery=_discovery(),
                grounded_completion=GroundedCompletionResult(
                    attempted=True,
                    search_run_id="search-run-1",
                    research_question_id="question-1",
                    draft_item_count=3,
                    classified_item_count=3,
                    staged_record_ids=("staged-1",),
                    grounded_record_ids=(),
                    promoted_record_ids=(),
                    grounding_failures=("staged-1",),
                    extraction_error="local grounding model returned no verifiable claim",
                ),
            ),
        )

        panel = research_jobs._coverage_panel_payload(result)

        assert panel is not None
        assert panel["promoted_record_count"] == 0
        assert panel["grounding_failure_count"] == 1
        assert panel["extraction_error"] == ("local grounding model returned no verifiable claim")


def _fake_completed_web_result(
    *,
    research_state_value: str = "researched_answer",
    research_state_reason: str = "grounded_completion_reretrieval_used_for_releaseable_answer",
    discovery: DiscoveryAugmentationResult | None = None,
    grounded_completion: GroundedCompletionResult | None = None,
    conversion_funnel: object | None = None,
) -> WebResearchResult:
    """Build the minimal duck-typed `WebResearchResult` shape `_presentation_payload`
    reads from, without running the real AI orchestration pipeline. Every attribute
    it touches is provided explicitly rather than guessed from `WebResearchResult`'s
    real property delegation, so a future added read raises `AttributeError` here
    instead of silently passing."""

    research_report = SimpleNamespace(to_dict=lambda: {"research_state": research_state_value})
    research = SimpleNamespace(
        progress_report=None,
        conversion_funnel_report=conversion_funnel,
        verification=None,
    )
    return cast(
        WebResearchResult,
        SimpleNamespace(
            session_id="session-1",
            question="A research question",
            research_state=SimpleNamespace(
                state=SimpleNamespace(value=research_state_value),
                reason=research_state_reason,
            ),
            narrative_releaseable=False,
            narrative=None,
            research_report=research_report,
            synthesis_error=None,
            workflow=SimpleNamespace(steps=()),
            close_result=SimpleNamespace(status=SimpleNamespace(value="allowed")),
            discovery=discovery,
            grounded_completion=grounded_completion,
            research=research,
        ),
    )


def test_presentation_payload_persists_a_populated_coverage_panel() -> None:
    """Closes the structural gap WEB-GQR-5 found: before `_coverage_panel_payload`
    existed, `_presentation_payload` (the durable async job result every visitor on
    the default-deployment async path actually receives) never carried discovery or
    grounded-completion facts at all, so a provider failure, a blocked acquisition
    route, or a failed extraction -- all already rendered on the synchronous `/ask`
    path's coverage panel -- were invisible to an async visitor."""

    result = _fake_completed_web_result(
        discovery=_discovery(
            federated_discovery_error="Core federated-discover CLI returned no response"
        ),
        grounded_completion=GroundedCompletionResult(
            attempted=True,
            search_run_id="search-run-1",
            research_question_id="question-1",
            extraction_error="local grounding model returned no verifiable claim",
        ),
    )

    payload = research_jobs._presentation_payload(result)

    assert payload["coverage_panel"] is not None
    assert payload["coverage_panel"]["federated_discovery_error"] == (
        "Core federated-discover CLI returned no response"
    )
    assert payload["coverage_panel"]["extraction_error"] == (
        "local grounding model returned no verifiable claim"
    )


def test_presentation_payload_persists_core_retrieval_failure_reason_for_a_blocked_run() -> None:
    """WEB-GQR-5 failure drill: a Core retrieval failure derives AI's `blocked`
    research state with reason `primary_retrieval_failed` (see
    `knowledge_engine_ai.copilot.research_state.derive_research_state`); the async
    job payload must carry that reason through rather than only the bare state."""

    result = _fake_completed_web_result(
        research_state_value="blocked",
        research_state_reason="primary_retrieval_failed",
    )

    payload = research_jobs._presentation_payload(result)

    assert payload["research_state"] == "blocked"
    assert payload["research_state_reason"] == "primary_retrieval_failed"


def test_presentation_payload_persists_acquisition_budget_exhaustion() -> None:
    """WEB-GQR-5 failure drill: overall budget exhausted. AI's BT-2 conversion
    funnel already records how many discovered candidates were skipped because the
    acquisition budget ran out (`AcquisitionPlanFunnel.skipped_budget_count`); the
    async job payload must preserve that count rather than collapsing the funnel
    into only its latency fields."""

    funnel = SimpleNamespace(
        to_dict=lambda: {
            "acquisition_plan": {"skipped_budget_count": 7},
            "time_to_first_grounded_information_ms": None,
            "time_to_final_report_ms": None,
        }
    )

    result = _fake_completed_web_result(conversion_funnel=funnel)

    payload = research_jobs._presentation_payload(result)

    assert payload["conversion_funnel"]["acquisition_plan"]["skipped_budget_count"] == 7


def _stage_update(stage: str, sequence: int, detail: str = "") -> ResearchStageUpdate:
    return ResearchStageUpdate(
        schema_version=1,
        sequence=sequence,
        session_id="s",
        stage=ResearchProgressStage(stage),
        elapsed_ms=sequence * 100,
        detail=detail,
    )


def test_running_job_exposes_the_stage_ai_just_announced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "research_sessions.sqlite3"
    settings = Settings(_env_file=None, session_db_path=str(database_path))
    research_jobs.create_research_job(
        str(database_path),
        session_id="session-stage",
        research_question_id="question-stage",
        question="A research question",
    )
    seen_while_running: list[dict[str, object] | None] = []

    def _announcing_run(*_args: object, on_stage: object = None, **_kwargs: object) -> None:
        assert callable(on_stage)
        on_stage(_stage_update("searching_indexed_evidence", 1))
        on_stage(_stage_update("acquiring_sources", 2, "acquisition routes: 2"))
        job = research_jobs.read_research_job(str(database_path), "session-stage")
        assert job is not None
        seen_while_running.append(job.current_stage)
        raise AIAdmissionError("rejected", "Research mode is unavailable right now.")

    monkeypatch.setattr(research_jobs, "run_guarded_ai_orchestration", _announcing_run)

    research_jobs._execute_research_job(settings, "A research question", "k", "session-stage", None)

    assert seen_while_running[0] is not None
    assert seen_while_running[0]["stage"] == "acquiring_sources"
    assert seen_while_running[0]["sequence"] == 2
    assert seen_while_running[0]["detail"] == "acquisition routes: 2"
    assert seen_while_running[0]["elapsed_ms"] == 200


def test_a_late_stage_update_never_overwrites_a_terminal_job(tmp_path: Path) -> None:
    database_path = str(tmp_path / "research_sessions.sqlite3")
    research_jobs.create_research_job(
        database_path,
        session_id="session-late",
        research_question_id="question-late",
        question="A research question",
    )
    research_jobs._record_stage(database_path, "session-late", _stage_update("reretrieving", 1))
    research_jobs._mark_failed(database_path, "session-late", "stopped")
    research_jobs._record_stage(database_path, "session-late", _stage_update("final_answer", 2))

    job = research_jobs.read_research_job(database_path, "session-late")
    assert job is not None and job.status == "failed"
    assert job.current_stage is not None
    assert job.current_stage["stage"] == "reretrieving"


def test_stage_detail_is_length_capped(tmp_path: Path) -> None:
    database_path = str(tmp_path / "research_sessions.sqlite3")
    research_jobs.create_research_job(
        database_path,
        session_id="session-cap",
        research_question_id="question-cap",
        question="A research question",
    )
    research_jobs._record_stage(
        database_path, "session-cap", _stage_update("discovering_sources", 1, "x" * 5000)
    )
    job = research_jobs.read_research_job(database_path, "session-cap")
    assert job is not None and job.current_stage is not None
    assert len(str(job.current_stage["detail"])) == 200


def test_stage_write_failure_is_swallowed(tmp_path: Path) -> None:
    # An unwritable path must never raise into the research thread.
    research_jobs._record_stage(
        str(tmp_path / "missing-dir" / "db.sqlite3"),
        "session-none",
        _stage_update("searching_indexed_evidence", 1),
    )


def test_job_before_any_stage_reads_as_no_stage(tmp_path: Path) -> None:
    database_path = str(tmp_path / "research_sessions.sqlite3")
    research_jobs.create_research_job(
        database_path,
        session_id="session-none",
        research_question_id="question-none",
        question="A research question",
    )
    job = research_jobs.read_research_job(database_path, "session-none")
    assert job is not None and job.current_stage is None


def test_malformed_stored_stage_reads_as_no_stage(tmp_path: Path) -> None:
    database_path = str(tmp_path / "research_sessions.sqlite3")
    research_jobs.create_research_job(
        database_path,
        session_id="session-bad",
        research_question_id="question-bad",
        question="A research question",
    )
    connection = sqlite3.connect(database_path)
    connection.execute("UPDATE web_research_jobs SET current_stage_json = '{not json'")
    connection.commit()
    connection.close()
    job = research_jobs.read_research_job(database_path, "session-bad")
    assert job is not None and job.current_stage is None


def test_a_pre_existing_database_without_current_stage_is_migrated_on_write(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "research_sessions.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE web_research_jobs (
            session_id TEXT PRIMARY KEY, research_question_id TEXT NOT NULL,
            question TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, visitor_error TEXT, result_json TEXT, request_id TEXT
        )
        """
    )
    connection.execute(
        "INSERT INTO web_research_jobs VALUES "
        "('old', 'q', 'Q?', 'running', 't', 't', NULL, NULL, NULL)"
    )
    connection.commit()
    connection.close()

    before = research_jobs.read_research_job(str(database_path), "old")
    assert before is not None and before.current_stage is None  # column absent: read defensively

    research_jobs._record_stage(
        str(database_path), "old", _stage_update("validating_extracting_evidence", 3)
    )
    after = research_jobs.read_research_job(str(database_path), "old")
    assert after is not None and after.current_stage is not None
    assert after.current_stage["stage"] == "validating_extracting_evidence"


def test_stage_history_grows_in_order(tmp_path: Path) -> None:
    database_path = str(tmp_path / "research_sessions.sqlite3")
    research_jobs.create_research_job(
        database_path,
        session_id="session-history",
        research_question_id="question-history",
        question="A research question",
    )
    for sequence, stage in enumerate(
        ("searching_indexed_evidence", "discovering_sources", "acquiring_sources"), start=1
    ):
        research_jobs._record_stage(
            database_path, "session-history", _stage_update(stage, sequence)
        )

    job = research_jobs.read_research_job(database_path, "session-history")
    assert job is not None and job.current_stage is not None
    assert [entry["stage"] for entry in job.current_stage["history"]] == [
        "searching_indexed_evidence",
        "discovering_sources",
        "acquiring_sources",
    ]
    assert [entry["sequence"] for entry in job.current_stage["history"]] == [1, 2, 3]
    assert job.current_stage["stage"] == "acquiring_sources"


def test_stage_history_is_capped_at_the_last_twelve(tmp_path: Path) -> None:
    database_path = str(tmp_path / "research_sessions.sqlite3")
    research_jobs.create_research_job(
        database_path,
        session_id="session-cap-history",
        research_question_id="question-cap-history",
        question="A research question",
    )
    for sequence in range(1, 21):
        research_jobs._record_stage(
            database_path,
            "session-cap-history",
            _stage_update("validating_extracting_evidence", sequence),
        )

    job = research_jobs.read_research_job(database_path, "session-cap-history")
    assert job is not None and job.current_stage is not None
    history = job.current_stage["history"]
    assert len(history) == 12
    assert [entry["sequence"] for entry in history] == list(range(9, 21))


def test_malformed_stored_history_restarts_cleanly(tmp_path: Path) -> None:
    database_path = str(tmp_path / "research_sessions.sqlite3")
    research_jobs.create_research_job(
        database_path,
        session_id="session-bad-history",
        research_question_id="question-bad-history",
        question="A research question",
    )
    connection = sqlite3.connect(database_path)
    connection.execute(
        "UPDATE web_research_jobs SET current_stage_json = ?",
        (json.dumps({"stage": "reretrieving", "history": "not a list"}),),
    )
    connection.commit()
    connection.close()

    research_jobs._record_stage(
        database_path, "session-bad-history", _stage_update("reretrieving", 7)
    )
    job = research_jobs.read_research_job(database_path, "session-bad-history")
    assert job is not None and job.current_stage is not None
    assert [entry["sequence"] for entry in job.current_stage["history"]] == [7]


def test_history_drops_malformed_entries_but_keeps_valid_ones(tmp_path: Path) -> None:
    database_path = str(tmp_path / "research_sessions.sqlite3")
    research_jobs.create_research_job(
        database_path,
        session_id="session-mixed-history",
        research_question_id="question-mixed-history",
        question="A research question",
    )
    connection = sqlite3.connect(database_path)
    connection.execute(
        "UPDATE web_research_jobs SET current_stage_json = ?",
        (
            json.dumps(
                {
                    "stage": "discovering_sources",
                    "history": [
                        "junk",
                        {"no_stage": 1},
                        {"stage": "discovering_sources", "sequence": 2, "elapsed_ms": 20},
                    ],
                }
            ),
        ),
    )
    connection.commit()
    connection.close()

    research_jobs._record_stage(
        database_path, "session-mixed-history", _stage_update("acquiring_sources", 3)
    )
    job = research_jobs.read_research_job(database_path, "session-mixed-history")
    assert job is not None and job.current_stage is not None
    assert [entry["sequence"] for entry in job.current_stage["history"]] == [2, 3]


def test_late_update_after_terminal_does_not_extend_history(tmp_path: Path) -> None:
    database_path = str(tmp_path / "research_sessions.sqlite3")
    research_jobs.create_research_job(
        database_path,
        session_id="session-late-history",
        research_question_id="question-late-history",
        question="A research question",
    )
    research_jobs._record_stage(
        database_path, "session-late-history", _stage_update("reretrieving", 1)
    )
    research_jobs._mark_failed(database_path, "session-late-history", "stopped")
    research_jobs._record_stage(
        database_path, "session-late-history", _stage_update("final_answer", 2)
    )

    job = research_jobs.read_research_job(database_path, "session-late-history")
    assert job is not None and job.current_stage is not None
    assert [entry["sequence"] for entry in job.current_stage["history"]] == [1]
