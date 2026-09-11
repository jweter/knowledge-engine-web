"""Real headless-Chromium browser end-to-end tests for the Ask product path.

`docs/INDUSTRY_REALITY_CHECK.md` flags "no Playwright/Selenium-style browser
workflow evidence was found" as a P1 production gap. This module closes that
gap for the Ask critical path: it starts the real FastAPI application as a
real HTTP server (a `uvicorn` subprocess) against a real SQLite fixture
database and a real Evidence Records JSONL file -- the same shapes
`tests/_fixtures.py` and `tests/test_ask_question_contract.py` already use
for Python-level tests -- then drives it with a real headless Chromium
instance. No mocked backend authority: Research/AI capability is left
genuinely unconfigured, so these tests also exercise the honest,
fail-closed "Broader Research is unavailable on this deployment" path
rather than fabricating a research result.

Chromium is optional at test time. When no usable executable is found (a
contributor machine or CI runner that has not installed Playwright's
browsers), every test in this module is skipped rather than failed --
see `_browser` below. `.github/workflows/browser-e2e.yml` installs
Chromium and always runs this module for real.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from sqlalchemy import Engine, MetaData, Table, insert, text

from tests._fixtures import build_engine, create_graph_tables, create_papers_table

pytestmark = pytest.mark.browser_e2e

_QUESTION = "does semaglutide increase IQ?"
_EVIDENCE_RECORD_ID = "ev-iq-1"
_PAPER_DOI = "10.1000/cognitive"
_PAPER_TITLE = "Semaglutide and cognitive outcomes"
_PAPER_ABSTRACT = "A study evaluated whether semaglutide increased IQ scores in participants."


def _candidate_chromium_executables() -> list[str]:
    candidates = []
    override = os.environ.get("KE_WEB_TEST_CHROMIUM_PATH")
    if override:
        candidates.append(override)
    # The stable symlink this harness's pre-installed Chromium is published
    # at (see the environment's own guidance); not present on a plain
    # contributor machine or an unprepared CI runner, which is fine -- the
    # fallback below tries Playwright's own default resolution instead.
    candidates.append("/opt/pw-browsers/chromium")
    return candidates


@pytest.fixture(scope="module")
def _browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        attempted: list[str] = []
        browser: Browser | None = None
        for candidate in _candidate_chromium_executables():
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
def page(_browser: Browser) -> Iterator[Page]:
    new_page = _browser.new_page()
    try:
        yield new_page
    finally:
        new_page.close()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _seed_fixture_data(tmp_path: Path) -> tuple[Engine, Path]:
    """Build a real SQLite database and Evidence Records JSONL, mirroring core's schema.

    One paper with a directly matching abstract (same shape as
    `test_ask_question_contract.py`'s direct-match case) plus one graph
    claim and evidence record for it, so the Ask page has a real
    source-linked citation to navigate rather than an empty demo.
    """

    engine = build_engine(tmp_path)
    create_papers_table(engine)
    create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS paper_search
                USING fts5(title, abstract, body_text, raw_text, tokenize='porter unicode61')
                """
            )
        )
        papers = Table("papers", MetaData(), autoload_with=engine)
        connection.execute(
            insert(papers).values(
                id=1, title=_PAPER_TITLE, doi=_PAPER_DOI, abstract=_PAPER_ABSTRACT
            )
        )
        connection.execute(
            text(
                "INSERT INTO paper_search(rowid, title, abstract, body_text, raw_text) "
                "VALUES (1, :title, :abstract, '', '')"
            ),
            {"title": _PAPER_TITLE, "abstract": _PAPER_ABSTRACT},
        )
        graph_claims = Table("graph_claims", MetaData(), autoload_with=engine)
        connection.execute(
            insert(graph_claims).values(
                id=1,
                evidence_record_id=_EVIDENCE_RECORD_ID,
                created_at="2026-01-01T00:00:00Z",
            )
        )

    evidence_path = tmp_path / "evidence_records.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "evidence_record_id": _EVIDENCE_RECORD_ID,
                "research_question": "Does semaglutide increase IQ?",
                "claim_text": "Semaglutide showed no statistically significant IQ change.",
                "evidence_direction": "null_result",
                "source_type": "paper",
                "source_title": _PAPER_TITLE,
                "source_doi": _PAPER_DOI,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return engine, evidence_path


