"""Capability-gated bridge from the web `/ask` page to Research Copilot.

The web page remains useful as deterministic retrieval when this optional
runtime is incomplete. This module owns the integration boundary so route
code does not need to know how `knowledge-engine-ai`, its durable session
store, or core's `ke` subprocess interface are assembled.

General Question Research Loop v1 deliberately enables the AI layer's
bounded, deterministic coverage-gap discovery policy for Research Copilot
runs. The local corpus remains the first stop; federated discovery runs only
when the AI layer's evidence-record coverage rule says the indexed evidence
is thin. Discovered candidates remain leads, not Evidence Records, until Core
acquires and validates them.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from knowledge_engine_ai.copilot.discovery_policy import (
    DiscoveryAugmentationResult,
    FederatedDiscoveryPolicy,
)
from knowledge_engine_ai.copilot.research_state import ResearchStateResult, derive_research_state
from knowledge_engine_ai.copilot.run_research_question import (
    ResearchQuestionResult,
    run_research_question,
)
from knowledge_engine_ai.llm import OllamaLLM
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


@dataclass(frozen=True)
class AICapability:
    """One deployment's static ability to attempt a Research Copilot run."""

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
    """Fail closed unless every Research Copilot prerequisite exists.

    This is deliberately a static deployment check. It does not contact
    Ollama, execute `ke`, create the session database, or contact scholarly
    providers merely to render the Ask form. Because General Question Research
    Loop v1 enables bounded discovery on every Research Copilot run, the
    discovery ledger must pass the same storage checks used by `/discover`
    before the AI path is advertised as available.
    """

    if not _nonblank(settings.llm_model):
        return _unavailable("model_not_configured")
    if _configured_file(settings.sources_path) is None:
        return _unavailable("sources_unavailable")
    if _configured_file(settings.evidence_records_path) is None:
        return _unavailable("evidence_unavailable")
    if _resolve_executable(settings.ke_executable) is None:
        return _unavailable("core_cli_unavailable")
    session_capability = _evaluate_session_storage(settings)
    if not session_capability.available:
        return session_capability
    discovery_capability = evaluate_discovery_capability(settings)
    if not discovery_capability.available:
        return _unavailable(discovery_capability.reason_code or "discovery_unavailable")
    return AICapability(available=True, session_storage_mode=settings.session_storage_mode)


def _build_discovery_policy(settings: Settings, executable: str) -> FederatedDiscoveryPolicy:
    """Build the bounded default policy for arbitrary-question Research Copilot runs.

    The policy's trigger is deterministic and implemented in
    `knowledge-engine-ai`: indexed evidence is always searched first, and
    external discovery is attempted only when deduplicated evidence-record
    coverage falls below the configured AI-layer threshold. This helper only
    supplies Web's validated durable ledger location, provider credentials,
    and Core CLI.
    """

    return FederatedDiscoveryPolicy(
        ledger_root=Path(settings.federated_discovery_ledger_root),
        openalex_api_key=settings.federated_openalex_api_key,
        semantic_scholar_api_key=settings.federated_semantic_scholar_api_key,
        ke_executable=executable,
    )


def run_ai_orchestration(
    settings: Settings,
    question: str,
    *,
    timeout_seconds: float | None = None,
) -> ResearchQuestionResult:
    """Run one durable Research Copilot session using configured local inputs.

    General Question Research Loop v1 enables bounded coverage-gap discovery
    on this path. This does not make discovery candidates citable evidence;
    acquisition/validation remains a separate Core responsibility.
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
            ke_executable=executable,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        # This integration crosses SQLite, subprocess, file, network-provider,
        # and local-model boundaries. Visitor output must not leak paths or raw
        # exception details; deterministic retrieval remains available.
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


def _nonblank(value: str | None) -> bool:
    return bool(value and value.strip())


def _resolve_executable(value: str) -> str | None:
    executable = value.strip()
    return shutil.which(executable) if executable else None


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
