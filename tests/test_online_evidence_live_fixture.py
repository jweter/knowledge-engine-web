"""Real, non-mocked proof of Web's online-evidence route against Core's fixture server.

`knowledge-engine-core` publishes `ke online-evidence-fixture-server` so that
this repository can run its own pipeline against a known Core response instead
of mocking the Core CLI boundary (see Core's `docs/online_evidence_contract.md`,
"Standalone integration fixture server"). Every other online-evidence test here
replaces the `ke` subprocess with a fake script or a monkeypatched bridge. This
module does not: it posts to Web's real `/research/online-evidence` route, which
runs the real guard, the real `ke online-research` and `ke online-evidence-validate`
subprocesses through AI's unmodified bridge, and the real report projection.

The only injected value is the fixture server's loopback port, passed through
AI's documented `fixture_server_port` integration-test option. No corpus, no
database and no Ollama service exist in this test.

Skips cleanly when `ke` is not on `PATH`; CI installs Core alongside Web, see
`.github/workflows/online-evidence-live-fixture.yml`.
"""

from __future__ import annotations

import functools
import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from knowledge_engine_ai.ke_client import online_research_evidence

from knowledge_engine_web import main
from knowledge_engine_web import online_evidence_orchestration as online
from knowledge_engine_web.ai_guardrails import AIRequestGuard

pytestmark = pytest.mark.skipif(
    shutil.which("ke") is None,
    reason="knowledge-engine-core's `ke` CLI is not on PATH; this is a real, non-mocked "
    "integration test against it, not a unit test -- see this module's docstring.",
)

_QUESTION = "Does semaglutide reduce body weight versus placebo?"


@pytest.fixture
def fixture_server() -> Iterator[subprocess.Popen[str]]:
    server = subprocess.Popen(
        ["ke", "online-evidence-fixture-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        yield server
    finally:
        assert server.stdin is not None
        server.stdin.close()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.terminate()
            server.wait(timeout=5)
        for stream in (server.stdout, server.stderr):
            if stream is not None:
                stream.close()


def _announced_port(server: subprocess.Popen[str]) -> int:
    assert server.stdout is not None
    line = server.stdout.readline()
    if not line:
        stderr = server.stderr.read() if server.stderr is not None else ""
        raise AssertionError(f"fixture server produced no announcement; stderr={stderr!r}")
    payload = json.loads(line)
    assert set(payload["pages"]) == {"retrievable", "http_500", "oversized"}
    port = payload["port"]
    assert isinstance(port, int)
    return port


def _enable_online_evidence(monkeypatch: pytest.MonkeyPatch, port: int, tmp_path: Path) -> None:
    ke = shutil.which("ke")
    assert ke is not None
    monkeypatch.setenv("KE_WEB_ONLINE_EVIDENCE_ENABLED", "true")
    monkeypatch.setenv("KE_WEB_KE_EXECUTABLE", ke)
    monkeypatch.setenv("KE_WEB_ONLINE_EVIDENCE_MAX_SOURCES", "3")
    # A fresh guard so rate-limit state from other tests cannot admit or refuse this one.
    monkeypatch.setattr(online, "_GLOBAL_ONLINE_EVIDENCE_GUARD", AIRequestGuard())
    monkeypatch.setattr(
        online,
        "online_research_evidence",
        functools.partial(online_research_evidence, fixture_server_port=port),
    )
    # Run from an empty directory so any corpus/database artefact would be visible.
    monkeypatch.chdir(tmp_path)


def test_online_evidence_route_against_real_fixture_server(
    fixture_server: subprocess.Popen[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_online_evidence(monkeypatch, _announced_port(fixture_server), tmp_path)

    response = TestClient(main.app).post("/research/online-evidence", json={"question": _QUESTION})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "content_checked_retrieval_only"
    assert body["research_report_complete"] is False
    assert body["validation_scope"] == "source_content_consistency_not_scientific_truth"
    assert body["search_run_id"].strip()

    evidence = body["evidence"]
    assert evidence["question"] == _QUESTION
    sources = {source["source_id"]: source for source in evidence["sources"]}
    # Core's fixture discovery names each candidate "doi:10.1/<good|broken|huge>".
    assert set(sources) == {"doi:10.1/good", "doi:10.1/broken", "doi:10.1/huge"}

    good = sources["doi:10.1/good"]
    assert good["status"] == "retrieved"
    assert good["content_sha256"]

    broken = sources["doi:10.1/broken"]
    assert broken["status"] == "failed"
    assert broken["content_sha256"] is None
    assert "500" in broken["failure_reason"]

    # A bare retrieval run never synthesizes claims; Web must not invent any.
    assert evidence["claims"] == []

    # The status summary must agree with the sources the route actually returned.
    summary = body["source_status_summary"]
    returned = [source["status"] for source in evidence["sources"]]
    assert sum(summary["status_counts"].values()) == len(returned) == 3
    for status, count in summary["status_counts"].items():
        assert count == returned.count(status)

    assert body["report_kind"] == "deterministic_projection_no_synthesis"
    report = body["report"]
    assert report["research_state"] == "insufficient_evidence"
    assert "Core supplied no claims for this question." in report["missing_evidence"]
    for source in evidence["sources"]:
        if source["status"] != "retrieved":
            expected = (
                f"Source {source['source_id']} {source['status']}: {source['failure_reason']}"
            )
            assert expected in report["missing_evidence"]

    # No corpus, database or PDF artefact may appear in the working directory.
    assert list(tmp_path.iterdir()) == []


def test_online_evidence_route_fails_closed_when_fixture_server_is_gone(
    fixture_server: subprocess.Popen[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    port = _announced_port(fixture_server)
    assert fixture_server.stdin is not None
    fixture_server.stdin.close()
    fixture_server.wait(timeout=10)
    _enable_online_evidence(monkeypatch, port, tmp_path)

    response = TestClient(main.app).post("/research/online-evidence", json={"question": _QUESTION})

    # The route must never present partial or unverified evidence as a result.
    if response.status_code == 200:
        body = response.json()
        statuses = {source["status"] for source in body["evidence"]["sources"]}
        assert "retrieved" not in statuses
    else:
        assert response.status_code == 502
        assert response.json()["detail"] == (
            "Online evidence retrieval or verification failed. No report was produced."
        )
    assert list(tmp_path.iterdir()) == []
