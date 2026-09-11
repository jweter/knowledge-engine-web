"""Automated accessibility (axe-core/WCAG) checks for the Ask critical path.

`docs/INDUSTRY_REALITY_CHECK.md` identified "no automated accessibility
tooling was found in the current repository search" as a P1 production gap.
This module is the first automated answer to that gap: it runs axe-core
(via `axe-playwright-python`, which vendors `axe.min.js` -- no network
access needed at test time) against the same real server/real-Chromium
pages `tests/test_browser_e2e.py` already exercises, and fails on any
"critical" or "serious" impact violation axe-core reports.

"moderate"/"minor" impact findings are not yet enforced -- see
`docs/browser_e2e_testing.md` for the remaining WCAG 2.2 AA gap this does
not close (manual keyboard/screen-reader passes, contrast auditing beyond
axe's automated checks, and pages/states beyond the four covered here).
"""

from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

from tests._browser_e2e_support import EVIDENCE_RECORD_ID, QUESTION

pytestmark = pytest.mark.browser_e2e

_ENFORCED_IMPACTS = {"critical", "serious"}


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
            f"{page_label} has {len(enforced)} critical/serious accessibility "
            f"violation(s) per axe-core:\n\n{details}"
        )


def test_homepage_has_no_critical_or_serious_accessibility_violations(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/")
    _assert_no_enforced_violations(page, "Homepage")


def test_ask_with_indexed_hit_has_no_critical_or_serious_accessibility_violations(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=" + QUESTION.replace(" ", "+").replace("?", "%3F"))
    _assert_no_enforced_violations(page, "Ask (indexed hit)")


def test_ask_with_no_match_has_no_critical_or_serious_accessibility_violations(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")
    _assert_no_enforced_violations(page, "Ask (no match)")


def test_claim_detail_page_has_no_critical_or_serious_accessibility_violations(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/claims/" + EVIDENCE_RECORD_ID)
    _assert_no_enforced_violations(page, "Claim detail")
