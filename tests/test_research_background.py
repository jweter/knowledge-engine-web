from __future__ import annotations

import time
from concurrent.futures import Future
from types import SimpleNamespace
from typing import cast

import pytest

import knowledge_engine_web.research_background as module
from knowledge_engine_web.ai_orchestration import WebResearchResult
from knowledge_engine_web.config import Settings
from knowledge_engine_web.research_background import (
    BackgroundResearchBusy,
    read_background_memory_state,
    start_background_research,
)


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("KE_WEB_AI_MAX_CONCURRENT_REQUESTS", "1")
    return Settings()


def _stub_result() -> WebResearchResult:
    return cast(WebResearchResult, SimpleNamespace())


def _stub_runner(
    settings: Settings,
    question: str,
    *,
    client_key: str,
    session_id: str,
) -> WebResearchResult:
    del settings, question, client_key, session_id
    return _stub_result()


def test_start_uses_exact_generated_id_for_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    captured: dict[str, str] = {}

    def runner(
        settings: Settings,
        question: str,
        *,
        client_key: str,
        session_id: str,
    ) -> WebResearchResult:
        del settings
        captured.update(question=question, client_key=client_key, session_id=session_id)
        return _stub_result()

    started = start_background_research(
        settings,
        "  Does creatine help?  ",
        client_key="client-1",
        runner=runner,
    )
    module._JOBS[started.session_id].future.result(timeout=2)

    assert captured["question"] == "Does creatine help?"
    assert captured["client_key"] == "client-1"
    assert captured["session_id"] == started.session_id
    assert started.status_url.endswith(started.session_id)


def test_active_capacity_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    pending: Future[WebResearchResult] = Future()
    monkeypatch.setattr(
        module,
        "_JOBS",
        {"occupied": module._BackgroundJob(pending, time.monotonic())},
    )

    with pytest.raises(BackgroundResearchBusy):
        start_background_research(
            settings,
            "Question?",
            client_key="client-1",
            runner=_stub_runner,
        )


def test_memory_state_reports_starting_job(monkeypatch: pytest.MonkeyPatch) -> None:
    pending: Future[WebResearchResult] = Future()
    monkeypatch.setattr(
        module,
        "_JOBS",
        {"session-1": module._BackgroundJob(pending, time.monotonic())},
    )

    state = read_background_memory_state("session-1")

    assert state is not None
    assert state.status == "starting"
    assert state.terminal is False
