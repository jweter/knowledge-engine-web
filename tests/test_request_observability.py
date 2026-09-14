from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_engine_web.main import app
from knowledge_engine_web.observability import REQUEST_ID_HEADER, RESPONSE_TIME_HEADER, logger
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
