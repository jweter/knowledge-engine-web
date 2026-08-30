"""Bounded process-local execution for durable Research Copilot sessions.

The durable source of truth remains knowledge-engine-ai's SQLite ResearchSession/
ResearchEvent store. This module only owns *active execution* so a browser request
can return before a long research run finishes. Once AI creates the caller-owned
session ID, Web's polling endpoint reads the durable store instead of this registry.

A process restart can interrupt an in-flight worker; it does not erase already
persisted session/events. Durable cross-redeploy *execution resumption* needs a real
worker/queue and is intentionally not claimed by this first WEB-GQR-4 slice.
"""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Protocol
from uuid import uuid4

from knowledge_engine_web.ai_guardrails import AIAdmissionError
from knowledge_engine_web.ai_orchestration import (
    AIOrchestrationError,
    WebResearchResult,
    run_guarded_ai_orchestration,
)
from knowledge_engine_web.config import Settings

_MAX_WORKERS = 8
_COMPLETED_JOB_RETENTION_SECONDS = 15 * 60
_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="ke-research")
_LOCK = Lock()


class BackgroundResearchRunner(Protocol):
    def __call__(
        self,
        settings: Settings,
        question: str,
        *,
        client_key: str,
        session_id: str,
    ) -> WebResearchResult: ...


@dataclass(frozen=True)
class BackgroundResearchStart:
    session_id: str
    status_url: str


@dataclass(frozen=True)
class BackgroundResearchMemoryState:
    session_id: str
    status: str
    terminal: bool
    visitor_message: str | None = None


@dataclass(frozen=True)
class _BackgroundJob:
    future: Future[WebResearchResult]
    created_monotonic: float


class BackgroundResearchBusy(RuntimeError):
    """The deployment's configured concurrent-research capacity is already occupied."""

    visitor_message = "Research mode is at capacity right now. Please try again shortly."


_JOBS: dict[str, _BackgroundJob] = {}


def start_background_research(
    settings: Settings,
    question: str,
    *,
    client_key: str,
    runner: BackgroundResearchRunner = run_guarded_ai_orchestration,
) -> BackgroundResearchStart:
    """Submit one bounded run and return the exact durable session identity AI will use."""

    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must be non-blank.")

    session_id = str(uuid4())
    now = time.monotonic()
    with _LOCK:
        _prune_completed_jobs(now)
        active_count = sum(not job.future.done() for job in _JOBS.values())
        configured_limit = max(1, settings.ai_max_concurrent_requests)
        if active_count >= min(configured_limit, _MAX_WORKERS):
            raise BackgroundResearchBusy(BackgroundResearchBusy.visitor_message)
        future = _EXECUTOR.submit(
            runner,
            settings,
            normalized_question,
            client_key=client_key,
            session_id=session_id,
        )
        _JOBS[session_id] = _BackgroundJob(future=future, created_monotonic=now)

    return BackgroundResearchStart(
        session_id=session_id,
        status_url=f"/ask/session/{session_id}",
    )


def read_background_memory_state(session_id: str) -> BackgroundResearchMemoryState | None:
    """Best-effort state before/without a durable session row.

    Successful runs should quickly become visible through the SQLite polling view. This
    fallback mainly prevents a newly-started browser poll from seeing a misleading 404
    during that handoff, and gives rate-limit/startup failures a visitor-safe terminal
    state while this Web process remains alive.
    """

    with _LOCK:
        job = _JOBS.get(session_id)
    if job is None:
        return None
    if not job.future.done():
        return BackgroundResearchMemoryState(
            session_id=session_id,
            status="starting",
            terminal=False,
        )

    try:
        job.future.result()
    except AIAdmissionError as exc:
        return BackgroundResearchMemoryState(
            session_id=session_id,
            status="rejected",
            terminal=True,
            visitor_message=exc.visitor_message,
        )
    except AIOrchestrationError as exc:
        return BackgroundResearchMemoryState(
            session_id=session_id,
            status="failed",
            terminal=True,
            visitor_message=str(exc),
        )
    except Exception:  # noqa: BLE001 - never expose unexpected worker internals to visitors.
        return BackgroundResearchMemoryState(
            session_id=session_id,
            status="failed",
            terminal=True,
            visitor_message="Research Copilot could not complete this request.",
        )

    return BackgroundResearchMemoryState(
        session_id=session_id,
        status="completed",
        terminal=True,
    )


def _prune_completed_jobs(now: float) -> None:
    expired = tuple(
        session_id
        for session_id, job in _JOBS.items()
        if job.future.done()
        and now - job.created_monotonic >= _COMPLETED_JOB_RETENTION_SECONDS
    )
    for session_id in expired:
        _JOBS.pop(session_id, None)


__all__ = [
    "BackgroundResearchBusy",
    "BackgroundResearchMemoryState",
    "BackgroundResearchStart",
    "read_background_memory_state",
    "start_background_research",
]
