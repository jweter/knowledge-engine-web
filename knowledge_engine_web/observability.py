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

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

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


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Log method/path/status/duration and propagate a request-correlation ID.

    Reuses an inbound `X-Request-ID` if a caller already minted one, so a
    client-side trace and this repository's server log can be joined;
    otherwise mints a fresh one. Registered outermost (see `main.py`) so it
    still records a request-ID and duration for responses the alpha-auth
    gate itself produces (e.g. 401), not only successful ones.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        started_at = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.monotonic() - started_at) * 1000
            logger.exception(
                "request_id=%s method=%s path=%s status=unhandled_exception duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.monotonic() - started_at) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[RESPONSE_TIME_HEADER] = f"{duration_ms:.1f}"
        logger.info(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
