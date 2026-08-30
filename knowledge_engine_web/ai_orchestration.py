"""Capability-gated bridge from the web `/ask` page to Research Copilot.

The web page remains useful as deterministic retrieval when this optional
runtime is incomplete. This module owns the integration boundary so route
code does not need to know how `knowledge-engine-ai`, its durable session
store, or core's `ke` subprocess interface are assembled.

General Question Research Loop v1 enables the AI layer's bounded,
deterministic coverage-gap research path for Research Copilot runs. The local
corpus remains the first stop. When indexed EvidenceRecord coverage is thin,
AI may run federated discovery, request Core's bounded acquisition plan,
acquire accessible papers, ground and promote new evidence, re-run the
original question, and only then synthesize from that new evidence. Discovery
candidates and acquired Papers never become answer evidence merely by being
found or downloaded.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from knowledge_engine_ai.copilot.discovery_policy import (
    DiscoveryAugmentationResult,
    FederatedDiscoveryPolicy,
)
from knowledge_engine_ai.copilot.grounded_completion import (
    GroundedCompletionPolicy,
    GroundedCompletionResult,
)
from knowledge_engine_ai.copilot.research_state import ResearchStateResult, derive_research_state
from knowledge_engine_ai.copilot.run_research_question import (
    ResearchQuestionResult,
    run_research_question,
)
from knowledge_engine_ai.llm import OllamaLLM
from knowledge_engine_ai.models import EvidenceReport
from knowledge_engine_ai.orchestrator.close_gate import SessionCloseResult
from knowledge_engine_ai.orchestrator.observability import SessionTrace
from knowledge_engine_ai.orchestrator.session_report import SessionReport
from knowledge_engine_ai.orchestrator.verification import VerificationResult
from knowledge_engine_ai.orchestrator.workflow import WorkflowResult
from knowledge_engine_ai.sessions.repository import SessionRepository, new_connection

from knowledge_engine_web.ai_guardrails import AIRequestGuard
from knowledge_engine_web.config import Settings
from knowledge_engine_web.discovery_orchestration import evaluate_discovery_capability

_GLOBAL_AI_REQUEST_GUARD = AIRequestGuard()
_EXECUTION_TIMEOUT_FRAGMENTS = (
    "configured execution time limit",
    "did not respond within",
)

# Commands the current composed Research Copilot path can invoke through
# knowledge-engine-ai. This is intentionally explicit rather than assuming
# any executable named "ke" is the right Core build. Command-specific --help
# probes do not contact providers, mutate research state, or run a model.
_RESEARCH_CORE_COMMANDS: tuple[str, ...] = (
    "evidence-report",
    "evidence-intelligence",
    "federated-discover",
    "citation-snowball",
    "general-question-acquisition-plan",
    "general-question-acquire-pmc",
    "general-question-acquire-europe-pmc",
    "general-question-acquire-core",
    "general-question-acquire-unpaywall",
    "extraction-review-batch-generate",
    "extraction-review-autoclassify",
    "extraction-review-promote",
    "evidence-review-automate",
    "evidence-record-review-promote",
)
_CORE_COMMAND_HELP_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class AICapability:
    """One deployment's static ability to attempt a complete Research Copilot run."""

    available: bool
    reason_code: str | None = None
    visitor_message: str | None = None
    session_storage_mode: str | None = None


@dataclass(frozen=True)
class WebResearchResult:
    """Web-facing Research Copilot result with AI-owned GQR workflow state.

    Web deliberately does not infer state from narrative text, candidate
    counts, or provider counts. The state is derived by knowledge-engine-ai
    from its deterministic workflow facts and carried through unchanged here.
    """

    research: ResearchQuestionResult
    research_state: ResearchStateResult

    @property
    def session_id(self) -> str:
        return self.research.session_id

    @property
    def question(self) -> str:
        return self.research.question

    @property
    def workflow(self) -> WorkflowResult:
        return self.research.workflow

    @property
    def discovery(self) -> DiscoveryAugmentationResult | None:
        return self.research.discovery

    @property
    def grounded_completion(self) -> GroundedCompletionResult | None:
        return self.research.grounded_completion

    @property
    def effective_evidence_report(self) -> EvidenceReport | None:
        return self.research.effective_evidence_report

    @property
    def used_reretrieved_evidence(self) -> bool:
        return self.research.used_reretrieved_evidence

    @property
    def narrative(self) -> str | None:
        return self.research.narrative

    @property
    def synthesis_error(self) -> str | None:
        return self.research.synthesis_error

    @property
    def verification(self) -> VerificationResult | None:
        return self.research.verification

    @property
    def session_report(self) -> SessionReport | None:
        return self.research.session_report

    @property
    def close_result(self) -> SessionCloseResult:
        return self.research.close_result

    @property
    def trace(self) -> SessionTrace:
        return self.research.trace

    @property
    def narrative_releaseable(self) -> bool:
        return self.research.narrative_releaseable


class AIOrchestrationError(RuntimeError):
    """The optional Research Copilot runtime could not complete safely."""


