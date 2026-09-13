"""Real-browser keyboard-navigation regression tests."""

from __future__ import annotations

from typing import cast

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.browser_e2e


def _focused_element_info(page: Page) -> dict[str, str]:
    return cast(
        dict[str, str],
        page.evaluate(
            """() => ({
                tag: document.activeElement?.tagName ?? '',
                id: document.activeElement?.id ?? '',
                href: document.activeElement?.getAttribute('href') ?? '',
            })"""
        ),
    )


def _first_text_input_style(page: Page) -> dict[str, str]:
    return cast(
        dict[str, str],
        page.locator("input[type='text'], input:not([type])").first.evaluate(
            """element => {
                const style = getComputedStyle(element);
                return {
                    outlineStyle: style.outlineStyle,
                    boxShadow: style.boxShadow,
                    borderColor: style.borderColor,
                    backgroundColor: style.backgroundColor,
                };
            }"""
        ),
    )


def test_skip_link_is_first_keyboard_target(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    page.keyboard.press("Tab")
    focused = _focused_element_info(page)
    assert focused["tag"] == "A"
    assert focused["href"] == "#main-content"


def test_skip_link_moves_focus_to_main_content(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    focused = _focused_element_info(page)
    assert focused["id"] == "main-content"


def test_question_input_is_keyboard_reachable(page: Page, live_app: str) -> None:
    # The question form lives on /ask; the landing page intentionally contains
    # no text input. /ask autofocuses q, which is itself keyboard reachability.
    page.goto(live_app + "/ask")
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    assert focused["id"] == "q"

    page.keyboard.press("Shift+Tab")
    assert _focused_element_info(page)["id"] != "q"
    page.keyboard.press("Tab")
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    assert focused["id"] == "q"


def test_question_input_has_visible_focus_style(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask")
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    assert focused["id"] == "q"
    focused_style = _first_text_input_style(page)

    page.keyboard.press("Shift+Tab")
    normal_style = _first_text_input_style(page)
    assert focused_style != normal_style


def test_discover_query_input_autofocus_and_reverse_tab(page: Page, live_app: str) -> None:
    page.goto(live_app + "/discover")
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    assert focused["id"] == "q"

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
    # /discover autofocuses the query input. Anchor the assertion to that
    # documented starting state so browser focus restoration/default focus
    # behavior cannot turn this into a test of the global navigation order.
    page.goto(live_app + "/discover")
    focused = _focused_element_info(page)
    assert focused["tag"] == "INPUT"
    assert focused["id"] == "q"

    page.keyboard.press("Tab")
    focused = _focused_element_info(page)
    assert focused["tag"] == "BUTTON"
    assert focused["id"] == "discover-submit"


def _hero_heading_animation_duration(page: Page) -> str:
    return cast(
        str,
        page.locator(".landing-hero-copy h1").evaluate(
            "element => getComputedStyle(element).animationDuration"
        ),
    )


def test_motion_toggle_is_keyboard_operable_and_stops_animation(page: Page, live_app: str) -> None:
    # WCAG 2.2.2 (Pause, Stop, Hide): the homepage's decorative constellation
    # background and headline animation run indefinitely and must be
    # user-pausable independent of the OS-level prefers-reduced-motion
    # setting. Regression-tests knowledge_constellation.js's #motion-toggle.
    page.goto(live_app + "/")

    toggle = page.locator("#motion-toggle")
    assert toggle.is_visible()
    assert toggle.get_attribute("aria-pressed") == "false"

    running_duration = _hero_heading_animation_duration(page)
    assert running_duration not in ("0s", "1e-06s")

    toggle.focus()
    focused = _focused_element_info(page)
    assert focused["id"] == "motion-toggle"

    page.keyboard.press("Enter")
    assert toggle.get_attribute("aria-pressed") == "true"
    assert "motion-paused" in (page.locator("body").get_attribute("class") or "")
    assert _hero_heading_animation_duration(page) == "1e-06s"

    # A second activation resumes motion.
    page.keyboard.press("Enter")
    assert toggle.get_attribute("aria-pressed") == "false"
    assert "motion-paused" not in (page.locator("body").get_attribute("class") or "")
    assert _hero_heading_animation_duration(page) not in ("0s", "1e-06s")


def test_motion_toggle_preference_persists_across_reload(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    toggle = page.locator("#motion-toggle")
    toggle.click()
    assert toggle.get_attribute("aria-pressed") == "true"

    page.reload()
    toggle = page.locator("#motion-toggle")
    assert toggle.get_attribute("aria-pressed") == "true"
    assert "motion-paused" in (page.locator("body").get_attribute("class") or "")
    assert _hero_heading_animation_duration(page) == "1e-06s"

    # A different real page (site-wide control, not homepage-only) honors
    # the same persisted preference on first load.
    page.goto(live_app + "/about")
    toggle = page.locator("#motion-toggle")
    assert toggle.get_attribute("aria-pressed") == "true"
    assert "motion-paused" in (page.locator("body").get_attribute("class") or "")
