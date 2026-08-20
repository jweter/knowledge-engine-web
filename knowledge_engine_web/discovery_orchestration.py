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
    FederatedDiscoverHistoryResult,
    FederatedDiscoveryResult,
    KeCommandError,
    federated_discover,
    federated_discover_history,
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
    ledger_capability = _evaluate_ledger_storage(settings)
    if not ledger_capability.available:
        return ledger_capability
    return DiscoveryCapability(available=True)


def run_discovery(
    settings: Settings,
    query: str,
    *,
    research_question_id: str | None = None,
) -> FederatedDiscoveryResult:
    """Run one federated discovery search using configured local inputs.

    ``research_question_id`` (WEB-FRD-5 item 5, `research_question.py`'s
    deterministic tracked-question identity) is forwarded to Core so later
    runs for the same question can be listed together via
    `run_discovery_history` below. Omitting it preserves the exact prior
    behavior of an untagged, one-off search.
    """

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
            research_question_id=research_question_id,
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
    research_question_id: str | None = None,
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
        return run_discovery(settings, query, research_question_id=research_question_id)


def run_discovery_history(
    settings: Settings, research_question_id: str
) -> FederatedDiscoverHistoryResult:
    """Fetch every persisted run tagged with ``research_question_id``, newest first.

    WEB-FRD-5 item 3/5: the read side of the tracked-question identity above.
    Gated by the same static capability check `run_discovery` uses -- this
    is a read over the same ledger, so the same "can we even reach Core's
    CLI and ledger root" prerequisites apply. Raises
    `DiscoveryOrchestrationError` on failure, sanitized the same way
    `run_discovery` sanitizes `KeCommandError`; a caller that wants to
    degrade gracefully (e.g. render "no history available" rather than
    fail the whole page) should catch it, not let it propagate to a
    visitor.
    """

    capability = evaluate_discovery_capability(settings)
    if not capability.available:
        raise DiscoveryOrchestrationError(
            capability.visitor_message or "Discovery is unavailable on this deployment."
        )

    executable = _resolve_executable(settings.ke_executable)
    assert executable is not None

    try:
        return federated_discover_history(
            research_question_id,
            ledger_root=Path(settings.federated_discovery_ledger_root),
            ke_executable=executable,
            execution_budget=ExecutionBudget.from_timeout(
                settings.discovery_request_timeout_seconds
            ),
        )
    except KeCommandError as exc:
        raise DiscoveryOrchestrationError(
            "Search history could not be read for this deployment."
        ) from exc


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


def _evaluate_ledger_storage(settings: Settings) -> DiscoveryCapability:
    """Mirror `ai_orchestration._evaluate_session_storage`'s local/persistent split.

    WEB-FRD-5 item 6: without this, a Render redeploy silently wipes the
    ledger and "since your last search" would be quietly false rather than
    honestly reporting "no history yet" -- the exact failure mode AI-O15
    already named and rejected for Research Sessions.
    """

    ledger_path = Path(settings.federated_discovery_ledger_root)
    if settings.discovery_ledger_storage_mode == "local":
        if not _ledger_root_is_usable(ledger_path):
            return _unavailable("ledger_root_unavailable")
        return DiscoveryCapability(available=True)

    persistent_root_value = settings.discovery_ledger_persistent_root
    if persistent_root_value is None or not persistent_root_value.strip():
        return _unavailable("persistent_ledger_root_unavailable")

    persistent_root = Path(persistent_root_value.strip())
    if not persistent_root.is_absolute() or not ledger_path.is_absolute():
        return _unavailable("persistent_ledger_path_invalid")
    if not persistent_root.is_dir() or not os.access(persistent_root, os.W_OK):
        return _unavailable("persistent_ledger_root_unavailable")

    try:
        resolved_root = persistent_root.resolve(strict=True)
        resolved_ledger = ledger_path.resolve(strict=False)
    except OSError:
        return _unavailable("persistent_ledger_path_invalid")

    if resolved_ledger == resolved_root or not resolved_ledger.is_relative_to(resolved_root):
        return _unavailable("persistent_ledger_path_invalid")

    if not _ledger_root_is_usable(ledger_path):
        return _unavailable("ledger_root_unavailable")

    return DiscoveryCapability(available=True)


__all__ = [
    "DiscoveryCapability",
    "DiscoveryOrchestrationError",
    "evaluate_discovery_capability",
    "run_discovery",
    "run_discovery_history",
    "run_guarded_discovery",
]