def _wait_until_serving(base_url: str, process: subprocess.Popen[bytes]) -> None:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = (
                process.stdout.read().decode("utf-8", errors="replace") if process.stdout else ""
            )
            raise RuntimeError(f"uvicorn exited early (code {process.returncode}):\n{output}")
        try:
            urllib.request.urlopen(base_url + "/", timeout=1).read()  # noqa: S310
            return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.2)
    process.kill()
    raise RuntimeError(f"Real Web server never became reachable at {base_url}")


@pytest.fixture
def live_app(tmp_path: Path) -> Iterator[str]:
    """Run the actual `knowledge_engine_web` FastAPI app as a real HTTP server.

    Deliberately leaves Research/AI capability unconfigured (no `ke`
    executable, no Ollama) so Ask takes its real, honest indexed-retrieval
    fallback -- the same path an unequipped deployment takes -- instead of
    a faked research result. See `docs/agent-development-policy.md` section
    1 and `knowledge_engine_web/ai_orchestration.py`'s capability gate.
    """

    _, evidence_path = _seed_fixture_data(tmp_path)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "KE_WEB_DATABASE_URL": f"sqlite:///{tmp_path / 'fixture.sqlite3'}",
        "KE_WEB_EVIDENCE_RECORDS_PATH": str(evidence_path),
        "KE_WEB_HOST": "127.0.0.1",
        "KE_WEB_PORT": str(port),
    }
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
        _wait_until_serving(base_url, process)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def test_homepage_loads_the_real_application(page: Page, live_app: str) -> None:
    page.goto(live_app + "/")

    assert "Knowledge Engine" in page.title()


def test_ask_shows_a_direct_indexed_match_and_an_honest_capability_notice(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=" + _QUESTION.replace(" ", "+").replace("?", "%3F"))

    # Real, deterministic indexed retrieval renders a source-linked result --
    # not a fabricated answer.
    assert page.get_by_text("Direct match").first.is_visible()
    assert page.get_by_role("link", name=_PAPER_TITLE).is_visible()
    citation_link = page.locator(f'a[href="/claims/{_EVIDENCE_RECORD_ID}"]')
    assert citation_link.is_visible()

    # This test environment has no Research/AI capability configured, so the
    # page must say so honestly rather than pretending research ran.
    assert "Broader Research is unavailable on this deployment" in page.content()


def test_citation_link_navigates_to_a_real_evidence_record_detail_page(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=" + _QUESTION.replace(" ", "+").replace("?", "%3F"))

    page.locator(f'a[href="/claims/{_EVIDENCE_RECORD_ID}"]').first.click()

    assert page.url == live_app + "/claims/" + _EVIDENCE_RECORD_ID
    assert page.locator("h1", has_text=_EVIDENCE_RECORD_ID).is_visible()
    assert "Semaglutide showed no statistically significant IQ change." in page.content()


def test_ask_with_no_matching_evidence_does_not_fabricate_an_answer(
    page: Page, live_app: str
) -> None:
    page.goto(live_app + "/ask?q=does+topical+minoxidil+regrow+hair%3F")

    assert "No relevant papers found in the indexed corpus." in page.content()
    assert "Direct match" not in page.content()


def test_ask_page_is_usable_at_a_mobile_viewport(page: Page, live_app: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})

    page.goto(live_app + "/ask?q=" + _QUESTION.replace(" ", "+").replace("?", "%3F"))

    assert page.get_by_label("Question").is_visible()
    assert page.get_by_role("button", name="Ask").is_visible()
    citation_link = page.locator(f'a[href="/claims/{_EVIDENCE_RECORD_ID}"]')
    assert citation_link.is_visible()
    body_width = page.evaluate("document.documentElement.scrollWidth")
    assert body_width <= 390, f"page overflows a 390px viewport (scrollWidth={body_width})"
