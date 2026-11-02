"""Opt-in, bounded Web boundary for corpus-free Core online evidence.

This is a retrieval/evidence preview, not a synthesized Research Report.
No indexed SQLite corpus, Ollama service, or persistent bulk cache is required.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from knowledge_engine_ai.execution import ExecutionBudget, ExecutionBudgetExceeded
from knowledge_engine_ai.ke_client import (
    KeCommandError,
    OnlineResearchEvidenceResult,
    online_research_evidence,
)

from knowledge_engine_web.ai_guardrails import AIRequestGuard
from knowledge_engine_web.config import Settings

_GLOBAL_ONLINE_EVIDENCE_GUARD = AIRequestGuard()


@dataclass(frozen=True)
class OnlineEvidenceCapability:
    available: bool
    reason_code: str | None = None


class OnlineEvidenceOrchestrationError(RuntimeError):
    """Sanitized failure at the Core CLI / provider boundary."""


def evaluate_online_evidence_capability(settings: Settings) -> OnlineEvidenceCapability:
    """Static gate: never start a provider request while checking availability."""
    if not settings.online_evidence_enabled:
        return OnlineEvidenceCapability(False, "feature_disabled")
    if shutil.which(settings.ke_executable) is None:
        return OnlineEvidenceCapability(False, "core_cli_unavailable")
    return OnlineEvidenceCapability(True)


def run_guarded_online_evidence(
    settings: Settings,
    question: str,
    *,
    client_key: str,
    guard: AIRequestGuard | None = None,
) -> OnlineResearchEvidenceResult:
    """Retrieve content-checked online evidence under an independent guard.

    The result is source-linked input only. It cannot be presented as a
    scientifically verified conclusion or as a completed Research Report.
    """
    capability = evaluate_online_evidence_capability(settings)
    if not capability.available:
        raise OnlineEvidenceOrchestrationError("Online evidence is unavailable on this deployment.")
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise OnlineEvidenceOrchestrationError("Provide a question between 1 and 1000 characters.")

    request_guard = guard if guard is not None else _GLOBAL_ONLINE_EVIDENCE_GUARD
    with request_guard.admit(
        client_key,
        max_concurrent_requests=settings.online_evidence_max_concurrent_requests,
        rate_limit_requests=settings.online_evidence_rate_limit_requests,
        rate_limit_window_seconds=settings.online_evidence_rate_limit_window_seconds,
    ):
        try:
            return online_research_evidence(
                question.strip(),
                max_sources=settings.online_evidence_max_sources,
                ke_executable=settings.ke_executable,
                execution_budget=ExecutionBudget.from_timeout(
                    settings.online_evidence_request_timeout_seconds
                ),
            )
        except (KeCommandError, ExecutionBudgetExceeded, OSError) as exc:
            raise OnlineEvidenceOrchestrationError(
                "Online evidence retrieval or verification failed. No report was produced."
            ) from exc


def summarize_returned_online_sources(result: OnlineResearchEvidenceResult) -> dict[str, object]:
    """Count only sources actually returned by Core, not providers searched.

    These are retrieval statuses, never scientific certainty, exhaustive
    provider coverage, or a Research Report release gate.
    """
    statuses = ("retrieved", "unavailable", "not_permitted", "failed")
    totals = dict.fromkeys(statuses, 0)
    by_provider: dict[str, dict[str, int]] = {}
    for source in result.evidence.sources:
        if source.status not in totals:
            raise OnlineEvidenceOrchestrationError("Online evidence has an invalid source status.")
        totals[source.status] += 1
        counts = by_provider.setdefault(source.provider, dict.fromkeys(statuses, 0))
        counts[source.status] += 1
    return {
        "scope": "returned_sources_only_not_exhaustive_provider_coverage",
        "source_count": len(result.evidence.sources),
        "status_counts": totals,
        "providers": [
            {
                "provider": provider,
                "source_count": sum(counts.values()),
                "status_counts": counts,
            }
            for provider, counts in sorted(by_provider.items())
        ],
    }
