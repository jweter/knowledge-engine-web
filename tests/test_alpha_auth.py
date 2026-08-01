from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_engine_web.main import app
from tests._fixtures import build_engine


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _database_url(tmp_path: Path) -> str:
    build_engine(tmp_path)
    return f"sqlite:///{tmp_path / 'fixture'}.sqlite3"


def test_no_auth_required_when_alpha_credentials_are_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.delenv("KE_WEB_ALPHA_USERNAME", raising=False)
    monkeypatch.delenv("KE_WEB_ALPHA_PASSWORD", raising=False)

    response = TestClient(app).get("/graph")

    assert response.status_code == 200


def test_request_without_credentials_is_rejected_when_alpha_auth_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KE_WEB_ALPHA_USERNAME", "tester")
    monkeypatch.setenv("KE_WEB_ALPHA_PASSWORD", "secret")

    response = TestClient(app).get("/graph")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="Knowledge Engine alpha"'


def test_request_with_correct_credentials_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_ALPHA_USERNAME", "tester")
    monkeypatch.setenv("KE_WEB_ALPHA_PASSWORD", "secret")

    response = TestClient(app).get("/graph", headers=_basic_auth_header("tester", "secret"))

    assert response.status_code == 200


def test_request_with_wrong_password_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KE_WEB_ALPHA_USERNAME", "tester")
    monkeypatch.setenv("KE_WEB_ALPHA_PASSWORD", "secret")

    response = TestClient(app).get("/graph", headers=_basic_auth_header("tester", "wrong-password"))

    assert response.status_code == 401


def test_a_malformed_authorization_header_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KE_WEB_ALPHA_USERNAME", "tester")
    monkeypatch.setenv("KE_WEB_ALPHA_PASSWORD", "secret")

    response = TestClient(app).get("/graph", headers={"Authorization": "Bearer not-basic-auth"})

    assert response.status_code == 401


def test_fails_closed_when_only_username_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KE_WEB_ALPHA_USERNAME", "tester")
    monkeypatch.delenv("KE_WEB_ALPHA_PASSWORD", raising=False)

    response = TestClient(app).get("/graph")

    assert response.status_code == 500
