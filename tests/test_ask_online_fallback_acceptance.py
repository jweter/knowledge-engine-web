"""Acceptance: the default /ask flow falls back to the real online-evidence-only
Research path end to end when no local corpus/Ollama is configured.

Only the external ``ke`` executable is replaced by a deterministic fake, and only
``llm_model`` is left unconfigured (the genuine "no local AI capability" case). The
real ``GET /ask`` route, the real background job executor
(``research_jobs.submit_research_job`` / ``_execute_research_job``), the real
online-evidence-only fallback (``research_jobs._try_online_fallback`` ->
``run_guarded_online_research_answer`` -> AI's ``run_online_research_question``, which
retrieves and content-checks evidence through the same Core CLI boundary
(``online-research`` / ``online-evidence-validate``) proven in
``tests/test_online_report_acceptance.py``), and the real ``GET /ask/session/{id}``
polling route all run. Nothing about the fallback itself is mocked, so citations,
uncertainty and cleanup are asserted on the product path rather than on a Python-level
stand-in for it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_engine_web import ai_orchestration, main
from knowledge_engine_web.ai_guardrails import AIRequestGuard

FAKE_KE = textwrap.dedent(
    """\
    #!{python}
    import hashlib, json, os, sys
    from pathlib import Path

    args = sys.argv[1:]
    log = Path(os.environ["FAKE_KE_LOG"])

    def opt(name):
        return args[args.index(name) + 1]

    if args[0] == "online-research":
        cache, out = Path(opt("--cache-dir")), Path(opt("--output"))
        ledger = Path(opt("--ledger-root"))
        with log.open("a") as fh:
            row = {{"root": str(out.parent), "max_sources": opt("--max-sources")}}
            fh.write(json.dumps(row) + "\\n")
        cache.mkdir(parents=True)
        ledger.mkdir(parents=True)
        (ledger / "run.sqlite3").write_bytes(b"ledger")
        text = "Caffeine raised systolic pressure by 8 mmHg in a small trial. No long-term data."
        digest = hashlib.sha256(text.encode()).hexdigest()
        (cache / (digest + ".txt")).write_text(text)
        quote = "raised systolic pressure by 8 mmHg"
        start = text.index(quote)
        material = "src-1\\n" + str(start) + "\\n" + quote
        excerpt_id = "src-1#" + hashlib.sha256(material.encode()).hexdigest()[:12]
        bundle = {{
            "schema": "ke-online-evidence/v1",
            "question": "Does caffeine raise blood pressure?",
            "sources": [
                {{"source_id": "src-1", "url": "https://example.org/trial", "provider": "pubmed",
                  "retrieved_at": "2026-11-16T12:00:00+00:00", "status": "retrieved",
                  "content_sha256": digest, "failure_reason": None, "title": "Caffeine trial"}},
                {{"source_id": "src-2", "url": "https://example.org/review", "provider": "crossref",
                  "retrieved_at": "2026-11-16T12:00:01+00:00", "status": "unavailable",
                  "content_sha256": None, "failure_reason": "provider timed out", "title": None}},
            ],
            "excerpts": [{{"excerpt_id": excerpt_id, "source_id": "src-1", "text": quote,
                           "char_start": start, "char_end": start + len(quote)}}],
            "claims": [{{"claim_id": "c1", "text": "Caffeine acutely raises blood pressure.",
                         "status": "supported",
                         "citations": [{{"excerpt_id": excerpt_id, "stance": "supports"}}]}}],
        }}
        out.write_text(json.dumps(bundle))
        out.with_name(out.name + ".discovery.json").write_text(
            json.dumps({{"search_run_id": "run-fallback-acceptance", "bundle": out.name}}))
        sys.exit(0)
    if args[0] == "online-evidence-validate":
        sys.exit(0)
    sys.exit(2)
    """
)

_EXCERPT_TEXT = "raised systolic pressure by 8 mmHg"
_SOURCE_TEXT = "Caffeine raised systolic pressure by 8 mmHg in a small trial. No long-term data."
_EXCERPT_START = _SOURCE_TEXT.index(_EXCERPT_TEXT)
_EXCERPT_ID = (
    "src-1#" + hashlib.sha256(f"src-1\n{_EXCERPT_START}\n{_EXCERPT_TEXT}".encode()).hexdigest()[:12]
)

# Directories security software drops into any fresh temp root (observed: Norton
# creates ``_norton_``). Not the product's data, so not the product's leftovers --
# see the identical allowance in tests/test_online_report_acceptance.py.
_FOREIGN_TEMP_DIRECTORIES = {"_norton_"}


def _leftovers(scratch: Path) -> list[Path]:
    return [
        path
        for path in scratch.rglob("*")
        if path.relative_to(scratch).parts[0] not in _FOREIGN_TEMP_DIRECTORIES
    ]


@pytest.fixture
def fallback_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    monkeypatch.setattr(tempfile, "tempdir", None)
    fake = tmp_path / "ke"
    fake.write_text(FAKE_KE.format(python=sys.executable))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    if os.name == "nt":
        # Windows cannot execute a shebang script and takes its temp root from TMP/TEMP,
        # not TMPDIR -- see the identical allowance in tests/test_online_report_acceptance.py.
        script, fake = fake, tmp_path / "ke.cmd"
        fake.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
        monkeypatch.setenv("TMP", str(scratch))
        monkeypatch.setenv("TEMP", str(scratch))
    log = tmp_path / "ke.log"
    monkeypatch.setenv("FAKE_KE_LOG", str(log))

    session_db = tmp_path / "research_sessions.sqlite3"
    monkeypatch.setenv("KE_WEB_DATABASE_URL", f"sqlite:///{tmp_path / 'knowledge.sqlite3'}")
    monkeypatch.setenv("KE_WEB_SESSION_DB_PATH", str(session_db))
    monkeypatch.setenv("KE_WEB_ASYNC_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("KE_WEB_ONLINE_EVIDENCE_ENABLED", "true")
    monkeypatch.setenv("KE_WEB_KE_EXECUTABLE", str(fake))
    monkeypatch.delenv("KE_WEB_LLM_MODEL", raising=False)
    monkeypatch.setattr(main, "answer_retrieval", lambda *_args, **_kwargs: [])
    # A fresh guard per test: the real module-level singleton is shared process-wide,
    # and other tests' calls to the real online fallback must not leave this test
    # rate-limited or over its concurrency slot.
    monkeypatch.setattr(ai_orchestration, "_GLOBAL_ONLINE_ASK_GUARD", AIRequestGuard())
    return {"scratch": scratch, "log": log, "session_db": session_db}


def _poll_until_terminal(
    client: TestClient, session_id: str, *, timeout_seconds: float = 15.0
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    payload: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/ask/session/{session_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["terminal"]:
            return payload
        time.sleep(0.05)
    pytest.fail(f"research job {session_id!r} did not reach a terminal state in time: {payload}")


def test_ask_falls_back_to_real_online_evidence_and_cleans_up_temp_data(
    fallback_app: dict[str, object],
) -> None:
    scratch = fallback_app["scratch"]
    log = fallback_app["log"]
    assert isinstance(scratch, Path) and isinstance(log, Path)

    client = TestClient(main.app)
    question = "Does caffeine raise blood pressure?"

    submitted = client.get("/ask", params={"q": question})
    assert submitted.status_code == 200
    # The genuine, unmocked local-capability check: no model is configured, so the
    # complete local-corpus/Ollama path is unavailable, yet Research still starts
    # because online evidence widens availability.
    assert "Research session running" in submitted.text
    assert "Broader Research is unavailable" not in submitted.text
    match = re.search(r'data-session-id="([^"]+)"', submitted.text)
    assert match is not None
    session_id = match.group(1)

    payload = _poll_until_terminal(client, session_id)

    assert payload["job_status"] == "completed"
    assert payload["terminal"] is True
    assert payload["visitor_error"] is None
    result = payload["result"]
    assert isinstance(result, dict)
    assert result["evidence_source"] == "online_evidence_only"
    assert result["narrative_releaseable"] is False
    assert result["online_search_run_id"] == "run-fallback-acceptance"

    # Citations: a claim's supporting evidence resolves to the excerpt this run's fake
    # Core CLI produced from one specific source (src-1, https://example.org/trial).
    research_report = result["research_report"]
    assert isinstance(research_report, dict)
    assert research_report["available"] is True
    report = research_report["report"]
    (row,) = report["conclusion_rows"]
    assert row["conclusion"].startswith("[supported]")
    assert _EXCERPT_ID in row["supporting_evidence_ids"]

    # Uncertainty: the unavailable second source is disclosed as missing evidence, and
    # the research state is capped below a full researched answer on this path.
    assert any("src-2 unavailable" in note for note in report["missing_evidence"])
    assert report["research_state"] == "partial_answer"
    assert "Directness was not assessed." in report["direct_evidence_summary"]
    assert "no LLM synthesis" in " ".join(report["limitations"])

    # Retention: the run used one bounded temp dir under the scratch root, and nothing
    # (cache, bundle, ledger) survives past this job reaching a terminal state.
    (record,) = [json.loads(line) for line in log.read_text().splitlines()]
    assert Path(record["root"]).parent == scratch
    assert Path(record["root"]).name.startswith("ke-online-research-")
    assert not Path(record["root"]).exists()
    assert _leftovers(scratch) == []
