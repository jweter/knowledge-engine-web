"""Real-Chromium coverage of the one-question online evidence preview page.

The POST to ``/research/online-evidence`` is stubbed at the browser network
layer (no provider or Core call), so these tests exercise the real page,
real static JavaScript and real DOM rendering contract only.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from playwright.sync_api import Page, Route

pytestmark = pytest.mark.browser_e2e

HOSTILE = '<img src=x onerror="window.__pwned=1">'


def _payload(*, claims: bool = True) -> dict[str, Any]:
    sources = [
        {
            "source_id": "s1",
            "url": "https://example.org/paper-1",
            "provider": "pubmed",
            "retrieved_at": "2026-11-02T12:00:00+00:00",
            "status": "retrieved",
            "content_sha256": "a" * 64,
            "failure_reason": None,
            "title": HOSTILE,
        },
        {
            "source_id": "s2",
            "url": "javascript:window.__pwned=1",
            "provider": "crossref",
            "retrieved_at": "2026-11-02T12:00:00+00:00",
            "status": "failed",
            "content_sha256": None,
            "failure_reason": "timeout",
            "title": None,
        },
    ]
    return {
        "status": "content_checked_retrieval_only",
        "research_report_complete": False,
        "validation_scope": "source_content_consistency_not_scientific_truth",
        "search_run_id": "run-e2e",
        "source_status_summary": {
            "scope": "returned_sources_only_not_exhaustive_provider_coverage",
            "source_count": 2,
            "status_counts": {"retrieved": 1, "unavailable": 0, "not_permitted": 0, "failed": 1},
            "providers": [],
        },
        "evidence": {
            "question": "q",
            "sources": sources,
            "excerpts": [{"excerpt_id": "x1", "source_id": "s1", "text": "Excerpt text."}],
            "claims": (
                [
                    {
                        "text": "A cited claim.",
                        "status": "supported_by_excerpt",
                        "citations": [{"excerpt_id": "x1"}],
                    }
                ]
                if claims
                else []
            ),
        },
    }


def _stub(page: Page, status: int, body: dict[str, Any]) -> None:
    def handler(route: Route) -> None:
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    page.route("**/research/online-evidence", handler)


def _ask(page: Page, base: str) -> None:
    page.goto(base + "/research/online")
    page.fill("#online-evidence-question", "does x affect y?")
    page.click("#online-evidence-submit")


def test_results_render_sources_and_citations_without_executing_provider_html(
    page: Page, live_app_with_online_evidence: str
) -> None:
    _stub(page, 200, _payload())
    _ask(page, live_app_with_online_evidence)
    page.locator("#online-evidence-results").wait_for(state="visible")

    assert "retrieval only" in page.locator("#online-evidence-progress").inner_text()
    assert (
        "not exhaustive provider coverage" in page.locator("#online-evidence-summary").inner_text()
    )
    # Hostile provider-supplied title is inert text, never parsed as markup.
    assert HOSTILE in page.locator("#src-s1 h3").inner_text()
    assert page.locator("#online-evidence-sources img").count() == 0
    assert page.evaluate("window.__pwned") is None
    # Only http(s) URLs become links; a javascript: URL stays plain text.
    assert page.locator('#src-s1 a[href="https://example.org/paper-1"]').count() == 1
    assert page.locator("#src-s2 a").count() == 0
    assert "Not usable as evidence: timeout" in page.locator("#src-s2").inner_text()
    # The citation links back to the exact source card it came from.
    link = page.locator('#online-evidence-claims a[href="#src-s1"]')
    assert link.count() == 1
    assert "Excerpt text." in page.locator("#online-evidence-claims blockquote").inner_text()
    assert page.locator("#online-evidence-submit").is_enabled()


def test_no_claims_states_absence_is_not_evidence_of_absence(
    page: Page, live_app_with_online_evidence: str
) -> None:
    _stub(page, 200, _payload(claims=False))
    _ask(page, live_app_with_online_evidence)
    page.locator("#online-evidence-results").wait_for(state="visible")
    empty = page.locator("#online-evidence-claims-empty")
    assert empty.is_visible()
    assert "Absence of claims is not evidence of absence" in empty.inner_text()


def test_service_error_is_announced_and_hides_results(
    page: Page, live_app_with_online_evidence: str
) -> None:
    _stub(page, 429, {"detail": "Online evidence is busy processing requests."})
    _ask(page, live_app_with_online_evidence)
    page.wait_for_function(
        "document.getElementById('online-evidence-error').textContent.length > 0"
    )
    assert "busy processing" in page.locator("#online-evidence-error").inner_text()
    assert page.locator("#online-evidence-results").is_hidden()
    assert page.locator("#online-evidence-submit").is_enabled()


def test_blank_question_is_rejected_client_side_without_a_request(
    page: Page, live_app_with_online_evidence: str
) -> None:
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url) if "online-evidence" in r.url else None)
    page.goto(live_app_with_online_evidence + "/research/online")
    page.evaluate("document.getElementById('online-evidence-question').required = false")
    page.fill("#online-evidence-question", "   ")
    page.click("#online-evidence-submit")
    assert page.locator("#online-evidence-error").inner_text() == "Enter a research question."
    assert not any(u.endswith("/research/online-evidence") for u in requests)
