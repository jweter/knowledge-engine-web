"""Shared real-server fixture data/env helpers for browser E2E test modules.

The actual pytest fixtures (`page`, `live_app`) live in `tests/conftest.py`
so every browser E2E test module gets them automatically without an import
that ruff's F811 flags as a fixture-name/parameter-name "redefinition" (a
known false positive for the standard pytest fixture-as-parameter pattern).
This module holds the fixture *data* and server-environment helpers those
conftest fixtures build on, plus the shared fixture constants (question,
evidence record id, paper metadata) test modules import directly.

Extend this module -- or add a sibling test module -- rather than
re-deriving the live-server/fixture-data setup. See
`docs/browser_e2e_testing.md`.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

from sqlalchemy import Engine, MetaData, Table, insert, text

from tests._fixtures import build_engine, create_graph_tables, create_papers_table

QUESTION = "does semaglutide increase IQ?"
EVIDENCE_RECORD_ID = "ev-iq-1"
PAPER_DOI = "10.1000/cognitive"
PAPER_TITLE = "Semaglutide and cognitive outcomes"
PAPER_ABSTRACT = "A study evaluated whether semaglutide increased IQ scores in participants."


def candidate_chromium_executables() -> list[str]:
    candidates = []
    override = os.environ.get("KE_WEB_TEST_CHROMIUM_PATH")
    if override:
        candidates.append(override)
    candidates.append("/opt/pw-browsers/chromium")
    return candidates


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def seed_fixture_data(tmp_path: Path) -> tuple[Engine, Path]:
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
            insert(papers).values(id=1, title=PAPER_TITLE, doi=PAPER_DOI, abstract=PAPER_ABSTRACT)
        )
        connection.execute(
            text(
                "INSERT INTO paper_search(rowid, title, abstract, body_text, raw_text) "
                "VALUES (1, :title, :abstract, '', '')"
            ),
            {"title": PAPER_TITLE, "abstract": PAPER_ABSTRACT},
        )
        graph_claims = Table("graph_claims", MetaData(), autoload_with=engine)
        connection.execute(
            insert(graph_claims).values(
                id=1,
                evidence_record_id=EVIDENCE_RECORD_ID,
                created_at="2026-01-01T00:00:00Z",
            )
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "evidence_record_id": EVIDENCE_RECORD_ID,
                "research_question": "Does semaglutide increase IQ?",
                "claim_text": "Semaglutide showed no statistically significant IQ change.",
                "evidence_direction": "null_result",
                "source_type": "paper",
                "source_title": PAPER_TITLE,
                "source_doi": PAPER_DOI,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return engine, evidence_path


def wait_until_serving(base_url: str, process: subprocess.Popen[bytes]) -> None:
    import time
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + 20
    last_http_error: urllib.error.HTTPError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = (
                process.stdout.read().decode("utf-8", errors="replace") if process.stdout else ""
            )
            raise RuntimeError(f"uvicorn exited early (code {process.returncode}):\n{output}")
        try:
            urllib.request.urlopen(base_url + "/", timeout=1).read()  # noqa: S310
            return
        except urllib.error.HTTPError as exc:
            # The server answered but with a non-2xx status on every attempt (e.g. a
            # fixture-env misconfiguration tripping alpha auth) -- surface that instead
            # of letting it look identical to "never came up" for the full deadline.
            last_http_error = exc
            time.sleep(0.2)
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.2)
    process.kill()
    if last_http_error is not None:
        raise RuntimeError(
            f"Real Web server at {base_url} kept answering HTTP {last_http_error.code} "
            f"({last_http_error.reason}) instead of becoming reachable -- check the "
            "fixture server env, not a startup timing issue"
        )
    raise RuntimeError(f"Real Web server never became reachable at {base_url}")


def isolated_server_env(tmp_path: Path, evidence_path: Path, port: int) -> dict[str, str]:
    """Return a deterministic child environment that cannot inherit Research authority.

    Settings also load repository ``.env``, so every KE_WEB setting that can
    enable external calls, authentication, or durable writes is explicitly
    overridden with a safe value rather than merely removed from ``os.environ``.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("KE_WEB_")}
    env.update(
        {
            "KE_WEB_DATABASE_URL": f"sqlite:///{tmp_path / 'fixture.sqlite3'}",
            "KE_WEB_EVIDENCE_RECORDS_PATH": str(evidence_path),
            "KE_WEB_RELATIONSHIP_RECORDS_PATH": "",
            "KE_WEB_WHATS_CHANGED_BASELINE_PATH": str(tmp_path / "whats_changed.json"),
            "KE_WEB_SNAPSHOT_METADATA_PATH": str(tmp_path / "snapshot.json"),
            "KE_WEB_HOST": "127.0.0.1",
            "KE_WEB_PORT": str(port),
            # Deliberately omitted, not set to "": AlphaBasicAuthMiddleware treats
            # a set-but-empty username/password as "configured" and fails closed
            # with 401 on every request (including this fixture's own readiness
            # probe below). Leaving them unset makes Settings() see None/None,
            # which is the actual "alpha gate disabled" state this suite needs.
            "KE_WEB_LLM_MODEL": "",
            "KE_WEB_OLLAMA_HOST": "http://127.0.0.1:1",
            "KE_WEB_SOURCES_PATH": "",
            "KE_WEB_SESSION_DB_PATH": str(tmp_path / "research_sessions.db"),
            "KE_WEB_SESSION_STORAGE_MODE": "local",
            "KE_WEB_SESSION_PERSISTENT_ROOT": "",
            "KE_WEB_KE_EXECUTABLE": str(tmp_path / "missing-ke"),
            "KE_WEB_CORE_CLI_COMMAND_PREFLIGHT": "false",
            "KE_WEB_AI_REQUEST_TIMEOUT_SECONDS": "1",
            "KE_WEB_AI_MAX_CONCURRENT_REQUESTS": "1",
            "KE_WEB_AI_RATE_LIMIT_REQUESTS": "1",
            "KE_WEB_AI_RATE_LIMIT_WINDOW_SECONDS": "60",
            "KE_WEB_ASYNC_RESEARCH_ENABLED": "false",
            "KE_WEB_RESEARCH_PAPERS_DIR": str(tmp_path / "research_papers"),
            "KE_WEB_FEDERATED_DISCOVERY_LEDGER_ROOT": str(tmp_path / "federated_runs"),
            "KE_WEB_FEDERATED_OPENALEX_API_KEY": "",
            "KE_WEB_FEDERATED_SEMANTIC_SCHOLAR_API_KEY": "",
            "KE_WEB_DISCOVERY_REQUEST_TIMEOUT_SECONDS": "1",
            "KE_WEB_DISCOVERY_MAX_CONCURRENT_REQUESTS": "1",
            "KE_WEB_DISCOVERY_RATE_LIMIT_REQUESTS": "1",
            "KE_WEB_DISCOVERY_RATE_LIMIT_WINDOW_SECONDS": "60",
            "KE_WEB_DISCOVERY_LEDGER_STORAGE_MODE": "local",
            "KE_WEB_DISCOVERY_LEDGER_PERSISTENT_ROOT": "",
        }
    )
    return env
