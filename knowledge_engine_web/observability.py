"""Request-level observability: a correlation ID and duration for every request.

`docs/INDUSTRY_REALITY_CHECK.md`'s Observability/performance gap calls for
client- and operator-visible timing on "request intake" and a shared ID so a
slow request can be traced end to end. The Research/AI path already reports
its own funnel/latency fields (`research_jobs.py`, `ask.html`) once a
session exists, but that is entirely gated on optional AI capability -- a
plain indexed Ask, Discover, or any other route got no timing or
correlation ID at all, Research capability or not. This module closes that
generic gap without touching the Research/AI path.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator, MutableMapping
from inspect import iscoroutinefunction
from typing import Any, cast

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
RESPONSE_TIME_HEADER = "X-Response-Time-Ms"

logger = logging.getLogger("knowledge_engine_web.request")
logger.setLevel(logging.INFO)
if not logger.handlers:
    # A dedicated handler so this line is operator-visible (stderr, captured
    # by Docker/Render logs) regardless of whether the process configures
    # root/uvicorn logging -- see `docs/deployment.md`. `propagate = False`
    # avoids a duplicate line if a host application later configures root
    # logging too.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.propagate = False

type ExceptionHandler = Callable[[Request, Any], Response | Awaitable[Response] | None]
_EXCEPTION_HANDLER_FAILED_KEY = "request_observability_exception_handler_failed"
_HANDLER_WRAPPED_ATTR = "_ke_request_observability_wrapped"
_HANDLER_MAP_WRAPPED_ATTR = "_ke_request_observability_handler_map_wrapped"


async def _run_exception_handler(
    handler: ExceptionHandler, request: Request, exc: Exception
) -> Response | None:
    if iscoroutinefunction(handler):
        async_handler = cast(Callable[[Request, Exception], Awaitable[Response | None]], handler)
        return await async_handler(request, exc)
    sync_handler = cast(Callable[[Request, Exception], Response | None], handler)
    return await run_in_threadpool(sync_handler, request, exc)


def _wrap_exception_handler(handler: ExceptionHandler) -> ExceptionHandler:
    if getattr(handler, _HANDLER_WRAPPED_ATTR, False):
        return handler

    async def wrapped_handler(request: Request, exc: Exception) -> Response | None:
        try:
            return await _run_exception_handler(handler, request, exc)
        except Exception:
            request.scope.setdefault("state", {})[_EXCEPTION_HANDLER_FAILED_KEY] = True
            raise

    setattr(wrapped_handler, _HANDLER_WRAPPED_ATTR, True)
    return cast(ExceptionHandler, wrapped_handler)


class WrappedExceptionHandlerMap(MutableMapping[Any, Any]):
    def __init__(self, handlers: MutableMapping[Any, Any]) -> None:
        self._handlers = handlers
        for key, handler in list(handlers.items()):
            self[key] = handler

    def __getitem__(self, key: Any) -> Any:
        return self._handlers[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self._handlers[key] = (
            _wrap_exception_handler(cast(ExceptionHandler, value)) if callable(value) else value
        )

    def __delitem__(self, key: Any) -> None:
        del self._handlers[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._handlers)

    def __len__(self) -> int:
        return len(self._handlers)


def install_exception_handler_wrappers(app: object) -> None:
    exception_handlers = getattr(app, "exception_handlers", None)
    if not isinstance(exception_handlers, MutableMapping):
        return

    if getattr(exception_handlers, _HANDLER_MAP_WRAPPED_ATTR, False):
        return

    wrapped_handlers = WrappedExceptionHandlerMap(exception_handlers)
    setattr(wrapped_handlers, _HANDLER_MAP_WRAPPED_ATTR, True)
    cast(Any, app).exception_handlers = wrapped_handlers


class RequestObservabilityMiddleware:
    """Log method/path/status/duration and propagate a request-correlation ID.

    Reuses an inbound `X-Request-ID` if a caller already minted one, so a
    client-side trace and this repository's server log can be joined;
    otherwise mints a fresh one. Registered outermost (see `main.py`) so it
    still records a request-ID and duration for responses the alpha-auth
    gate itself produces (e.g. 401), not only successful ones.
    """

    def __init__(
        self,
        app: ASGIApp,
    ) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = Headers(scope=scope).get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        started_at = time.monotonic()
        response_started = False
        status_code: int | None = None

        async def send_with_observability_headers(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                headers = MutableHeaders(raw=message["headers"])
                headers[REQUEST_ID_HEADER] = request_id
                headers[RESPONSE_TIME_HEADER] = f"{(time.monotonic() - started_at) * 1000:.1f}"
            await send(message)

        try:
            await self.app(scope, receive, send_with_observability_headers)
        except Exception:
            duration_ms = (time.monotonic() - started_at) * 1000
            logger.exception(
                "request_id=%s method=%s path=%s status=unhandled_exception duration_ms=%.1f",
                request_id,
                method,
                path,
                duration_ms,
            )
            if scope.setdefault("state", {}).pop(_EXCEPTION_HANDLER_FAILED_KEY, False):
                raise

            if response_started:
                raise

            fallback_response = PlainTextResponse("Internal Server Error", status_code=500)
            await fallback_response(scope, receive, send_with_observability_headers)
            return

        duration_ms = (time.monotonic() - started_at) * 1000
        rendered_status = status_code if status_code is not None else 0
        logger.info(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
            request_id,
            method,
            path,
            rendered_status,
            duration_ms,
        )
