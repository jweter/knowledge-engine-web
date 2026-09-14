"""Real-browser coverage for WCAG 2.1.4 Character Key Shortcuts
(`docs/manual_accessibility_checklist.md` row 6).

2.1.4 requires that any single-character keyboard shortcut (no modifier key)
can be turned off, remapped, or is only active while a specific component
has focus. Whether a screen-reader user perceives such a shortcut as safe is
a judgment call, but whether this codebase implements *any* bare
single-character shortcut at all is a plain, scriptable fact: no
`keydown`/`keypress`/`keyup` listener exists anywhere in this repository's
templates or static JavaScript (confirmed by source inspection), so 2.1.4
cannot currently be violated -- there is nothing to turn off or remap. This
test proves that conclusion behaviorally in a real Chromium instance rather
than resting on the source-inspection claim alone, and will fail the moment
a future change wires up a bare-character shortcut without the criterion's
required escape hatch.

What remains manual (per the accessibility checklist): re-checking this
conclusion whenever a future change adds an interaction-triggered keyboard
handler, since that handler would need its own turn-off/remap/focus-scoped
verification rather than a blanket "no shortcuts exist" check like this one.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests._browser_e2e_support import EVIDENCE_RECORD_ID, QUESTION

pytestmark = pytest.mark.browser_e2e

# Single printable characters most commonly wired up as bare keyboard
# shortcuts on real sites (search focus, help, vim-style navigation,
# Gmail-style single-letter actions) plus a couple of digits. None of them
# is expected to do anything here, since no such shortcut exists.
_SAMPLE_SHORTCUT_KEYS = [
    "a",
    "c",
    "d",
    "e",
    "f",
    "g",
    "h",
    "j",
    "k",
    "m",
    "n",
    "p",
    "q",
    "r",
    "s",
    "t",
    "u",
    "x",
    "/",
    "?",
    "1",
    "0",
]


def _focus_neutral_body(page: Page) -> None:
    page.locator("body").evaluate(
        """body => {
            body.setAttribute('tabindex', '-1');
            body.focus();
        }"""
    )
    assert page.evaluate("document.activeElement === document.body")


def _assert_no_bare_character_shortcut_fires(page: Page, page_label: str) -> None:
    before_url = page.url
    _focus_neutral_body(page)

    for key in _SAMPLE_SHORTCUT_KEYS:
        page.keyboard.press(key)

    page.wait_for_timeout(100)

    assert page.url == before_url, (
        f"{page_label}: a bare single-character key press navigated the page "
        "away -- a WCAG 2.1.4 Character Key Shortcuts violation"
    )
    assert page.evaluate("document.activeElement === document.body"), (
        f"{page_label}: a bare single-character key press moved focus away from "
        "the neutral body element -- a WCAG 2.1.4 Character Key Shortcuts "
        "violation (an undocumented, un-turn-off-able shortcut moved focus)"
    )


def test_homepage_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    _assert_no_bare_character_shortcut_fires(page, "Homepage")


def test_ask_with_indexed_hit_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    _assert_no_bare_character_shortcut_fires(page, "Ask (indexed hit)")


def test_ask_with_no_match_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")
    _assert_no_bare_character_shortcut_fires(page, "Ask (no match)")


def test_claim_detail_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/claims/" + EVIDENCE_RECORD_ID)
    _assert_no_bare_character_shortcut_fires(page, "Claim detail")


def test_graph_summary_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/graph")
    _assert_no_bare_character_shortcut_fires(page, "Graph summary")


def test_dashboard_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/dashboard")
    _assert_no_bare_character_shortcut_fires(page, "Evidence Intelligence dashboard")


def test_claims_list_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/claims")
    _assert_no_bare_character_shortcut_fires(page, "Claims list")


def test_discover_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/discover")
    _assert_no_bare_character_shortcut_fires(page, "Discover")


def test_discover_with_unavailable_capability_has_no_bare_character_shortcuts(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/discover?q=GLP-1+receptor+agonist+weight+loss")
    _assert_no_bare_character_shortcut_fires(page, "Discover (capability unavailable)")


def test_about_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/about")
    _assert_no_bare_character_shortcut_fires(page, "About")


def test_roadmap_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/roadmap")
    _assert_no_bare_character_shortcut_fires(page, "Roadmap")


def test_roadmap_concept_preview_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/static/concept-preview.html")
    _assert_no_bare_character_shortcut_fires(page, "Roadmap concept preview")


def test_demo_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/demo")
    _assert_no_bare_character_shortcut_fires(page, "Demo")


def test_reports_index_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/reports")
    _assert_no_bare_character_shortcut_fires(page, "Reports index")


def test_report_view_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/reports/graph")
    _assert_no_bare_character_shortcut_fires(page, "Report view (graph)")


def test_unconfirmed_claims_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/unconfirmed-claims")
    _assert_no_bare_character_shortcut_fires(page, "Unconfirmed claims")


def test_relationship_candidates_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/relationship-candidates")
    _assert_no_bare_character_shortcut_fires(page, "Relationship candidates")


def test_paper_detail_has_no_bare_character_shortcuts(page: Page, live_app: str) -> None:
    page.goto(live_app + "/papers/1")
    _assert_no_bare_character_shortcut_fires(page, "Paper detail")
