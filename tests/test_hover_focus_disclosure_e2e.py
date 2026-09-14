"""Automated coverage for the objectively-checkable part of WCAG 2.2 AA
1.4.13 Content on Hover or Focus (`docs/manual_accessibility_checklist.md`
row 5), scoped to the site-wide header "Inspect" menu.

1.4.13 applies to additional content that appears *because of* hovering or
focusing a trigger. Whether such content is dismissible/hoverable/persistent
is exactly the kind of thing that needs a real browser. But whether the
"Inspect" menu is content-on-hover-or-focus at all is a plain, scriptable
fact: it is a native `<details>/<summary>` disclosure widget with no CSS
`:hover` rule and no hover/focus JavaScript listener anywhere in this
codebase (confirmed by inspection before writing this test) -- it only
opens on an explicit activation (click, or Enter/Space while focused), which
places it outside 1.4.13's scope entirely (the criterion's own note excludes
content whose visibility is controlled by explicit user action, not hover or
focus). If a future change made it hover- or focus-triggered, that would
both violate this criterion and be exactly what these tests catch.

This does not replace the manual checklist row: it establishes the
plain fact (hover/focus alone never reveals it) that the row's own
"Header Inspect dropdown" scope depends on, and additionally regression-
tests that the widget remains keyboard- and click-operable so removing this
gap does not silently reintroduce a different one.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.browser_e2e

_SUMMARY = "summary"
_FIRST_MENU_LINK = ".inspect-menu > div a"


def _menu_is_open(page: Page) -> bool:
    return bool(page.evaluate("() => document.querySelector('.inspect-menu').open"))


def _assert_menu_not_revealed_by_hover(page: Page, page_label: str) -> None:
    assert not _menu_is_open(page), f"{page_label}: Inspect menu unexpectedly open before test"
    page.hover(_SUMMARY)
    page.wait_for_timeout(150)
    assert not _menu_is_open(page), (
        f"{page_label}: hovering the Inspect summary opened its menu -- WCAG 1.4.13 "
        "Content on Hover or Focus would then apply to it"
    )
    assert not page.locator(_FIRST_MENU_LINK).first.is_visible(), (
        f"{page_label}: Inspect menu links became visible merely from hover"
    )


def _assert_menu_not_revealed_by_focus_alone(page: Page, page_label: str) -> None:
    page.locator(_SUMMARY).focus()
    page.wait_for_timeout(150)
    assert not _menu_is_open(page), (
        f"{page_label}: focusing the Inspect summary opened its menu without an explicit "
        "activation -- WCAG 1.4.13 Content on Hover or Focus would then apply to it"
    )


def _assert_menu_opens_and_closes_on_click(page: Page, page_label: str) -> None:
    page.click(_SUMMARY)
    assert _menu_is_open(page), f"{page_label}: clicking the Inspect summary did not open it"
    assert page.locator(_FIRST_MENU_LINK).first.is_visible(), (
        f"{page_label}: Inspect menu content is not visible/reachable once opened"
    )
    page.click(_SUMMARY)
    assert not _menu_is_open(page), (
        f"{page_label}: clicking the open Inspect summary did not close it"
    )


def _assert_menu_opens_and_closes_on_keyboard_activation(page: Page, page_label: str) -> None:
    page.locator(_SUMMARY).focus()
    page.keyboard.press("Enter")
    assert _menu_is_open(page), (
        f"{page_label}: activating the focused Inspect summary with Enter did not open it"
    )
    page.keyboard.press("Enter")
    assert not _menu_is_open(page), (
        f"{page_label}: a second Enter on the focused Inspect summary did not close it"
    )


def test_homepage_inspect_menu_not_revealed_by_hover(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    _assert_menu_not_revealed_by_hover(page, "Homepage")


def test_homepage_inspect_menu_not_revealed_by_focus_alone(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    _assert_menu_not_revealed_by_focus_alone(page, "Homepage")


def test_homepage_inspect_menu_click_toggles_open_and_closed(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    _assert_menu_opens_and_closes_on_click(page, "Homepage")


def test_homepage_inspect_menu_keyboard_toggles_open_and_closed(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    _assert_menu_opens_and_closes_on_keyboard_activation(page, "Homepage")


def test_about_inspect_menu_not_revealed_by_hover_or_focus(page: Page, live_app: str) -> None:
    # Site-wide header control: spot-check a second page so this isn't
    # accidentally homepage-specific markup/CSS.
    page.goto(live_app + "/about")
    _assert_menu_not_revealed_by_hover(page, "About")
    _assert_menu_not_revealed_by_focus_alone(page, "About")
    _assert_menu_opens_and_closes_on_keyboard_activation(page, "About")
