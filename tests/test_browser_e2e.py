"""Real headless-Chromium browser end-to-end tests for the Ask product path."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests._browser_e2e_support import EVIDENCE_RECORD_ID, PAPER_TITLE, QUESTION

pytestmark = pytest.mark.browser_e2e


def test_homepage_loads_the_real_application(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    assert "Knowledge Engine" in page.title()


def test_ask_shows_a_direct_indexed_match_and_an_honest_capability_notice(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    assert page.get_by_text("Direct match").first.is_visible()
    assert page.get_by_role("link", name=PAPER_TITLE).is_visible()
    citation_link = page.locator(f'a[href="/claims/{EVIDENCE_RECORD_ID}"]')
    assert citation_link.is_visible()
    assert "Broader Research is unavailable on this deployment" in page.content()


def test_citation_link_navigates_to_a_real_evidence_record_detail_page(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    page.locator(f'a[href="/claims/{EVIDENCE_RECORD_ID}"]').first.click()
    assert page.url == live_app + "/claims/" + EVIDENCE_RECORD_ID
    assert page.locator("h1", has_text=EVIDENCE_RECORD_ID).is_visible()
    assert "Semaglutide showed no statistically significant IQ change." in page.content()


def test_ask_with_no_matching_evidence_does_not_fabricate_an_answer(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")
    assert "No relevant papers found in the indexed corpus." in page.content()
    assert "Direct match" not in page.content()


def test_ask_page_is_usable_at_a_mobile_viewport(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    assert page.get_by_label("Question").is_visible()
    assert page.get_by_role("button", name="Ask").is_visible()
    citation_link = page.locator(f'a[href="/claims/{EVIDENCE_RECORD_ID}"]')
    assert citation_link.is_visible()
    body_width = page.evaluate("document.documentElement.scrollWidth")
    assert body_width <= 390, f"page overflows a 390px viewport (scrollWidth={body_width})"
