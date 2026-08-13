"""Process-local admission controls for the optional Research Copilot path."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class AIAdmissionError(RuntimeError):
    """One optional AI request was rejected before compute began."""

    def __init__(self, reason_code: str, visitor_message: str) -> None:
        super().__init__(visitor_message)
        self.reason_code = reason_code
        self.visitor_message = visitor_message


class AIRequestGuard:
    """A thread-safe single-process concurrency and fixed-window limiter."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._active_requests = 0
        self._accepted_at: dict[str, deque[float]] = defaultdict(deque)

    @contextmanager
    def admit(
        self,
        client_key: str,
        *,
        max_concurrent_requests: int,
        rate_limit_requests: int,
        rate_limit_window_seconds: float,
    ) -> Iterator[None]:
        """Admit one request or fail before any Research Copilot work starts."""

        now = self._clock()
        with self._lock:
            self._prune(now, rate_limit_window_seconds)
            if self._active_requests >= max_concurrent_requests:
                raise AIAdmissionError(
                    "concurrency_limit_reached",
                    "Research Copilot is already processing the maximum number of requests. "
                    "Please wait and try again. Deterministic retrieval results are still "
                    "shown below.",
                )

            accepted = self._accepted_at[client_key]
            if len(accepted) >= rate_limit_requests:
                raise AIAdmissionError(
                    "rate_limit_reached",
                    "Research Copilot has received too many requests recently. Please wait and "
                    "try again. Deterministic retrieval results are still shown below.",
                )

            accepted.append(now)
            self._active_requests += 1

        try:
            yield
        finally:
            with self._lock:
                self._active_requests -= 1

    def _prune(self, now: float, window_seconds: float) -> None:
        cutoff = now - window_seconds
        for key in tuple(self._accepted_at):
            accepted = self._accepted_at[key]
            while accepted and accepted[0] <= cutoff:
                accepted.popleft()
            if not accepted:
                del self._accepted_at[key]


__all__ = ["AIAdmissionError", "AIRequestGuard"]
