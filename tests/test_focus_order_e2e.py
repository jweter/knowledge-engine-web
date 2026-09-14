"""Automated coverage for the objectively-checkable part of WCAG 2.2 AA
2.4.3 Focus Order (`docs/manual_accessibility_checklist.md` row 8).

Whether a full-page Tab traversal reaches elements in a *sensible
reading/interaction order* is a human judgment call. But whether the
browser's actual Tab order matches the page's document order -- the
precondition every other focus-order judgment depends on -- is a plain,
scriptable fact: no positive `tabindex` exists to override natural order,
and a real Tab-key traversal visits every visible focusable element in
exactly the sequence `querySelectorAll` would return it in.

This does not replace the manual checklist row: it narrows it to the
genuinely subjective remainder (does the resulting order *read* sensibly)
instead of leaving the whole criterion untested.
"""

from __future__ import annotations

from typing import cast

import pytest
from playwright.sync_api import Locator, Page

from tests._browser_e2e_support import EVIDENCE_RECORD_ID, QUESTION

pytestmark = pytest.mark.browser_e2e

# Same native/ARIA-widened focusable selector used by
# tests/test_reflow_and_focus_indicators_e2e.py, excluding programmatic-only
# focus targets (tabindex="-1", e.g. the skip-link's <main id="main-content">
# target) that are deliberately not part of the normal tab order.
_FOCUSABLE_SELECTOR = (
    "a[href], button:not([disabled]), input:not([disabled]):not([type='hidden']), "
    "select:not([disabled]), textarea:not([disabled]), "
    "[tabindex]:not([tabindex='-1']), summary"
)

_ORDER_ATTR = "data-e2e-focus-order"


def _positive_tabindex_elements(page: Page) -> list[str]:
    return cast(
        list[str],
        page.evaluate(
            """() => Array.from(document.querySelectorAll('[tabindex]'))
                .filter(el => Number(el.getAttribute('tabindex')) > 0)
                .map(el => el.outerHTML.slice(0, 120))"""
        ),
    )


def _tag_visible_focusable_elements_in_dom_order(page: Page) -> int:
    """Stamp every visible focusable element with its document-order index.

    Returns the count tagged. Uses the same per-element `is_visible()` check
    already relied on by the focus-visible-indicator test, so a dropdown's
    still-closed contents (e.g. the header "Inspect" menu) are correctly
    excluded rather than guessed at via a second, divergent visibility check.
    """
    handles: Locator = page.locator(_FOCUSABLE_SELECTOR)
    count = handles.count()
    tagged = 0
    for index in range(count):
        element = handles.nth(index)
        if not element.is_visible():
            continue
        element.evaluate(
            "(element, order) => element.setAttribute(order.attr, String(order.value))",
            {"attr": _ORDER_ATTR, "value": tagged},
        )
        tagged += 1
    return tagged


def _assert_full_page_tab_order_matches_document_order(page: Page, page_label: str) -> None:
    positive_tabindex = _positive_tabindex_elements(page)
    assert not positive_tabindex, (
        f"{page_label} has element(s) with a positive tabindex, which overrides natural "
        "document order and breaks WCAG 2.4.3 Focus Order:\n\n" + "\n".join(positive_tabindex)
    )

    expected_count = _tag_visible_focusable_elements_in_dom_order(page)
    assert expected_count > 0, f"{page_label} has no focusable elements to check"

    # Explicitly focus the first tagged element rather than blurring whatever
    # currently has focus: per the HTML spec, blur() clears
    # `document.activeElement` but does not reset the browser's *sequential
    # focus navigation starting point*, so on a page that autofocuses an
    # element (Ask, Discover), a subsequent Tab would silently resume from
    # that autofocused element instead of the top of the page -- exercising
    # only the tail of the order, not the full traversal this criterion
    # requires. Focusing the first element directly sidesteps that browser
    # quirk and deterministically starts the walk at position 0.
    page.locator(f"[{_ORDER_ATTR}='0']").focus()
    observed = [0]
    for _ in range(expected_count - 1):
        page.keyboard.press("Tab")
        tag_name = page.evaluate("() => document.activeElement.tagName")
        # Tabbing through a same-page iframe (the Roadmap page's embedded
        # concept-preview) reports the outer <iframe> element as
        # document.activeElement for every tab stop inside it -- it is
        # covered in its own right as a standalone page/state elsewhere, so
        # here we only need to keep tabbing until focus re-emerges into the
        # top-level document rather than mis-reading the iframe boundary as
        # a broken order.
        guard = 0
        while tag_name == "IFRAME" and guard < 50:
            page.keyboard.press("Tab")
            tag_name = page.evaluate("() => document.activeElement.tagName")
            guard += 1
        order = page.evaluate(
            "(attr) => { const el = document.activeElement; "
            "return el ? el.getAttribute(attr) : null; }",
            _ORDER_ATTR,
        )
        if order is None:
            break
        observed.append(int(order))

    expected = list(range(expected_count))
    assert observed == expected, (
        f"{page_label}'s keyboard Tab order does not match its document order "
        f"(WCAG 2.4.3 Focus Order): expected {expected}, observed {observed}"
    )


def test_homepage_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    _assert_full_page_tab_order_matches_document_order(page, "Homepage")


def test_ask_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    _assert_full_page_tab_order_matches_document_order(page, "Ask (indexed hit)")


def test_ask_no_match_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")
    _assert_full_page_tab_order_matches_document_order(page, "Ask (no match)")


def test_claim_detail_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/claims/" + EVIDENCE_RECORD_ID)
    _assert_full_page_tab_order_matches_document_order(page, "Claim detail")


def test_dashboard_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/dashboard")
    _assert_full_page_tab_order_matches_document_order(page, "Evidence Intelligence dashboard")


def test_graph_summary_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/graph")
    _assert_full_page_tab_order_matches_document_order(page, "Graph summary")


def test_claims_list_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/claims")
    _assert_full_page_tab_order_matches_document_order(page, "Claims list")


def test_discover_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/discover")
    _assert_full_page_tab_order_matches_document_order(page, "Discover")


def test_discover_with_unavailable_capability_tab_order_matches_document_order(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/discover?q=GLP-1+receptor+agonist+weight+loss")
    _assert_full_page_tab_order_matches_document_order(page, "Discover (capability unavailable)")


def test_about_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/about")
    _assert_full_page_tab_order_matches_document_order(page, "About")


def test_roadmap_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/roadmap")
    _assert_full_page_tab_order_matches_document_order(page, "Roadmap")


def test_roadmap_concept_preview_tab_order_matches_document_order(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/static/concept-preview.html")
    _assert_full_page_tab_order_matches_document_order(page, "Roadmap concept preview")


def test_demo_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/demo")
    _assert_full_page_tab_order_matches_document_order(page, "Demo")


def test_reports_index_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/reports")
    _assert_full_page_tab_order_matches_document_order(page, "Reports index")


def test_report_view_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/reports/graph")
    _assert_full_page_tab_order_matches_document_order(page, "Report view (graph)")


def test_unconfirmed_claims_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/unconfirmed-claims")
    _assert_full_page_tab_order_matches_document_order(page, "Unconfirmed claims")


def test_relationship_candidates_tab_order_matches_document_order(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/relationship-candidates")
    _assert_full_page_tab_order_matches_document_order(page, "Relationship candidates")


def test_paper_detail_tab_order_matches_document_order(page: Page, live_app: str) -> None:
    page.goto(live_app + "/papers/1")
    _assert_full_page_tab_order_matches_document_order(page, "Paper detail")
