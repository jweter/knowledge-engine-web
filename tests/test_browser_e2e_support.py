"""Unit tests for the shared browser-E2E screenshot-evidence helper.

``capture_page_screenshot`` is pure enough logic (env-var gate, nodeid
sanitization, and swallowing capture failures) to unit-test directly with a
fake page rather than only exercising it indirectly through a real Chromium
run. See ``docs/UNATTENDED_VERIFICATION.md`` for how the unattended worker
uses it.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from tests._browser_e2e_support import SCREENSHOT_DIR_ENV_VAR, capture_page_screenshot


class _FakePage:
    def __init__(self, *, raise_error: bool = False) -> None:
        self.raise_error = raise_error
        self.screenshot_paths: list[str] = []

    def screenshot(self, *, path: str) -> None:
        if self.raise_error:
            raise PlaywrightError("page is closed")
        self.screenshot_paths.append(path)
        Path(path).write_bytes(b"fake-png")


def test_capture_page_screenshot_is_a_noop_when_env_var_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SCREENSHOT_DIR_ENV_VAR, raising=False)
    page = _FakePage()

    capture_page_screenshot(cast(Page, page), nodeid="tests/test_x.py::test_y")

    assert page.screenshot_paths == []


def test_capture_page_screenshot_writes_a_sanitized_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "shots"
    monkeypatch.setenv(SCREENSHOT_DIR_ENV_VAR, str(target))
    page = _FakePage()

    capture_page_screenshot(cast(Page, page), nodeid="tests/test_x.py::test_y[chromium]")

    files = list(target.glob("*.png"))
    assert len(files) == 1
    assert "::" not in files[0].name
    assert "[" not in files[0].name
    assert "]" not in files[0].name


def test_capture_page_screenshot_creates_the_directory_if_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "does" / "not" / "exist" / "yet"
    monkeypatch.setenv(SCREENSHOT_DIR_ENV_VAR, str(target))
    page = _FakePage()

    capture_page_screenshot(cast(Page, page), nodeid="tests/test_x.py::test_y")

    assert target.is_dir()
    assert len(page.screenshot_paths) == 1


def test_capture_page_screenshot_swallows_playwright_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SCREENSHOT_DIR_ENV_VAR, str(tmp_path / "shots"))
    page = _FakePage(raise_error=True)

    capture_page_screenshot(cast(Page, page), nodeid="tests/test_x.py::test_y")
