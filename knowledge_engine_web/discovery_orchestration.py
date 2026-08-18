"""Capability-gated bridge from the web `/discover` page to federated discovery.

Mirrors `ai_orchestration.py`'s pattern for the Research Copilot integration,
but for a separate, opt-in feature: Core's `ke federated-discover` command
(FRD-1/FRD-2/FRD-3 -- PubMed, Crossref, OpenAlex, Semantic Scholar behind
one recorded, deduplicated search run). Kept on its own `AIRequestGuard`
instance and its own timeout/concurrency/rate-limit settings so this feature
cannot starve, or be starved by, the existing Research Copilot path.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from knowledge_engine_ai.execution import ExecutionBudget
from knowledge_engine_ai.ke_client import (
    FederatedDiscoveryResult,
    KeCommandError,
    federated_discover,
)

from knowledge_engine_web.ai_guardrails import AIRequestGuard
from knowledge_engine_web.config import Settings

_GLOBAL_DISCOVERY_REQUEST_GUARD = AIRequestGuard()

_DEFAULT_DISCOVERY_LIMIT = 10


@dataclass(frozen=True)
class DiscoveryCapability:
    """One deployment's static ability to attempt a federated discovery run."""

    available: bool
    reason_code: str | None = None
    visitor_message: str | None = None


class DiscoveryOrchestrationError(RuntimeError):
    """The optional federated discovery runtime could not complete safely."""


def evaluate_discovery_capability(settings: Settings) -> DiscoveryCapability:
    """Fail closed unless every local federated-discovery prerequisite exists.

    Deliberately static: does not execute `ke` or contact any provider merely
    to render the Discover form. Runtime dependencies are exercised only
    after a person explicitly submits a query.
    """

    if _resolve_executable(settings.ke_executable) is None:
        return _unavailable("core_cli_unavailable")
    if not _ledger_root_is_usable(Path(settings.federated_discovery_ledger_root)):
        return _unavailable("ledger_root_unavailable")
    return DiscoveryCapability(available=True)


def run_discovery(settings: Settings, query: str) -> FederatedDiscoveryResult:
    """Run one federated discovery search using configured local inputs."""

    capability = evaluate_discovery_capability(settings)
    if not capability.available:
        raise DiscoveryOrchestrationError(
            capability.visitor_message or "Discovery is unavailable on this deployment."
        )

    executable = _resolve_executable(settings.ke_executable)
    assert executable is not None

    try:
        return federated_discover(
            query,
            ledger_root=Path(settings.federated_discovery_ledger_root),
            limit=_DEFAULT_DISCOVERY_LIMIT,
            openalex_api_key=settings.federated_openalex_api_key,
            semantic_scholar_api_key=settings.federated_semantic_scholar_api_key,
            ke_executable=executable,
            execution_budget=ExecutionBudget.from_timeout(
                settings.discovery_request_timeout_seconds
            ),
        )
    except KeCommandError as exc:
        # Crosses a subprocess boundary to several external provider APIs.
        # Visitor output must not leak paths, raw exception details, or
        # provider-side error bodies.
        raise DiscoveryOrchestrationError(
            "Discovery could not complete this request. Please try again."
        ) from exc


def run_guarded_discovery(
    settings: Settings,
    query: str,
    *,
    client_key: str,
    guard: AIRequestGuard | None = None,
) -> FederatedDiscoveryResult:
    """Admit and run one bounded federated discovery request."""

    request_guard = guard if guard is not None else _GLOBAL_DISCOVERY_REQUEST_GUARD
    with request_guard.admit(
        client_key,
        max_concurrent_requests=settings.discovery_max_concurrent_requests,
        rate_limit_requests=settings.discovery_rate_limit_requests,
        rate_limit_window_seconds=settings.discovery_rate_limit_window_seconds,
    ):
        return run_discovery(settings, query)


def _unavailable(reason_code: str) -> DiscoveryCapability:
    return DiscoveryCapability(
        available=False,
        reason_code=reason_code,
        visitor_message="Discovery is unavailable on this deployment.",
    )


def _resolve_executable(value: str) -> str | None:
    executable = value.strip()
    return shutil.which(executable) if executable else None


def _ledger_root_is_usable(path: Path) -> bool:
    if path.exists():
        return path.is_dir() and os.access(path, os.W_OK)
    return path.parent.is_dir() and os.access(path.parent, os.W_OK)


__all__ = [
    "DiscoveryCapability",
    "DiscoveryOrchestrationError",
    "evaluate_discovery_capability",
    "run_discovery",
    "run_guarded_discovery",
]
