"""Real-browser coverage for WCAG 2.3.3 (Animation from Interactions):
`docs/manual_accessibility_checklist.md` row 7 asks whether the
constellation/neural-web decorative motion (`knowledge_engine_web/static/
knowledge_constellation.js`) actually respects the OS-level
`prefers-reduced-motion: reduce` setting.

`tests/test_knowledge_constellation_face.py::test_constellation_motion_is_accessibility_safe`
only asserts that the right strings (`matchMedia(...)`, the CSS media query)
exist in the source files -- it cannot catch a logic bug that leaves the
canvas animating anyway, because the canvas motion is driven entirely by a
`requestAnimationFrame` loop in JavaScript, not by CSS, so axe-core and
CSS-only checks cannot see it either. This module instead emulates the real
OS-level media feature in a real Chromium instance and observes actual
rendered output over time:

- under `prefers-reduced-motion: reduce`, the canvas's pixel content is
  identical before and after a wait (the animation loop never restarts
  itself), and the CSS-driven headline aurora animation is neutralized;
- under the default `no-preference` setting, the canvas visibly changes
  over the same wait (a control case proving the comparison technique
  itself is sensitive to real motion, so the reduced-motion assertion isn't
  vacuously true).

What remains manual (per the checklist): whether a screen reader announces
anything about the motion, and subjective judgment for any other
interaction-triggered animation this repository adds in the future.
"""

from __future__ import annotations

from typing import cast

import pytest
from playwright.sync_api import Page, ViewportSize

pytestmark = pytest.mark.browser_e2e

_VIEWPORT: ViewportSize = {"width": 800, "height": 600}


def _canvas_data_url(page: Page) -> str:
    return cast(
        str,
        page.evaluate(
            "() => document.getElementById('knowledge-constellation-field')?.toDataURL() ?? ''"
        ),
    )


def _hero_heading_animation_duration(page: Page) -> str:
    return cast(
        str,
        page.locator(".landing-hero-copy h1").evaluate(
            "element => getComputedStyle(element).animationDuration"
        ),
    )


def test_constellation_canvas_is_static_when_reduced_motion_preferred(
    page: Page, live_app: str
) -> None:
    page.set_viewport_size(_VIEWPORT)
    page.emulate_media(reduced_motion="reduce")
    page.goto(live_app + "/")

    before = _canvas_data_url(page)
    assert before, "expected the constellation canvas to render something"
    page.wait_for_timeout(400)
    after = _canvas_data_url(page)

    assert before == after, (
        "the constellation canvas kept redrawing even though "
        "prefers-reduced-motion: reduce is active (WCAG 2.3.3)"
    )
    assert _hero_heading_animation_duration(page) == "1e-06s"


def test_constellation_canvas_animates_by_default(page: Page, live_app: str) -> None:
    # Control case: proves the before/after canvas comparison above actually
    # detects real motion, so the reduced-motion assertion isn't vacuously
    # true (e.g. because the canvas never renders anything at all).
    page.set_viewport_size(_VIEWPORT)
    page.emulate_media(reduced_motion="no-preference")
    page.goto(live_app + "/")

    before = _canvas_data_url(page)
    page.wait_for_timeout(400)
    after = _canvas_data_url(page)

    assert before != after, (
        "expected the constellation canvas to keep animating under the "
        "default no-preference motion setting"
    )
    assert _hero_heading_animation_duration(page) not in ("0s", "1e-06s")


def test_about_page_constellation_layer_also_respects_reduced_motion(
    page: Page, live_app: str
) -> None:
    # The constellation layer runs site-wide (base.html's body class), not
    # only on the homepage -- verify a second, non-homepage page too.
    page.set_viewport_size(_VIEWPORT)
    page.emulate_media(reduced_motion="reduce")
    page.goto(live_app + "/about")

    before = _canvas_data_url(page)
    assert before
    page.wait_for_timeout(400)
    after = _canvas_data_url(page)

    assert before == after
