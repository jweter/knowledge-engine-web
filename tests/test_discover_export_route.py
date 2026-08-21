"""Route-level tests for `/discover/export.md` and `/discover/export.json`.

Reuses `test_discover_route.py`'s fixture/monkeypatch conventions (patching
`main.run_guarded_discovery` and `main.evaluate_discovery_capability`) so
these tests exercise the exact same result data the `/discover` page route
renders, confirming the export carries the same coverage-limitation facts.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from knowledge_engine_web import main
from knowledge_engine_web.ai_guardrails import AIAdmissionError
from knowledge_engine_web.discovery_orchestration import DiscoveryOrchestrationError
from knowledge_engine_web.main import app
from tests.test_discover_route import (
    _available_capability,
    _discovery_result,
    _unavailable_capability,
)


def test_markdown_export_requires_a_query() -> None:
    response = TestClient(app).get("/discover/export.md")

    assert response.status_code == 400


def test_json_export_requires_a_query() -> None:
    response = TestClient(app).get("/discover/export.json")

    assert response.status_code == 400


def test_markdown_export_reports_unavailable_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _unavailable_capability()
    )

    response = TestClient(app).get("/discover/export.md", params={"q": "semaglutide"})

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()


def test_markdown_export_carries_provider_reason_and_degraded_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main, "run_guarded_discovery", lambda settings, query, **kwargs: _discovery_result()
    )

    response = TestClient(app).get("/discover/export.md", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert (
        'attachment; filename="discovery-run-abc-123.md"' in response.headers["content-disposition"]
    )
    body = response.text
    assert "degraded / partial" in body
    assert "rate limited" in body
    assert "provider\\_rate\\_limited" in body
    assert "A Trial of Semaglutide for Body Weight Reduction" in body


def test_json_export_carries_provider_reason_and_degraded_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main, "run_guarded_discovery", lambda settings, query, **kwargs: _discovery_result()
    )

    response = TestClient(app).get("/discover/export.json", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert (
        'attachment; filename="discovery-run-abc-123.json"'
        in response.headers["content-disposition"]
    )
    payload = response.json()
    assert payload["completeness"] == "partial"
    openalex = next(p for p in payload["provider_coverage"] if p["provider"] == "openalex")
    assert openalex["label"] == "rate limited"
    assert openalex["reason"] == "provider_rate_limited"
    assert payload["candidates"][0]["title"] == ("A Trial of Semaglutide for Body Weight Reduction")


def test_json_export_carries_retraction_state_shown_on_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(
            observation_flags=(
                SimpleNamespace(
                    provider="crossref", retracted=True, preprint=None, preprint_version=None
                ),
            )
        ),
    )

    response = TestClient(app).get("/discover/export.json", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidates"][0]["publication_status"]["retraction_state"] == "retracted"


def test_markdown_export_reports_rate_limit_admission_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )

    def fail(settings: object, query: str, **kwargs: object) -> None:
        raise AIAdmissionError("rate_limit_reached", "Discovery has received too many requests.")

    monkeypatch.setattr(main, "run_guarded_discovery", fail)

    response = TestClient(app).get("/discover/export.md", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 429
    assert "too many requests" in response.json()["detail"]


def test_markdown_export_reports_orchestration_error_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )

    def fail(settings: object, query: str, **kwargs: object) -> None:
        raise DiscoveryOrchestrationError("Discovery could not complete this request.")

    monkeypatch.setattr(main, "run_guarded_discovery", fail)

    response = TestClient(app).get("/discover/export.json", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 502
    assert response.json()["detail"] == "Discovery could not complete this request."


def test_discover_page_links_to_both_export_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main, "run_guarded_discovery", lambda settings, query, **kwargs: _discovery_result()
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "/discover/export.md?q=" in body
    assert "/discover/export.json?q=" in body
