"""Automated coverage for the objectively-checkable part of one more WCAG
2.2 AA criterion `docs/manual_accessibility_checklist.md` (row 11) previously
listed as needing a human pass:

- 2.5.8 Target Size (Minimum): pointer-activatable targets should be at
  least 24x24 CSS px, unless an exception applies. The exceptions that need
  human/contextual judgment (Equivalent, Essential, adequate Spacing between
  undersized targets) are out of scope here, but the "Inline" exception --
  a target that is a plain link inside a sentence or block of text, whose
  size is dictated by the surrounding text's line-height rather than
  deliberate touch-target sizing -- is mechanically detectable: such a link
  renders with `display: inline` (the browser default for `<a>`), whereas
  every button-styled or nav-styled control in this codebase is deliberately
  given a block/inline-block/flex display. Checkbox/radio inputs are
  excluded too (the "User agent control" exception covers an unrestyled
  native control), though this codebase's only checkbox is gated behind
  Research capability and does not appear in this fixture environment.

This does not close row 11 -- it narrows it to the exceptions that remain
genuinely contextual (Equivalent, Essential, Spacing) and to drag-style
interactions (2.5.7), neither of which this module attempts to judge.
"""

from __future__ import annotations

from typing import TypedDict, cast

import pytest
from playwright.sync_api import Locator, Page

from tests._browser_e2e_support import EVIDENCE_RECORD_ID, QUESTION

pytestmark = pytest.mark.browser_e2e

# Same focusable-element scope as tests/test_reflow_and_focus_indicators_e2e.py,
# minus checkbox/radio inputs (WCAG 2.5.8's "User agent control" exception
# covers an unrestyled native control; this codebase's only checkbox --
# Ask's Research quick-toggle -- is gated behind Research capability and
# does not render in this fixture environment).
_TARGET_SELECTOR = (
    "a[href], button:not([disabled]), "
    "input:not([disabled]):not([type='hidden']):not([type='checkbox']):not([type='radio']), "
    "select:not([disabled]), textarea:not([disabled]), "
    "[tabindex]:not([tabindex='-1']), summary"
)

_MINIMUM_SIZE = 24


class _TargetMetrics(TypedDict):
    display: str
    width: float
    height: float


def _target_metrics(locator: Locator) -> _TargetMetrics:
    return cast(
        _TargetMetrics,
        locator.evaluate(
            """element => {
                const style = getComputedStyle(element);
                const box = element.getBoundingClientRect();
                return { display: style.display, width: box.width, height: box.height };
            }"""
        ),
    )


def _assert_no_undersized_non_inline_targets(page: Page, page_label: str) -> None:
    handles = page.locator(_TARGET_SELECTOR)
    count = handles.count()
    assert count > 0, f"{page_label} has no pointer targets to check"
    failures: list[str] = []
    for index in range(count):
        element = handles.nth(index)
        if not element.is_visible():
            continue
        metrics = _target_metrics(element)
        if metrics["display"] == "inline":
            # WCAG 2.5.8 "Inline" exception: a plain link inside running
            # text, sized by line-height rather than deliberate touch-target
            # sizing.
            continue
        if metrics["width"] < _MINIMUM_SIZE or metrics["height"] < _MINIMUM_SIZE:
            description = cast(str, element.evaluate("element => element.outerHTML.slice(0, 120)"))
            failures.append(
                f"{description} ({metrics['width']:.1f}x{metrics['height']:.1f}px, "
                f"display={metrics['display']})"
            )
    assert not failures, (
        f"{page_label} has {len(failures)} non-inline pointer target(s) smaller than "
        f"{_MINIMUM_SIZE}x{_MINIMUM_SIZE} CSS px (WCAG 2.5.8 Target Size Minimum):\n\n"
        + "\n".join(failures)
    )


def test_homepage_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    _assert_no_undersized_non_inline_targets(page, "Homepage")


def test_ask_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    _assert_no_undersized_non_inline_targets(page, "Ask (indexed hit)")


def test_ask_no_match_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")
    _assert_no_undersized_non_inline_targets(page, "Ask (no match)")


def test_claim_detail_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/claims/" + EVIDENCE_RECORD_ID)
    _assert_no_undersized_non_inline_targets(page, "Claim detail")


def test_dashboard_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/dashboard")
    _assert_no_undersized_non_inline_targets(page, "Evidence Intelligence dashboard")


def test_graph_summary_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/graph")
    _assert_no_undersized_non_inline_targets(page, "Graph summary")


def test_claims_list_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/claims")
    _assert_no_undersized_non_inline_targets(page, "Claims list")


def test_discover_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/discover")
    _assert_no_undersized_non_inline_targets(page, "Discover")


def test_discover_with_unavailable_capability_targets_meet_minimum_size(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/discover?q=GLP-1+receptor+agonist+weight+loss")
    _assert_no_undersized_non_inline_targets(page, "Discover (capability unavailable)")


def test_about_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/about")
    _assert_no_undersized_non_inline_targets(page, "About")


def test_roadmap_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/roadmap")
    _assert_no_undersized_non_inline_targets(page, "Roadmap")


def test_roadmap_concept_preview_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/static/concept-preview.html")
    _assert_no_undersized_non_inline_targets(page, "Roadmap concept preview")


def test_demo_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/demo")
    _assert_no_undersized_non_inline_targets(page, "Demo")


def test_reports_index_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/reports")
    _assert_no_undersized_non_inline_targets(page, "Reports index")


def test_report_view_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/reports/graph")
    _assert_no_undersized_non_inline_targets(page, "Report view (graph)")


def test_unconfirmed_claims_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/unconfirmed-claims")
    _assert_no_undersized_non_inline_targets(page, "Unconfirmed claims")


def test_relationship_candidates_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/relationship-candidates")
    _assert_no_undersized_non_inline_targets(page, "Relationship candidates")


def test_paper_detail_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/papers/1")
    _assert_no_undersized_non_inline_targets(page, "Paper detail")