class _WorkflowStepLike(Protocol):
    @property
    def error(self) -> str | None: ...


class _WorkflowLike(Protocol):
    @property
    def steps(self) -> tuple[_WorkflowStepLike, ...]: ...


class _ResearchResultLike(Protocol):
    @property
    def workflow(self) -> _WorkflowLike: ...

    @property
    def synthesis_error(self) -> str | None: ...


def evaluate_ai_capability(settings: Settings) -> AICapability:
    """Fail closed unless every complete Research Copilot prerequisite exists.

    The ordinary local check remains filesystem-only. Hosted deployments may
    additionally enable ``core_cli_command_preflight``; that performs cached,
    command-specific ``--help`` probes against the configured local Core CLI.
    Those probes do not contact Ollama, scholarly providers, or mutate Core
    state. Research mode can promote newly grounded EvidenceRecords, so both
    the durable evidence file and acquired-paper destination must be writable
    before Web advertises the complete path as available.
    """

    if not _nonblank(settings.llm_model):
        return _unavailable("model_not_configured")
    if _configured_file(settings.sources_path) is None:
        return _unavailable("sources_unavailable")
    if _configured_writable_file(settings.evidence_records_path) is None:
        return _unavailable("evidence_unavailable")
    executable = _resolve_executable(settings.ke_executable)
    if executable is None:
        return _unavailable("core_cli_unavailable")
    if settings.core_cli_command_preflight and not _core_cli_has_required_commands(executable):
        return _unavailable("core_cli_incomplete")
    if not _directory_destination_is_usable(Path(settings.research_papers_dir)):
        return _unavailable("research_papers_unavailable")
    session_capability = _evaluate_session_storage(settings)
    if not session_capability.available:
        return session_capability
    discovery_capability = evaluate_discovery_capability(settings)
    if not discovery_capability.available:
        return _unavailable(discovery_capability.reason_code or "discovery_unavailable")
    return AICapability(available=True, session_storage_mode=settings.session_storage_mode)


def _build_discovery_policy(settings: Settings, executable: str) -> FederatedDiscoveryPolicy:
    """Build Web's bounded discovery-and-acquisition-plan policy.

    Indexed evidence is always searched first. External discovery is attempted
    only when AI's deterministic evidence-record coverage rule says the index
    is thin. Acquisition planning is enabled here because Research mode now
    composes the GQR-4/GQR-5 grounded-completion bridge; the plan still cannot
    put a candidate into synthesis by itself.
    """

    return FederatedDiscoveryPolicy(
        ledger_root=Path(settings.federated_discovery_ledger_root),
        openalex_api_key=settings.federated_openalex_api_key,
        semantic_scholar_api_key=settings.federated_semantic_scholar_api_key,
        ke_executable=executable,
        enable_acquisition_plan=True,
    )


def _build_grounded_completion_policy(settings: Settings) -> GroundedCompletionPolicy:
    """Build the bounded GQR-4/GQR-5 policy paired with Web's discovery policy."""

    assert settings.llm_model is not None
    return GroundedCompletionPolicy(
        ledger_root=Path(settings.federated_discovery_ledger_root),
        papers_dir=Path(settings.research_papers_dir),
        grounding_model=settings.llm_model.strip(),
    )


def run_ai_orchestration(
    settings: Settings,
    question: str,
    *,
    timeout_seconds: float | None = None,
    session_id: str | None = None,
) -> ResearchQuestionResult:
    """Run one complete durable Research Copilot session.

    The composed path is indexed retrieval first, then bounded discovery and
    acquisition planning only when coverage is thin, followed by grounded
    completion and original-question re-retrieval. Synthesis uses the
    reretrieved report only when newly promoted grounded evidence exists;
    otherwise AI keeps the original report and records why the research path
    did not produce replacement evidence.
    """

    capability = evaluate_ai_capability(settings)
    if not capability.available:
        raise AIOrchestrationError(
            capability.visitor_message or "Research Copilot is unavailable on this deployment."
        )

    assert settings.llm_model is not None
    assert settings.sources_path is not None
    assert settings.evidence_records_path is not None
    executable = _resolve_executable(settings.ke_executable)
    assert executable is not None
    model = settings.llm_model.strip()

    connection: sqlite3.Connection | None = None
    try:
        connection = new_connection(settings.session_db_path)
        repository = SessionRepository(connection)
        return run_research_question(
            question,
            session_repository=repository,
            sources=Path(settings.sources_path),
            evidence=Path(settings.evidence_records_path),
            llm=OllamaLLM(model=model, host=settings.ollama_host),
            discovery_policy=_build_discovery_policy(settings, executable),
            grounded_completion_policy=_build_grounded_completion_policy(settings),
            ke_executable=executable,
            timeout_seconds=timeout_seconds,
            session_id=session_id,
        )
    except Exception as exc:
        # This integration crosses SQLite, subprocess, writable corpus,
        # provider-network, acquisition, and local-model boundaries. Visitor
        # output must not leak paths or raw exception details; deterministic
        # retrieval remains available.
        raise AIOrchestrationError(
            "Research Copilot could not complete this request. "
            "Deterministic retrieval results are still shown below."
        ) from exc
    finally:
        if connection is not None:
            connection.close()


