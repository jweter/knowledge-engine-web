"""Capability-gated bridge from the web `/ask` page to Research Copilot.

The web page remains useful as deterministic retrieval when this optional
runtime is incomplete. This module owns the integration boundary so route
code does not need to know how `knowledge-engine-ai`, its durable session
store, or core's `ke` subprocess interface are assembled.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from knowledge_engine_ai.copilot.run_research_question import (
    ResearchQuestionResult,
    run_research_question,
)
from knowledge_engine_ai.llm import OllamaLLM
from knowledge_engine_ai.sessions.repository import SessionRepository, new_connection

from knowledge_engine_web.config import Settings


@dataclass(frozen=True)
class AICapability:
    """One deployment's static ability to attempt a Research Copilot run."""

    available: bool
    reason_code: str | None = None
    visitor_message: str | None = None


class AIOrchestrationError(RuntimeError):
    """The optional Research Copilot runtime could not complete safely."""


def evaluate_ai_capability(settings: Settings) -> AICapability:
    """Fail closed unless every local Research Copilot prerequisite exists.

    This is deliberately a static deployment check. It does not contact
    Ollama, execute `ke`, create the session database, or otherwise mutate
    state merely to render the Ask form. Runtime dependencies are exercised
    only after a person explicitly requests AI narration.
    """

    if not _nonblank(settings.llm_model):
        return _unavailable("model_not_configured")
    if _configured_file(settings.sources_path) is None:
        return _unavailable("sources_unavailable")
    if _configured_file(settings.evidence_records_path) is None:
        return _unavailable("evidence_unavailable")
    if _resolve_executable(settings.ke_executable) is None:
        return _unavailable("core_cli_unavailable")
    if not _session_store_is_usable(Path(settings.session_db_path)):
        return _unavailable("session_store_unavailable")
    return AICapability(available=True)


def run_ai_orchestration(settings: Settings, question: str) -> ResearchQuestionResult:
    """Run one durable Research Copilot session using configured local inputs."""

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
            ke_executable=executable,
        )
    except Exception as exc:
        # This integration crosses SQLite, subprocess, file, and local-model
        # boundaries. Visitor output must not leak paths or raw exception
        # details; deterministic retrieval remains available.
        raise AIOrchestrationError(
            "Research Copilot could not complete this request. "
            "Deterministic retrieval results are still shown below."
        ) from exc
    finally:
        if connection is not None:
            connection.close()


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


__all__ = [
    "AICapability",
    "AIOrchestrationError",
    "evaluate_ai_capability",
    "run_ai_orchestration",
]
