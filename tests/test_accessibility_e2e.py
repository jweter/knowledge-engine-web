"""Automated accessibility (axe-core/WCAG) checks for reachable Web pages.

`docs/INDUSTRY_REALITY_CHECK.md` identified "no automated accessibility
tooling was found in the current repository search" as a P1 production gap.
This module is the automated answer to that gap: it runs axe-core (via
`axe-playwright-python`, which vendors `axe.min.js` -- no network access
needed at test time) against real server/real-Chromium pages, and fails on
any "critical", "serious", "moderate", or "minor" impact violation axe-core
reports.

Every page covered here is reachable without Research/AI capability
configured (indexed retrieval only, same fixture data as
`tests/test_browser_e2e.py`), so this suite adds coverage without faking
backend authority -- see `docs/agent-development-policy.md` section 1's
read-only, fail-closed posture. The async-Research progress/report views
and the mobile Product Reality review panel remain unchecked because
exercising them honestly requires real Research capability, which this
repository cannot fake without violating that posture; see
`docs/browser_e2e_testing.md`.
"""

from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

from tests._browser_e2e_support import EVIDENCE_RECORD_ID, QUESTION

pytestmark = pytest.mark.browser_e2e

_ENFORCED_IMPACTS = {"critical", "serious", "moderate", "minor"}


def _assert_no_enforced_violations(page: Page, page_label: str) -> None:
    axe = Axe()
    results = axe.run(page)
    enforced = [v for v in results.response["violations"] if v["impact"] in _ENFORCED_IMPACTS]
    if enforced:
        details = "\n\n".join(
            f"{v['id']} ({v['impact']}): {v['help']} -- {v['helpUrl']}\n"
            + "\n".join(f"  target: {', '.join(node['target'])}" for node in v["nodes"])
            for v in enforced
        )
        pytest.fail(
            f"{page_label} has {len(enforced)} accessibility violation(s) per "
            f"axe-core:\n\n{details}"
        )


def test_homepage_has_no_accessibility_violations(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")
    _assert_no_enforced_violations(page, "Homepage")


def test_ask_with_indexed_hit_has_no_accessibility_violations(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    _assert_no_enforced_violations(page, "Ask (indexed hit)")


def test_ask_with_no_match_has_no_accessibility_violations(page: Page, live_app: str) -> None:
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")
    _assert_no_enforced_violations(page, "Ask (no match)")


def test_claim_detail_page_has_no_accessibility_violations(page: Page, live_app: str) -> None:
    page.goto(live_app + "/claims/" + EVIDENCE_RECORD_ID)
    _assert_no_enforced_violations(page, "Claim detail")


def test_graph_summary_page_has_no_accessibility_violations(page: Page, live_app: str) -> None:
    page.goto(live_app + "/graph")
    _assert_no_enforced_violations(page, "Graph summary")


def test_dashboard_page_has_no_accessibility_violations(page: Page, live_app: str) -> None:
    page.goto(live_app + "/dashboard")
    _assert_no_enforced_violations(page, "Evidence Intelligence dashboard")


def test_claims_list_page_has_no_accessibility_violations(page: Page, live_app: str) -> None:
    page.goto(live_app + "/claims")
    _assert_no_enforced_violations(page, "Claims list")
