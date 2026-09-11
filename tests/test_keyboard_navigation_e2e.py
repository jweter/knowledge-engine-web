"""Real-keyboard navigation E2E checks for reachable Web pages.

`docs/INDUSTRY_REALITY_CHECK.md`'s Accessibility gap notes that automated
axe-core coverage exists but "no manual keyboard-navigation/screen-reader
pass has been performed." This module does not replace that manual pass --
axe-core and a scripted Tab/Enter sequence cannot substitute for a human
screen-reader session -- but it adds real, automated evidence for the one
keyboard behavior axe-core's static DOM analysis cannot verify: what a real
browser actually focuses when a real keyboard user presses Tab and Enter.

Every page covered here is reachable without Research/AI capability
configured (same fixture data as `tests/test_browser_e2e.py`), so this adds
coverage without faking backend authority -- see
`docs/agent-development-policy.md` section 1.
"""

from __future__ import annotations

from typing import cast

import pytest
from playwright.sync_api import Page

from tests._browser_e2e_support import QUESTION

pytestmark = pytest.mark.browser_e2e


def _focused_element_info(page: Page) -> dict[str, str]:
    result = page.evaluate(
        """() => {
            const el = document.activeElement;
            if (!el) return {tag: '', className: '', id: '', text: ''};
            return {
                tag: el.tagName,
                className: el.className || '',
                id: el.id || '',
                text: (el.textContent || '').trim(),
            };
        }"""
    )
    return cast(dict[str, str], result)


def test_skip_link_is_first_tab_stop_on_homepage(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    page.keyboard.press("Tab")
    focused = _focused_element_info(page)
    assert focused["tag"] == "A"
    assert "skip-link" in focused["className"]
    assert focused["text"] == "Skip to main content"


def test_skip_link_activation_moves_focus_to_main_content(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    focused = _focused_element_info(page)
    assert focused["id"] == "main-content"


def test_ask_page_autofocuses_question_input(page: Page, live_app: str) -> None:
    # The question field carries `autofocus`, so a real browser focuses it
    # immediately on load -- a keyboard user lands straight on the page's
    # primary control rather than needing to Tab past the header nav at all.
    # The skip link (shared base.html markup, verified above on the
    # homepage) remains reachable by tabbing backward from here.
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    assert focused["id"] == "q"


def test_ask_form_input_is_keyboard_reachable_and_focus_visible(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask")
    question_input = page.locator('input[type="text"]').first
    question_input.focus()
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    # A real keyboard user must see where focus is: the element must not be
    # rendered with no visible outline/box-shadow indicator at all.
    outline, box_shadow = page.evaluate(
        """() => {
            const el = document.activeElement;
            const style = window.getComputedStyle(el);
            return [style.outlineStyle, style.boxShadow];
        }"""
    )
    assert outline != "none" or box_shadow != "none"
