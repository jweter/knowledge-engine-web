"""Shared pytest fixtures.

Only the real-server/real-Chromium browser E2E fixtures live here
(`page`, `live_app`). They are defined here, rather than imported into each
browser E2E test module, so pytest injects them by parameter name without
ruff's F811 flagging the import as an unused-name "redefinition" -- a known
false positive for the standard pytest fixture-as-parameter pattern. See
`tests/_browser_e2e_support.py` for the fixture data/env helpers these build
on, and `docs/browser_e2e_testing.md` for what the resulting test modules
cover.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from _pytest.tmpdir import TempPathFactory
from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from tests._browser_e2e_support import (
    candidate_chromium_executables,
    capture_page_screenshot,
    free_port,
    isolated_server_env,
    isolated_server_env_with_alpha_auth,
    seed_fixture_data,
    wait_until_serving,
)


@pytest.fixture(scope="module")
def _browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        attempted: list[str] = []
        browser: Browser | None = None
        for candidate in candidate_chromium_executables():
            if not Path(candidate).exists():
                continue
            try:
                browser = playwright.chromium.launch(headless=True, executable_path=candidate)
                break
            except PlaywrightError as exc:
                attempted.append(f"{candidate}: {exc}")
        if browser is None:
            try:
                browser = playwright.chromium.launch(headless=True)
            except PlaywrightError as exc:
                attempted.append(f"Playwright-managed default: {exc}")
                pytest.skip(
                    "No usable Chromium executable for browser E2E tests. Set "
                    "KE_WEB_TEST_CHROMIUM_PATH to a Chromium binary, or run "
                    "`poetry run playwright install chromium`. Tried: " + "; ".join(attempted)
                )
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def page(_browser: Browser, request: pytest.FixtureRequest) -> Iterator[Page]:
    new_page = _browser.new_page()
    try:
        yield new_page
    finally:
        capture_page_screenshot(new_page, nodeid=request.node.nodeid)
        new_page.close()


@pytest.fixture(scope="module")
def live_app(tmp_path_factory: TempPathFactory) -> Iterator[str]:
    """Run one isolated real Web app per browser-test module.

    Browser tests in a module are read-only against the seeded fixture authority,
    so restarting uvicorn for every individual assertion added substantial CI
    latency without increasing isolation. A module-scoped server preserves a
    clean database between modules while keeping the critical-path browser gate
    small enough to run as required CI.
    """
    tmp_path = tmp_path_factory.mktemp("browser-e2e-app")
    _, evidence_path = seed_fixture_data(tmp_path)
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "knowledge_engine_web.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=isolated_server_env(tmp_path, evidence_path, port),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_until_serving(base_url, process)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


@pytest.fixture
def live_app_with_research_available(tmp_path: Path) -> Iterator[str]:
    """Run the real Web app with static Research prerequisites available.

    The fixture supplies only local, inert prerequisites needed for the Ask UI
    to render its Research controls. It does not contact Ollama, Core, or any
    scholarly provider, and the test route does not start a Research run.
    """
    _, evidence_path = seed_fixture_data(tmp_path)
    sources_path = tmp_path / "sources.csv"
    sources_path.write_text("source_id\nfixture\n", encoding="utf-8")
    research_papers_dir = tmp_path / "research_papers"
    research_papers_dir.mkdir()

    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = isolated_server_env(tmp_path, evidence_path, port)
    env.update(
        {
            "KE_WEB_LLM_MODEL": "browser-e2e-fixture-model",
            "KE_WEB_SOURCES_PATH": str(sources_path),
            "KE_WEB_KE_EXECUTABLE": sys.executable,
            "KE_WEB_RESEARCH_PAPERS_DIR": str(research_papers_dir),
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "knowledge_engine_web.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_until_serving(base_url, process)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


@pytest.fixture
def live_app_with_alpha_auth(tmp_path: Path) -> Iterator[str]:
    """Same real Web app as `live_app`, with the alpha Basic Auth gate turned on."""
    _, evidence_path = seed_fixture_data(tmp_path)
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "knowledge_engine_web.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=isolated_server_env_with_alpha_auth(tmp_path, evidence_path, port),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_until_serving(base_url, process, ready_on_401=True)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
