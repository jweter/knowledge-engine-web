"""Acceptance: an online-source report runs end to end and leaves no temp data.

Only the external ``ke`` executable is replaced by a deterministic fake. The real
Web route, guard, AI client (subprocess, temp directory, content-hash and excerpt
validation) and report projection all run, so citations, uncertainty and cleanup
are asserted on the product path rather than on mocks of it.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from knowledge_engine_web import main
from knowledge_engine_web.ai_guardrails import AIRequestGuard
from knowledge_engine_web.config import Settings

FAKE_KE = textwrap.dedent(
    """\
    #!{python}
    import hashlib, json, os, sys, time
    from pathlib import Path

    args = sys.argv[1:]
    mode = os.environ["FAKE_KE_MODE"]
    log = Path(os.environ["FAKE_KE_LOG"])

    def opt(name):
        return args[args.index(name) + 1]

    if args[0] == "online-research":
        cache, out = Path(opt("--cache-dir")), Path(opt("--output"))
        ledger = Path(opt("--ledger-root"))
        with log.open("a") as fh:
            row = {{"root": str(out.parent), "max_sources": opt("--max-sources")}}
            fh.write(json.dumps(row) + "\\n")
        if mode == "hang":
            time.sleep(30)
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
                  "retrieved_at": "2026-11-02T12:00:00+00:00", "status": "retrieved",
                  "content_sha256": digest, "failure_reason": None, "title": "Caffeine trial"}},
                {{"source_id": "src-2", "url": "https://example.org/review", "provider": "crossref",
                  "retrieved_at": "2026-11-02T12:00:01+00:00", "status": "unavailable",
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
            json.dumps({{"search_run_id": "run-acceptance", "bundle": out.name}}))
        sys.exit(1 if mode == "provider_failure" else 0)
    if args[0] == "online-evidence-validate":
        sys.exit(0)
    sys.exit(2)
    """
)


@pytest.fixture
def online_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    monkeypatch.setattr(tempfile, "tempdir", None)
    fake = tmp_path / "ke"
    fake.write_text(FAKE_KE.format(python=sys.executable))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    if os.name == "nt":
        # Windows cannot execute a shebang script and takes its temp root from TMP/TEMP, not
        # TMPDIR. Without this the fake is never found (503) and these acceptance tests fail on
        # every Windows run of the repository preflight.
        script, fake = fake, tmp_path / "ke.cmd"
        fake.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
        monkeypatch.setenv("TMP", str(scratch))
        monkeypatch.setenv("TEMP", str(scratch))
    log = tmp_path / "ke.log"
    monkeypatch.setenv("FAKE_KE_LOG", str(log))
    monkeypatch.setenv("FAKE_KE_MODE", "ok")

    def settings(**overrides: Any) -> Settings:
        return Settings(
            _env_file=None, online_evidence_enabled=True, ke_executable=str(fake), **overrides
        )

    state: dict[str, Any] = {"overrides": {}}
    monkeypatch.setattr(main, "Settings", lambda: settings(**state["overrides"]))
    monkeypatch.setattr(
        "knowledge_engine_web.online_evidence_orchestration._GLOBAL_ONLINE_EVIDENCE_GUARD",
        AIRequestGuard(),
    )
    return {"scratch": scratch, "log": log, "state": state, "monkeypatch": monkeypatch}


def _ask() -> object:
    return TestClient(main.app).post(
        "/research/online-evidence", json={"question": "Does caffeine raise blood pressure?"}
    )


# Directories that security software on the machine drops into any directory used as a temp
# root (observed: Norton creates ``_norton_`` in a fresh %TEMP%). They are not the product's
# data, so they are not the product's leftovers.
FOREIGN_TEMP_DIRECTORIES = {"_norton_"}


def _leftovers(scratch: Path) -> list[Path]:
    return [
        path
        for path in scratch.rglob("*")
        if path.relative_to(scratch).parts[0] not in FOREIGN_TEMP_DIRECTORIES
    ]


def test_online_report_has_citations_uncertainty_and_leaves_no_temp_data(
    online_app: dict[str, object],
) -> None:
    scratch, log = online_app["scratch"], online_app["log"]
    assert isinstance(scratch, Path) and isinstance(log, Path)
    response = _ask()
    assert response.status_code == 200  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]

    # Not presented as a finished/synthesized report or as scientific truth.
    assert body["research_report_complete"] is False
    assert body["validation_scope"] == "source_content_consistency_not_scientific_truth"
    assert body["search_run_id"] == "run-acceptance"

    # Citations: claim -> excerpt -> source link, all from this request's content.
    evidence = body["evidence"]
    (excerpt,) = evidence["excerpts"]
    sources = {s["source_id"]: s for s in evidence["sources"]}
    assert excerpt["text"] == "raised systolic pressure by 8 mmHg"
    assert sources[excerpt["source_id"]]["url"] == "https://example.org/trial"
    (claim,) = evidence["claims"]
    assert claim["citations"] == [{"excerpt_id": excerpt["excerpt_id"], "stance": "supports"}]
    report = body["report"]
    (row,) = report["conclusion_rows"]
    assert row["conclusion"].startswith("[supported]")
    assert excerpt["excerpt_id"] in row["supporting_evidence_ids"]

    # Uncertainty: unavailable source and unassessed directness are disclosed.
    assert any("src-2 unavailable" in m for m in report["missing_evidence"])
    assert body["source_status_summary"]["status_counts"]["unavailable"] == 1
    assert report["research_state"] == "partial_answer"
    assert "Directness was not assessed." in report["direct_evidence_summary"]
    assert "no LLM synthesis" in " ".join(report["limitations"])
    assert "not independently verified" in json.dumps(report)

    # Retention: the run used one bounded temp dir under the scratch root, and
    # nothing (cache, bundle, ledger) survives the request.
    (record,) = [json.loads(line) for line in log.read_text().splitlines()]
    assert Path(record["root"]).parent == scratch
    assert Path(record["root"]).name.startswith("ke-online-research-")
    assert record["max_sources"] == "3"
    assert not Path(record["root"]).exists()
    assert _leftovers(scratch) == []


@pytest.mark.parametrize("mode", ["provider_failure", "hang"])
def test_failed_or_timed_out_online_run_returns_sanitized_error_and_cleans_up(
    online_app: dict[str, object], mode: str
) -> None:
    scratch, log, state = online_app["scratch"], online_app["log"], online_app["state"]
    mp = online_app["monkeypatch"]
    assert isinstance(scratch, Path) and isinstance(log, Path) and isinstance(state, dict)
    assert isinstance(mp, pytest.MonkeyPatch)
    mp.setenv("FAKE_KE_MODE", mode)
    if mode == "hang":
        state["overrides"] = {"online_evidence_request_timeout_seconds": 0.5}
    response = _ask()
    assert response.status_code == 502  # type: ignore[attr-defined]
    detail = response.json()["detail"]  # type: ignore[attr-defined]
    assert "No report was produced" in detail
    assert str(scratch) not in detail
    (record,) = [json.loads(line) for line in log.read_text().splitlines()]
    assert not Path(record["root"]).exists()
    assert _leftovers(scratch) == []
