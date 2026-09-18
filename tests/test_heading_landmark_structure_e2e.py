"""Real-browser coverage for the objectively-checkable part of WCAG 2.2 AA
2.4.6 Headings and Labels (`docs/manual_accessibility_checklist.md` row 9).

Whether a screen-reader user can *understand* a heading or landmark out of
context is a human judgment call. But whether the heading structure and
landmark regions a screen reader would navigate by are even well-formed is
a plain, scriptable fact:

- no heading level is skipped (e.g. an h2 followed directly by an h4, with
  no h3 in between), and the page has exactly one top-level (h1) heading --
  the precondition for "navigate by heading" to produce a coherent outline
  at all;
- exactly one `main` landmark exists, so "jump to main content" is
  unambiguous;
- when more than one landmark of the same role exists on a page (e.g. two
  `nav` regions), each instance has its own non-empty, distinct accessible
  name, so a screen-reader user's landmark list does not show two
  indistinguishable entries.

`axe-core` (`tests/test_accessibility_e2e.py`) does not catch any of this:
`heading-order`, `landmark-one-main`, `landmark-unique`, etc. are tagged
"best practice" in axe-core and are not part of its default enabled
ruleset. This does not replace the manual checklist row: it narrows it to
the genuinely subjective remainder (does a heading's or landmark's text
actually make sense out of context) instead of leaving the whole criterion
untested.
"""

from __future__ import annotations

from typing import cast

import pytest
from playwright.sync_api import Page

from tests._browser_e2e_support import EVIDENCE_RECORD_ID, QUESTION

pytestmark = pytest.mark.browser_e2e

# Mirrors the standard HTML sectioning-content-to-ARIA-role mapping: a
# <header>/<footer> only maps to banner/contentinfo when it is not nested
# inside another sectioning element (article/aside/main/nav/section), per
# the HTML-AAM spec -- otherwise it is a plain, unnamed group.
_LANDMARK_ROLES_JS = """
() => {
    const roleOf = (el) => {
        const explicit = el.getAttribute('role');
        if (explicit) return explicit;
        const tag = el.tagName.toLowerCase();
        const nestedInSectioning = el.closest('article, aside, main, nav, section') !== null;
        if (tag === 'main') return 'main';
        if (tag === 'nav') return 'navigation';
        if (tag === 'header') return nestedInSectioning ? null : 'banner';
        if (tag === 'footer') return nestedInSectioning ? null : 'contentinfo';
        if (tag === 'aside') return 'complementary';
        if (tag === 'form') {
            const named = el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby');
            return named ? 'form' : null;
        }
        return null;
    };
    const isVisible = (el) => {
        const style = getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden'
            && el.getAttribute('aria-hidden') !== 'true';
    };
    const accessibleName = (el) => {
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const referenced = labelledBy
                .split(/\\s+/)
                .map((id) => document.getElementById(id))
                .filter(Boolean)
                .map((node) => node.textContent.trim())
                .join(' ')
                .trim();
            if (referenced) return referenced;
        }
        const label = el.getAttribute('aria-label');
        if (label && label.trim()) return label.trim();
        return '';
    };
    return Array.from(document.querySelectorAll('main, nav, header, footer, aside, form, [role]'))
        .filter(isVisible)
        .map((el) => [roleOf(el), accessibleName(el)])
        .filter(([role]) => role !== null);
}
"""

_HEADINGS_JS = """
() => Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'))
    .filter((el) => {
        const style = getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden'
            && el.getAttribute('aria-hidden') !== 'true';
    })
    .map((el) => [Number(el.tagName[1]), el.textContent.trim().slice(0, 60)])
"""


def _assert_no_skipped_heading_levels(page: Page, page_label: str) -> None:
    headings = cast(list[tuple[int, str]], page.evaluate(_HEADINGS_JS))
    assert headings, f"{page_label} has no heading elements at all"

    first_level, first_text = headings[0]
    assert first_level == 1, (
        f"{page_label}'s first heading is h{first_level} ('{first_text}'), not h1 -- "
        "a screen-reader user navigating by heading has no top-level entry point "
        "(WCAG 2.4.6 Headings and Labels)"
    )

    previous_level = first_level
    for level, text in headings[1:]:
        assert level <= previous_level + 1, (
            f"{page_label} skips from h{previous_level} to h{level} at heading "
            f"'{text}' -- a screen-reader user navigating by heading level loses "
            "the intervening structure (WCAG 2.4.6 Headings and Labels)"
        )
        previous_level = level


