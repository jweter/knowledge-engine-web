"""Automated coverage for the objectively-checkable part of WCAG 2.2 AA
criterion 2.5.8 (Target Size Minimum).

Pointer-activatable targets should be at least 24x24 CSS px unless a defined
exception applies. This module exercises both desktop and narrow/mobile
layouts. It recognizes two mechanically verifiable exceptions:

* Inline: an inline anchor embedded in surrounding running text.
* Spacing: an undersized target has enough separation that a 24 CSS pixel
  diameter circle centered on its bounding box does not intersect another
  target, or the corresponding circle for another undersized target.

The contextual Equivalent and Essential exceptions remain human judgment and
are intentionally not inferred here.
"""

from __future__ import annotations

from math import hypot
from typing import TypedDict, cast

import pytest
from playwright.sync_api import Locator, Page

from tests._browser_e2e_support import EVIDENCE_RECORD_ID, QUESTION

pytestmark = pytest.mark.browser_e2e

_TARGET_SELECTOR = (
    "a[href], button:not([disabled]), "
    "input:not([disabled]):not([type='hidden']):not([type='checkbox']):not([type='radio']), "
    "select:not([disabled]), textarea:not([disabled]), "
    "[tabindex]:not([tabindex='-1']), summary"
)

_MINIMUM_SIZE = 24
_MINIMUM_RADIUS = _MINIMUM_SIZE / 2
_VIEWPORTS = ((1280, 720), (375, 812))


class _TargetMetrics(TypedDict):
    display: str
    x: float
    y: float
    width: float
    height: float
    inline_text_flow: bool


def _target_metrics(locator: Locator) -> _TargetMetrics:
    return cast(
        _TargetMetrics,
        locator.evaluate(
            """element => {
                const style = getComputedStyle(element);
                const box = element.getBoundingClientRect();
                const parent = element.parentNode;
                const inlineTextFlow =
                    element.tagName === 'A' &&
                    style.display === 'inline' &&
                    parent &&
                    Array.from(parent.childNodes).some(node =>
                        node !== element &&
                        node.nodeType === Node.TEXT_NODE &&
                        node.textContent &&
                        node.textContent.trim().length > 0
                    );
                return {
                    display: style.display,
                    x: box.x,
                    y: box.y,
                    width: box.width,
                    height: box.height,
                    inline_text_flow: Boolean(inlineTextFlow),
                };
            }"""
        ),
    )


def _is_undersized(metrics: _TargetMetrics) -> bool:
    return metrics["width"] < _MINIMUM_SIZE or metrics["height"] < _MINIMUM_SIZE


def _has_spacing_exception(index: int, targets: list[_TargetMetrics]) -> bool:
    """Return whether target ``index`` meets WCAG 2.5.8's Spacing exception."""
    target = targets[index]
    center_x = target["x"] + target["width"] / 2
    center_y = target["y"] + target["height"] / 2

    for other_index, other in enumerate(targets):
        if other_index == index:
            continue

        if _is_undersized(other):
            other_center_x = other["x"] + other["width"] / 2
            other_center_y = other["y"] + other["height"] / 2
            if hypot(center_x - other_center_x, center_y - other_center_y) < _MINIMUM_SIZE:
                return False
            continue

        nearest_x = min(max(center_x, other["x"]), other["x"] + other["width"])
        nearest_y = min(max(center_y, other["y"]), other["y"] + other["height"])
        if hypot(center_x - nearest_x, center_y - nearest_y) < _MINIMUM_RADIUS:
            return False

    return True


def _assert_current_viewport(page: Page, page_label: str, viewport_label: str) -> None:
    handles = page.locator(_TARGET_SELECTOR)
    count = handles.count()
    assert count > 0, f"{page_label} has no pointer targets to check"

    visible: list[tuple[Locator, _TargetMetrics]] = []
    for index in range(count):
        element = handles.nth(index)
        if element.is_visible():
            visible.append((element, _target_metrics(element)))

    targets = [metrics for _, metrics in visible]
    failures: list[str] = []
    for index, (element, metrics) in enumerate(visible):
        if not _is_undersized(metrics):
            continue
        if metrics["inline_text_flow"]:
            # WCAG 2.5.8 Inline exception: specifically an anchor embedded in
            # surrounding running text, not merely any display:inline target.
            continue
        if _has_spacing_exception(index, targets):
            continue

        description = cast(str, element.evaluate("element => element.outerHTML.slice(0, 120)"))
        failures.append(
            f"{description} ({metrics['width']:.1f}x{metrics['height']:.1f}px, "
            f"display={metrics['display']})"
        )

    assert not failures, (
        f"{page_label} at {viewport_label} has {len(failures)} pointer target(s) smaller than "
        f"{_MINIMUM_SIZE}x{_MINIMUM_SIZE} CSS px without a mechanically verified Inline or "
        "Spacing exception (WCAG 2.5.8 Target Size Minimum):\n\n" + "\n".join(failures)
    )


def _assert_targets_meet_minimum_size(page: Page, page_label: str) -> None:
    for width, height in _VIEWPORTS:
        page.set_viewport_size({"width": width, "height": height})
        _assert_current_viewport(page, page_label, f"{width}x{height}")


def test_homepage_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    _assert_targets_meet_minimum_size(page, "Homepage")


def test_ask_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    _assert_targets_meet_minimum_size(page, "Ask (indexed hit)")


def test_ask_no_match_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")
    _assert_targets_meet_minimum_size(page, "Ask (no match)")


def test_claim_detail_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/claims/" + EVIDENCE_RECORD_ID)
    _assert_targets_meet_minimum_size(page, "Claim detail")


def test_dashboard_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/dashboard")
    _assert_targets_meet_minimum_size(page, "Evidence Intelligence dashboard")


def test_graph_summary_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/graph")
    _assert_targets_meet_minimum_size(page, "Graph summary")


def test_claims_list_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/claims")
    _assert_targets_meet_minimum_size(page, "Claims list")


def test_discover_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/discover")
    _assert_targets_meet_minimum_size(page, "Discover")


def test_discover_with_unavailable_capability_targets_meet_minimum_size(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/discover?q=GLP-1+receptor+agonist+weight+loss")
    _assert_targets_meet_minimum_size(page, "Discover (capability unavailable)")


def test_about_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/about")
    _assert_targets_meet_minimum_size(page, "About")


def test_roadmap_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/roadmap")
    _assert_targets_meet_minimum_size(page, "Roadmap")


def test_roadmap_concept_preview_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/static/concept-preview.html")
    _assert_targets_meet_minimum_size(page, "Roadmap concept preview")


def test_demo_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/demo")
    _assert_targets_meet_minimum_size(page, "Demo")


def test_reports_index_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/reports")
    _assert_targets_meet_minimum_size(page, "Reports index")


def test_report_view_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/reports/graph")
    _assert_targets_meet_minimum_size(page, "Report view (graph)")


def test_unconfirmed_claims_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/unconfirmed-claims")
    _assert_targets_meet_minimum_size(page, "Unconfirmed claims")


def test_relationship_candidates_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/relationship-candidates")
    _assert_targets_meet_minimum_size(page, "Relationship candidates")


def test_paper_detail_targets_meet_minimum_size(page: Page, live_app: str) -> None:
    page.goto(live_app + "/papers/1")
    _assert_targets_meet_minimum_size(page, "Paper detail")
