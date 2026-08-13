from __future__ import annotations

import pytest

from knowledge_engine_web.ai_guardrails import AIAdmissionError, AIRequestGuard


def test_guard_rejects_concurrent_work_and_releases_the_slot() -> None:
    guard = AIRequestGuard(clock=lambda: 10.0)
    with (
        guard.admit(
            "client-a",
            max_concurrent_requests=1,
            rate_limit_requests=10,
            rate_limit_window_seconds=60.0,
        ),
        pytest.raises(AIAdmissionError) as raised,
        guard.admit(
            "client-b",
            max_concurrent_requests=1,
            rate_limit_requests=10,
            rate_limit_window_seconds=60.0,
        ),
    ):
        pytest.fail("a second request must not be admitted")

    assert raised.value.reason_code == "concurrency_limit_reached"
    with guard.admit(
        "client-b",
        max_concurrent_requests=1,
        rate_limit_requests=10,
        rate_limit_window_seconds=60.0,
    ):
        pass


def test_guard_releases_the_slot_after_runner_failure() -> None:
    guard = AIRequestGuard(clock=lambda: 10.0)
    with (
        pytest.raises(RuntimeError, match="failed"),
        guard.admit(
            "client-a",
            max_concurrent_requests=1,
            rate_limit_requests=10,
            rate_limit_window_seconds=60.0,
        ),
    ):
        raise RuntimeError("failed")

    with guard.admit(
        "client-b",
        max_concurrent_requests=1,
        rate_limit_requests=10,
        rate_limit_window_seconds=60.0,
    ):
        pass


def test_guard_rate_limits_only_admitted_requests_until_window_expires() -> None:
    now = [10.0]
    guard = AIRequestGuard(clock=lambda: now[0])
    with guard.admit(
        "client-a",
        max_concurrent_requests=1,
        rate_limit_requests=2,
        rate_limit_window_seconds=60.0,
    ):
        pass
    with guard.admit(
        "client-a",
        max_concurrent_requests=1,
        rate_limit_requests=2,
        rate_limit_window_seconds=60.0,
    ):
        pass
    with (
        pytest.raises(AIAdmissionError) as raised,
        guard.admit(
            "client-a",
            max_concurrent_requests=1,
            rate_limit_requests=2,
            rate_limit_window_seconds=60.0,
        ),
    ):
        pytest.fail("the third admitted request must be rate limited")

    assert raised.value.reason_code == "rate_limit_reached"
    now[0] = 70.0
    with guard.admit(
        "client-a",
        max_concurrent_requests=1,
        rate_limit_requests=2,
        rate_limit_window_seconds=60.0,
    ):
        pass


def test_guard_tracks_clients_independently() -> None:
    guard = AIRequestGuard(clock=lambda: 10.0)
    with guard.admit(
        "client-a",
        max_concurrent_requests=1,
        rate_limit_requests=1,
        rate_limit_window_seconds=60.0,
    ):
        pass
    with guard.admit(
        "client-b",
        max_concurrent_requests=1,
        rate_limit_requests=1,
        rate_limit_window_seconds=60.0,
    ):
        pass