def _assert_landmark_structure_is_well_formed(page: Page, page_label: str) -> None:
    landmarks = cast(list[list[str]], page.evaluate(_LANDMARK_ROLES_JS))

    main_landmarks = [entry for entry in landmarks if entry[0] == "main"]
    assert len(main_landmarks) == 1, (
        f"{page_label} has {len(main_landmarks)} 'main' landmark(s), expected exactly one -- "
        "a screen reader's 'jump to main content' navigation is ambiguous or missing "
        "(WCAG 2.4.6 Headings and Labels / landmark-one-main)"
    )

    by_role: dict[str, list[str]] = {}
    for role, name in landmarks:
        by_role.setdefault(role, []).append(name)

    for role, names in by_role.items():
        if len(names) <= 1:
            continue
        assert all(names), (
            f"{page_label} has {len(names)} '{role}' landmarks but at least one has no "
            "accessible name (aria-label/aria-labelledby) -- a screen-reader user's "
            "landmark list cannot tell them apart (WCAG 2.4.6 Headings and Labels)"
        )
        assert len(set(names)) == len(names), (
            f"{page_label} has {len(names)} '{role}' landmarks that do not all have "
            f"distinct accessible names ({names}) -- a screen-reader user's landmark "
            "list shows indistinguishable entries (WCAG 2.4.6 Headings and Labels)"
        )


def test_homepage_has_well_formed_heading_and_landmark_structure(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    _assert_no_skipped_heading_levels(page, "Homepage")
    _assert_landmark_structure_is_well_formed(page, "Homepage")


def test_ask_with_indexed_hit_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    _assert_no_skipped_heading_levels(page, "Ask (indexed hit)")
    _assert_landmark_structure_is_well_formed(page, "Ask (indexed hit)")


def test_ask_with_no_match_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")
    _assert_no_skipped_heading_levels(page, "Ask (no match)")
    _assert_landmark_structure_is_well_formed(page, "Ask (no match)")


def test_claim_detail_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/claims/" + EVIDENCE_RECORD_ID)
    _assert_no_skipped_heading_levels(page, "Claim detail")
    _assert_landmark_structure_is_well_formed(page, "Claim detail")


def test_graph_summary_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/graph")
    _assert_no_skipped_heading_levels(page, "Graph summary")
    _assert_landmark_structure_is_well_formed(page, "Graph summary")


def test_dashboard_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/dashboard")
    _assert_no_skipped_heading_levels(page, "Evidence Intelligence dashboard")
    _assert_landmark_structure_is_well_formed(page, "Evidence Intelligence dashboard")


def test_claims_list_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/claims")
    _assert_no_skipped_heading_levels(page, "Claims list")
    _assert_landmark_structure_is_well_formed(page, "Claims list")


def test_discover_has_well_formed_heading_and_landmark_structure(page: Page, live_app: str) -> None:
    page.goto(live_app + "/discover")
    _assert_no_skipped_heading_levels(page, "Discover")
    _assert_landmark_structure_is_well_formed(page, "Discover")


def test_discover_with_unavailable_capability_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/discover?q=GLP-1+receptor+agonist+weight+loss")
    _assert_no_skipped_heading_levels(page, "Discover (capability unavailable)")
    _assert_landmark_structure_is_well_formed(page, "Discover (capability unavailable)")


def test_about_has_well_formed_heading_and_landmark_structure(page: Page, live_app: str) -> None:
    page.goto(live_app + "/about")
    _assert_no_skipped_heading_levels(page, "About")
    _assert_landmark_structure_is_well_formed(page, "About")


def test_roadmap_has_well_formed_heading_and_landmark_structure(page: Page, live_app: str) -> None:
    page.goto(live_app + "/roadmap")
    _assert_no_skipped_heading_levels(page, "Roadmap")
    _assert_landmark_structure_is_well_formed(page, "Roadmap")


def test_roadmap_concept_preview_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/static/concept-preview.html")
    _assert_no_skipped_heading_levels(page, "Roadmap concept preview")
    _assert_landmark_structure_is_well_formed(page, "Roadmap concept preview")


def test_demo_has_well_formed_heading_and_landmark_structure(page: Page, live_app: str) -> None:
    page.goto(live_app + "/demo")
    _assert_no_skipped_heading_levels(page, "Demo")
    _assert_landmark_structure_is_well_formed(page, "Demo")


def test_reports_index_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/reports")
    _assert_no_skipped_heading_levels(page, "Reports index")
    _assert_landmark_structure_is_well_formed(page, "Reports index")


def test_report_view_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/reports/graph")
    _assert_no_skipped_heading_levels(page, "Report view")
    _assert_landmark_structure_is_well_formed(page, "Report view")


def test_unconfirmed_claims_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/unconfirmed-claims")
    _assert_no_skipped_heading_levels(page, "Unconfirmed claims")
    _assert_landmark_structure_is_well_formed(page, "Unconfirmed claims")


def test_relationship_candidates_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/relationship-candidates")
    _assert_no_skipped_heading_levels(page, "Relationship candidates")
    _assert_landmark_structure_is_well_formed(page, "Relationship candidates")


def test_paper_detail_has_well_formed_heading_and_landmark_structure(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/papers/1")
    _assert_no_skipped_heading_levels(page, "Paper detail")
    _assert_landmark_structure_is_well_formed(page, "Paper detail")