def run_guarded_ai_orchestration(
    settings: Settings,
    question: str,
    *,
    client_key: str,
    guard: AIRequestGuard | None = None,
    session_id: str | None = None,
) -> WebResearchResult:
    """Admit one bounded request and attach AI's deterministic GQR state."""

    request_guard = guard if guard is not None else _GLOBAL_AI_REQUEST_GUARD
    with request_guard.admit(
        client_key,
        max_concurrent_requests=settings.ai_max_concurrent_requests,
        rate_limit_requests=settings.ai_rate_limit_requests,
        rate_limit_window_seconds=settings.ai_rate_limit_window_seconds,
    ):
        research = run_ai_orchestration(
            settings,
            question,
            timeout_seconds=settings.ai_request_timeout_seconds,
            session_id=session_id,
        )
        return WebResearchResult(
            research=research,
            research_state=derive_research_state(research),
        )


def result_reached_execution_limit(result: _ResearchResultLike) -> bool:
    """Return whether durable workflow state records an execution timeout."""

    errors = [
        error
        for step in result.workflow.steps
        if (error := getattr(step, "error", None)) is not None
    ]
    if result.synthesis_error:
        errors.append(result.synthesis_error)
    return any(fragment in error for error in errors for fragment in _EXECUTION_TIMEOUT_FRAGMENTS)


def _unavailable(reason_code: str) -> AICapability:
    return AICapability(
        available=False,
        reason_code=reason_code,
        visitor_message=(
            "Research Copilot is unavailable on this deployment; Ask remains retrieval-only."
        ),
    )


def _configured_file(value: str | None) -> Path | None:
    if value is None or not value.strip():
        return None
    path = Path(value.strip())
    return path if path.is_file() else None


def _configured_writable_file(value: str | None) -> Path | None:
    path = _configured_file(value)
    if path is None or not os.access(path, os.W_OK):
        return None
    return path


def _nonblank(value: str | None) -> bool:
    return bool(value and value.strip())


def _resolve_executable(value: str) -> str | None:
    executable = value.strip()
    return shutil.which(executable) if executable else None


@lru_cache(maxsize=8)
def _core_cli_has_required_commands(executable: str) -> bool:
    """Verify the configured Core CLI exposes the complete Research command set.

    The result is process-cached because a deployed executable is immutable for
    the lifetime of the Web process. Each probe is deliberately ``--help``
    only: no provider request, database mutation, acquisition, extraction, or
    model call can occur merely from rendering the Ask page.
    """

    for command in _RESEARCH_CORE_COMMANDS:
        try:
            result = subprocess.run(
                [executable, command, "--help"],
                capture_output=True,
                text=True,
                check=False,
                timeout=_CORE_COMMAND_HELP_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0:
            return False
    return True


def _directory_destination_is_usable(path: Path) -> bool:
    if path.exists():
        return path.is_dir() and os.access(path, os.W_OK)
    return path.parent.is_dir() and os.access(path.parent, os.W_OK)


def _session_store_is_usable(path: Path) -> bool:
    if path.exists():
        return path.is_file() and os.access(path, os.W_OK)
    return path.parent.is_dir() and os.access(path.parent, os.W_OK)


def _evaluate_session_storage(settings: Settings) -> AICapability:
    database_path = Path(settings.session_db_path)
    if settings.session_storage_mode == "local":
        if not _session_store_is_usable(database_path):
            return _unavailable("session_store_unavailable")
        return AICapability(available=True, session_storage_mode="local")

    persistent_root_value = settings.session_persistent_root
    if persistent_root_value is None or not persistent_root_value.strip():
        return _unavailable("persistent_session_root_unavailable")

    persistent_root = Path(persistent_root_value.strip())
    if not persistent_root.is_absolute() or not database_path.is_absolute():
        return _unavailable("persistent_session_path_invalid")
    if not persistent_root.is_dir() or not os.access(persistent_root, os.W_OK):
        return _unavailable("persistent_session_root_unavailable")

    try:
        resolved_root = persistent_root.resolve(strict=True)
        resolved_database = database_path.resolve(strict=False)
    except OSError:
        return _unavailable("persistent_session_path_invalid")

    if resolved_database == resolved_root or not resolved_database.is_relative_to(resolved_root):
        return _unavailable("persistent_session_path_invalid")

    if not _session_store_is_usable(database_path):
        return _unavailable("session_store_unavailable")

    return AICapability(available=True, session_storage_mode="persistent")


__all__ = [
    "AICapability",
    "AIOrchestrationError",
    "WebResearchResult",
    "evaluate_ai_capability",
    "result_reached_execution_limit",
    "run_ai_orchestration",
    "run_guarded_ai_orchestration",
]
