"""Real-browser coverage for WCAG 3.2.1 (On Focus) and 3.2.2 (On Input):
`docs/manual_accessibility_checklist.md` row 13 asks whether focusing or
typing into the Ask/Discover query input ever triggers an unexpected context
change (navigation, form submission) on its own, before the user explicitly
presses the submit button.

Both inputs use `autofocus` and are plain `<input type="text">` elements
inside a `<form method="get">` with no `onchange`/`oninput`/`onfocus`
handler in the templates and no such listener registered in the page's own
JavaScript (`ask.html`/`discover.html` only listen for the form's `submit`
event, to show a running-status message). A regression here would most
likely come from a future auto-submit-as-you-type feature, so this
mechanically proves the current behavior and guards it going forward.

What remains manual (per the checklist): any other form control this
repository adds in the future that could introduce an on-focus/on-input
context change.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.browser_e2e


def test_focusing_the_ask_question_input_does_not_navigate(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask")
    before_url = page.url

    page.locator("#q").focus()
    page.wait_for_timeout(150)

    assert page.url == before_url


def test_typing_into_the_ask_question_input_does_not_navigate(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask")
    before_url = page.url

    page.locator("#q").fill("does semaglutide increase IQ?")
    page.wait_for_timeout(150)

    assert page.url == before_url
    assert page.locator("#ask-running-status").is_hidden()


def test_focusing_the_discover_query_input_does_not_navigate(page: Page, live_app: str) -> None:
    page.goto(live_app + "/discover")
    before_url = page.url

    page.locator("#q").focus()
    page.wait_for_timeout(150)

    assert page.url == before_url


def test_typing_into_the_discover_query_input_does_not_navigate(page: Page, live_app: str) -> None:
    page.goto(live_app + "/discover")
    before_url = page.url

    page.locator("#q").fill("GLP-1 receptor agonist weight loss")
    page.wait_for_timeout(150)

    assert page.url == before_url
    assert page.locator("#discover-running-status").is_hidden()
