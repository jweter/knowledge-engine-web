"""Automated coverage for the objectively-checkable parts of two WCAG 2.2 AA
criteria that `docs/manual_accessibility_checklist.md` (rows 4 and 10)
previously listed as needing a human pass:

- 1.4.10 Reflow: content must remain usable at a 320px CSS width without
  requiring two-dimensional scrolling. Whether reflowed content still reads
  sensibly is a judgment call for a human, but "does the page overflow
  horizontally at all" is a plain layout measurement.
- 2.4.7 Focus Visible: every interactive element -- not only the first text
  input `tests/test_keyboard_navigation_e2e.py` already checks -- must show
  some visible change when it receives focus. Whether that change has
  sufficient *contrast* is a human judgment call; whether it exists at all
  is a computed-style comparison.

This does not replace the manual checklist rows: it narrows them to the
genuinely subjective remainder (reading order after reflow, focus-indicator
contrast/clarity) instead of leaving the whole criterion untested. See
`docs/manual_accessibility_checklist.md` for what still requires a human.
"""

from __future__ import annotations

from typing import cast

import pytest
from playwright.sync_api import Locator, Page

from tests._browser_e2e_support import EVIDENCE_RECORD_ID, QUESTION

pytestmark = pytest.mark.browser_e2e

# Native and ARIA-widened focusable elements, excluding programmatic-only
# focus targets (tabindex="-1", e.g. the skip-link's <main id="main-content">
# target) that are deliberately not part of the normal tab order.
_FOCUSABLE_SELECTOR = (
    "a[href], button:not([disabled]), input:not([disabled]):not([type='hidden']), "
    "select:not([disabled]), textarea:not([disabled]), "
    "[tabindex]:not([tabindex='-1']), summary"
)


def _assert_no_horizontal_overflow(page: Page, page_label: str) -> None:
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, (
        f"{page_label} overflows horizontally by {overflow}px at a 320px CSS width "
        "(WCAG 1.4.10 Reflow) -- content should reflow to a single column instead "
        "of requiring two-dimensional scrolling"
    )


def _style_signature(locator: Locator) -> dict[str, str]:
    return cast(
        dict[str, str],
        locator.evaluate(
            """element => {
                const style = getComputedStyle(element);
                return {
                    outlineStyle: style.outlineStyle,
                    outlineWidth: style.outlineWidth,
                    boxShadow: style.boxShadow,
                    borderColor: style.borderColor,
                    backgroundColor: style.backgroundColor,
                    textDecorationLine: style.textDecorationLine,
                };
            }"""
        ),
    )


def _assert_every_focusable_element_has_a_visible_focus_indicator(
    page: Page, page_label: str
) -> None:
    handles = page.locator(_FOCUSABLE_SELECTOR)
    count = handles.count()
    assert count > 0, f"{page_label} has no focusable elements to check"
    failures: list[str] = []
    for index in range(count):
        element = handles.nth(index)
        if not element.is_visible():
            continue
        unfocused = _style_signature(element)
        element.focus()
        focused = _style_signature(element)
        element.evaluate("element => element.blur()")
        if focused == unfocused:
            description = cast(str, element.evaluate("element => element.outerHTML.slice(0, 120)"))
            failures.append(description)
    assert not failures, (
        f"{page_label} has {len(failures)} focusable element(s) with no visible "
        "focus-state style change (WCAG 2.4.7 Focus Visible):\n\n" + "\n".join(failures)
    )


def test_homepage_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/")
    _assert_no_horizontal_overflow(page, "Homepage")


def test_ask_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    _assert_no_horizontal_overflow(page, "Ask (indexed hit)")


def test_ask_no_match_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")
    _assert_no_horizontal_overflow(page, "Ask (no match)")


def test_claim_detail_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/claims/" + EVIDENCE_RECORD_ID)
    _assert_no_horizontal_overflow(page, "Claim detail")


def test_dashboard_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/dashboard")
    _assert_no_horizontal_overflow(page, "Evidence Intelligence dashboard")


def test_graph_summary_reflows_at_320px_without_horizontal_scroll(
    page: Page, live_app: str
) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/graph")
    _assert_no_horizontal_overflow(page, "Graph summary")


def test_claims_list_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/claims")
    _assert_no_horizontal_overflow(page, "Claims list")


def test_discover_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/discover")
    _assert_no_horizontal_overflow(page, "Discover")


def test_discover_with_unavailable_capability_reflows_at_320px_without_horizontal_scroll(
    page: Page, live_app: str
) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/discover?q=GLP-1+receptor+agonist+weight+loss")
    _assert_no_horizontal_overflow(page, "Discover (capability unavailable)")


def test_about_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/about")
    _assert_no_horizontal_overflow(page, "About")


def test_roadmap_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/roadmap")
    _assert_no_horizontal_overflow(page, "Roadmap")


def test_roadmap_concept_preview_reflows_at_320px_without_horizontal_scroll(
    page: Page, live_app: str
) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/static/concept-preview.html")
    _assert_no_horizontal_overflow(page, "Roadmap concept preview")


def test_demo_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/demo")
    _assert_no_horizontal_overflow(page, "Demo")


def test_reports_index_reflows_at_320px_without_horizontal_scroll(
    page: Page, live_app: str
) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/reports")
    _assert_no_horizontal_overflow(page, "Reports index")


def test_report_view_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/reports/graph")
    _assert_no_horizontal_overflow(page, "Report view (graph)")


def test_unconfirmed_claims_reflows_at_320px_without_horizontal_scroll(
    page: Page, live_app: str
) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/unconfirmed-claims")
    _assert_no_horizontal_overflow(page, "Unconfirmed claims")


def test_relationship_candidates_reflows_at_320px_without_horizontal_scroll(
    page: Page, live_app: str
) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/relationship-candidates")
    _assert_no_horizontal_overflow(page, "Relationship candidates")


def test_paper_detail_reflows_at_320px_without_horizontal_scroll(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 320, "height": 800})
    page.goto(live_app + "/papers/1")
    _assert_no_horizontal_overflow(page, "Paper detail")


def test_homepage_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Homepage")


def test_ask_every_focusable_element_has_visible_focus_indicator(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Ask (indexed hit)")


def test_ask_no_match_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Ask (no match)")


def test_claim_detail_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/claims/" + EVIDENCE_RECORD_ID)
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Claim detail")


def test_dashboard_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/dashboard")
    _assert_every_focusable_element_has_a_visible_focus_indicator(
        page, "Evidence Intelligence dashboard"
    )


def test_graph_summary_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/graph")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Graph summary")


def test_claims_list_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/claims")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Claims list")


def test_discover_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/discover")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Discover")


def test_discover_with_unavailable_capability_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/discover?q=GLP-1+receptor+agonist+weight+loss")
    _assert_every_focusable_element_has_a_visible_focus_indicator(
        page, "Discover (capability unavailable)"
    )


def test_about_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/about")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "About")


def test_roadmap_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/roadmap")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Roadmap")


def test_roadmap_concept_preview_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/static/concept-preview.html")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Roadmap concept preview")


def test_demo_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/demo")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Demo")


def test_reports_index_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/reports")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Reports index")


def test_report_view_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/reports/graph")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Report view (graph)")


def test_unconfirmed_claims_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/unconfirmed-claims")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Unconfirmed claims")


def test_relationship_candidates_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/relationship-candidates")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Relationship candidates")


def test_paper_detail_every_focusable_element_has_visible_focus_indicator(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/papers/1")
    _assert_every_focusable_element_has_a_visible_focus_indicator(page, "Paper detail")
