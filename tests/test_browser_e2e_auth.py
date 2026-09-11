"""Real headless-Chromium browser E2E tests for the alpha Basic Auth gate.

`tests/test_alpha_auth.py` already covers `AlphaBasicAuthMiddleware` at the
`TestClient` (ASGI transport) level. This module closes the separate,
previously-uncovered gap `docs/INDUSTRY_REALITY_CHECK.md` and
`docs/browser_e2e_testing.md` listed: real browser-driven authentication
behavior against the real server -- a real Chromium HTTP client presenting
(or omitting) HTTP Basic credentials, not a simulated ASGI request.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Browser, Page

from tests._browser_e2e_support import ALPHA_PASSWORD, ALPHA_USERNAME

pytestmark = pytest.mark.browser_e2e


def _assert_rejected_navigation(page: Page, url: str) -> None:
    """Assert the real browser receives the Basic Auth rejection without rendering the app."""
    response = page.goto(url)
    assert response is not None
    assert response.status == 401
    assert "Knowledge Engine" not in page.title()


def test_unauthenticated_browser_request_is_challenged(
    page: Page, live_app_with_alpha_auth: str
) -> None:
    _assert_rejected_navigation(page, live_app_with_alpha_auth + "/")


def test_correct_credentials_allow_real_browser_access(
    _browser: Browser, live_app_with_alpha_auth: str
) -> None:
    context = _browser.new_context(
        http_credentials={"username": ALPHA_USERNAME, "password": ALPHA_PASSWORD}
    )
    try:
        page = context.new_page()
        response = page.goto(live_app_with_alpha_auth + "/")
        assert response is not None
        assert response.status == 200
        assert "Knowledge Engine" in page.title()
    finally:
        context.close()


def test_wrong_credentials_are_rejected_by_the_real_browser_flow(
    _browser: Browser, live_app_with_alpha_auth: str
) -> None:
    context = _browser.new_context(
        http_credentials={"username": ALPHA_USERNAME, "password": "not-the-real-password"}
    )
    try:
        page = context.new_page()
        _assert_rejected_navigation(page, live_app_with_alpha_auth + "/")
    finally:
        context.close()
