from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from knowledge_engine_web.main import app
from knowledge_engine_web.observability import (
    REQUEST_ID_HEADER,
    RESPONSE_TIME_HEADER,
    RequestObservabilityMiddleware,
    install_exception_handler_wrappers,
    logger,
)
from tests._fixtures import build_engine

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE
)


def _database_url(tmp_path: Path) -> str:
    build_engine(tmp_path)
    return f"sqlite:///{tmp_path / 'fixture'}.sqlite3"


def test_response_gets_a_generated_request_id_and_timing_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/graph")

    assert response.status_code == 200
    assert _UUID4_RE.match(response.headers[REQUEST_ID_HEADER])
    assert float(response.headers[RESPONSE_TIME_HEADER]) >= 0.0


def test_inbound_request_id_is_echoed_back_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/graph", headers={REQUEST_ID_HEADER: "caller-supplied-id-1"})

    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id-1"


def test_request_gets_a_correlated_log_line_with_method_path_status_and_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    with caplog.at_level(logging.INFO, logger=logger.name):
        response = TestClient(app).get(
            "/graph", headers={REQUEST_ID_HEADER: "caller-supplied-id-2"}
        )

    assert len(caplog.records) == 1
    message = caplog.records[0].message
    assert "request_id=caller-supplied-id-2" in message
    assert "method=GET" in message
    assert "path=/graph" in message
    assert f"status={response.status_code}" in message
    assert "duration_ms=" in message


def test_a_response_the_alpha_auth_gate_itself_produces_still_gets_a_request_id_and_log_line(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("KE_WEB_ALPHA_USERNAME", "tester")
    monkeypatch.setenv("KE_WEB_ALPHA_PASSWORD", "secret")

    with caplog.at_level(logging.INFO, logger=logger.name):
        response = TestClient(app).get("/graph")

    assert response.status_code == 401
    assert _UUID4_RE.match(response.headers[REQUEST_ID_HEADER])
    assert len(caplog.records) == 1
    assert "status=401" in caplog.records[0].message


def test_unhandled_exception_response_still_gets_request_id_header() -> None:
    isolated_app = FastAPI()
    install_exception_handler_wrappers(isolated_app)

    @isolated_app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("boom")

    isolated_app.add_middleware(RequestObservabilityMiddleware)

    response = TestClient(isolated_app, raise_server_exceptions=False).get(
        "/boom",
        headers={REQUEST_ID_HEADER: "caller-supplied-id-3"},
    )

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id-3"
    assert float(response.headers[RESPONSE_TIME_HEADER]) >= 0.0


def test_unhandled_exception_preserves_a_registered_exception_handler_response() -> None:
    isolated_app = FastAPI()
    install_exception_handler_wrappers(isolated_app)

    @isolated_app.exception_handler(RuntimeError)
    async def _runtime_error_handler(*_: object) -> JSONResponse:
        return JSONResponse({"detail": "custom-runtime-error"}, status_code=500)

    @isolated_app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("boom")

    install_exception_handler_wrappers(isolated_app)
    isolated_app.add_middleware(RequestObservabilityMiddleware)

    response = TestClient(isolated_app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "custom-runtime-error"}
    assert REQUEST_ID_HEADER in response.headers


def test_exception_handler_failures_are_not_swallowed_by_the_middleware() -> None:
    isolated_app = FastAPI()
    install_exception_handler_wrappers(isolated_app)

    @isolated_app.exception_handler(RuntimeError)
    async def _runtime_error_handler(*_: object) -> JSONResponse:
        raise ValueError("handler boom")

    @isolated_app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("boom")

    install_exception_handler_wrappers(isolated_app)
    isolated_app.add_middleware(RequestObservabilityMiddleware)

    with pytest.raises(ValueError, match="handler boom"):
        TestClient(isolated_app).get("/boom")


def test_unhandled_exception_with_context_still_uses_the_fallback_response() -> None:
    isolated_app = FastAPI()
    install_exception_handler_wrappers(isolated_app)

    @isolated_app.get("/boom")
    def _boom() -> None:
        try:
            raise ValueError("inner")
        except ValueError as exc:
            raise RuntimeError("boom") from exc

    isolated_app.add_middleware(RequestObservabilityMiddleware)

    response = TestClient(isolated_app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert REQUEST_ID_HEADER in response.headers


def test_started_response_is_not_followed_by_a_fallback_response() -> None:
    async def _partial_response_then_fail(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 500, "headers": []})
        raise RuntimeError("boom after start")

    middleware = RequestObservabilityMiddleware(_partial_response_then_fail)
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/boom",
        "raw_path": b"/boom",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
    }
    sent_messages: list[Message] = []

    async def _receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _send(message: Message) -> None:
        sent_messages.append(message)

    with pytest.raises(RuntimeError, match="boom after start"):
        asyncio.run(middleware(scope, _receive, _send))

    assert [message["type"] for message in sent_messages] == ["http.response.start"]
    raw_headers = dict(sent_messages[0]["headers"])
    assert b"x-request-id" in raw_headers
    assert b"x-response-time-ms" in raw_headers
