"""Real-browser coverage for WCAG 3.2.1 (On Focus) and 3.2.2 (On Input).

The tests deliberately exercise a *new* focus transition even though the Ask
and Discover query inputs use ``autofocus``. They also type real sequential
keystrokes and observe long enough for a conventional debounced input handler
to run. That keeps the regression coverage representative of user behavior
instead of only checking DOM value assignment.

What remains manual (per the accessibility checklist): any other form control
this repository adds in the future that could introduce an on-focus/on-input
context change.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.browser_e2e

_INPUT_OBSERVATION_MS = 750


def _move_focus_to_neutral_body(page: Page) -> None:
    """Move focus away from an autofocus input before explicitly refocusing it."""
    page.locator("body").evaluate(
        """body => {
            body.setAttribute('tabindex', '-1');
            body.focus();
        }"""
    )
    assert page.evaluate("document.activeElement === document.body")


def test_focusing_the_ask_question_input_does_not_navigate(page: Page, live_app: str) -> None:
    expected_url = live_app + "/ask"
    page.goto(expected_url)
    # Catch an unexpected context change caused by the initial autofocus itself.
    assert page.url == expected_url
    _move_focus_to_neutral_body(page)
    before_url = page.url

    page.locator("#q").focus()
    page.wait_for_timeout(150)

    assert page.url == before_url


def test_typing_into_the_ask_question_input_does_not_navigate(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask")
    before_url = page.url

    page.locator("#q").press_sequentially("does semaglutide increase IQ?", delay=20)
    page.wait_for_timeout(_INPUT_OBSERVATION_MS)

    assert page.url == before_url
    assert page.locator("#ask-running-status").is_hidden()


def test_focusing_the_discover_query_input_does_not_navigate(page: Page, live_app: str) -> None:
    expected_url = live_app + "/discover"
    page.goto(expected_url)
    # Catch an unexpected context change caused by the initial autofocus itself.
    assert page.url == expected_url
    _move_focus_to_neutral_body(page)
    before_url = page.url

    page.locator("#q").focus()
    page.wait_for_timeout(150)

    assert page.url == before_url


def test_typing_into_the_discover_query_input_does_not_navigate(page: Page, live_app: str) -> None:
    page.goto(live_app + "/discover")
    before_url = page.url

    page.locator("#q").press_sequentially("GLP-1 receptor agonist weight loss", delay=20)
    page.wait_for_timeout(_INPUT_OBSERVATION_MS)

    assert page.url == before_url
    assert page.locator("#discover-running-status").is_hidden()
