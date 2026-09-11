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
from playwright.sync_api import Browser, Error, Page

from tests._browser_e2e_support import ALPHA_PASSWORD, ALPHA_USERNAME

pytestmark = pytest.mark.browser_e2e

# A real Chromium network stack has been observed to reject a Basic Auth
# challenge two different ways depending on Chromium version/build: either
# `page.goto` completes and returns a 401 response, or the navigation itself
# fails with one of these `net::` errors before any response is available.
# Either outcome proves the real browser never rendered the app -- the point
# of this real-browser (not TestClient) coverage -- so both count as pass.
_BROWSER_LEVEL_AUTH_REJECTION_ERRORS = (
    "net::ERR_INVALID_AUTH_CREDENTIALS",
    "net::ERR_HTTP_RESPONSE_CODE_FAILURE",
)


def _assert_rejected_navigation(page: Page, url: str) -> None:
    """Assert the real browser receives the Basic Auth rejection without rendering the app."""
    try:
        response = page.goto(url)
    except Error as exc:
        assert any(marker in str(exc) for marker in _BROWSER_LEVEL_AUTH_REJECTION_ERRORS), (
            f"Unexpected navigation error, not a known auth rejection: {exc}"
        )
        return
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
