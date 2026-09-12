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
`docs/agent-development-policy.md` section 1. `/discover`'s federated
discovery capability is a separate gate from Ask's Research capability, but
the fixture server leaves it equally unconfigured (no `ke` CLI), so its form
is reachable in the same honest fail-closed posture.
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


def _first_text_input_style(page: Page) -> dict[str, str]:
    result = page.locator('input[type="text"]').first.evaluate(
        """(el) => {
            const style = window.getComputedStyle(el);
            return {
                outlineStyle: style.outlineStyle,
                boxShadow: style.boxShadow,
                borderColor: style.borderColor,
                backgroundColor: style.backgroundColor,
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


def test_ask_page_autofocuses_question_input_and_supports_reverse_tab(
    page: Page, live_app: str
) -> None:
    # The question field carries `autofocus`, so a real browser focuses it
    # immediately on load. Shift+Tab must still let a keyboard user traverse
    # backward through the real document order without programmatic focus.
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    assert focused["id"] == "q"

    page.keyboard.press("Shift+Tab")
    focused = _focused_element_info(page)
    assert focused["tag"] in {"A", "SUMMARY"}
    assert focused["id"] != "q"


def test_ask_form_input_is_keyboard_reachable_and_focus_visible(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask")

    # The Ask input autofocuses. Capture its focused style first, then use only
    # real keyboard traversal to move away and capture the ordinary style.
    focused_style = _first_text_input_style(page)
    page.keyboard.press("Shift+Tab")
    focused = _focused_element_info(page)
    assert focused["id"] != "q"
    normal_style = _first_text_input_style(page)

    # Tab must return to the input, and the keyboard-focused rendering must be
    # visibly distinguishable from its unfocused rendering.
    page.keyboard.press("Tab")
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    assert focused["id"] == "q"

    assert focused_style != normal_style
    assert (
        focused_style["outlineStyle"] != normal_style["outlineStyle"]
        or focused_style["boxShadow"] != normal_style["boxShadow"]
        or focused_style["borderColor"] != normal_style["borderColor"]
        or focused_style["backgroundColor"] != normal_style["backgroundColor"]
    )


def test_discover_page_autofocuses_query_input_and_supports_reverse_tab(
    page: Page, live_app: str
) -> None:
    # `/discover` reaches its honest fail-closed "Discovery is unavailable on
    # this deployment" state without any Research/AI capability configured
    # (same posture as the Ask keyboard tests above), so this real form is
    # reachable and worth the same keyboard-navigation evidence Ask already
    # has -- see `docs/agent-development-policy.md` section 1.
    page.goto(live_app + "/discover")
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    assert focused["id"] == "q"

    page.keyboard.press("Shift+Tab")
    focused = _focused_element_info(page)
    assert focused["tag"] in {"A", "SUMMARY"}
    assert focused["id"] != "q"


def test_discover_form_input_is_keyboard_reachable_and_focus_visible(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/discover")

    focused_style = _first_text_input_style(page)
    page.keyboard.press("Shift+Tab")
    focused = _focused_element_info(page)
    assert focused["id"] != "q"
    normal_style = _first_text_input_style(page)

    page.keyboard.press("Tab")
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    assert focused["id"] == "q"

    assert focused_style != normal_style
    assert (
        focused_style["outlineStyle"] != normal_style["outlineStyle"]
        or focused_style["boxShadow"] != normal_style["boxShadow"]
        or focused_style["borderColor"] != normal_style["borderColor"]
        or focused_style["backgroundColor"] != normal_style["backgroundColor"]
    )


def test_discover_submit_button_is_reachable_by_tab_from_query_input(
    page: Page, live_app: str
) -> None:
    # The unavailable-capability notice sits between the query input and the
    # submit button in document order (see `discover.html`); it is plain text
    # with no tabbable element, so Tab from the input must land on the real
    # submit button next, not skip past it or get stuck on the notice.
    page.goto(live_app + "/discover")
    page.keyboard.press("Tab")
    focused = _focused_element_info(page)
    assert focused["tag"] == "BUTTON"
    assert focused["id"] == "discover-submit"
