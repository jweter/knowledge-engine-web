"""Opt-in live Product Reality acceptance for the online evidence preview.

Drives the real Web endpoint -> AI client -> Core ``ke online-research`` path
against real providers. Skipped unless ``KE_WEB_LIVE_ONLINE_ACCEPTANCE=1`` so
normal CI stays offline and deterministic. It asserts integrity and cleanup
(source statuses valid, every citation resolves, no temporary directory
survives, retrieval-only labelling), NOT that providers return usable
evidence: a run with zero retrieved sources is a valid, honest outcome.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_engine_web import main

pytestmark = pytest.mark.skipif(
    os.environ.get("KE_WEB_LIVE_ONLINE_ACCEPTANCE") != "1" or shutil.which("ke") is None,
    reason="set KE_WEB_LIVE_ONLINE_ACCEPTANCE=1 with the Core `ke` CLI installed",
)

_VALID_STATUSES = {"retrieved", "unavailable", "not_permitted", "failed"}


def _leftovers() -> set[Path]:
    return set(Path(tempfile.gettempdir()).glob("ke-online-research-*"))


def test_live_one_question_run_is_labelled_consistent_and_leaves_no_temp_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KE_WEB_ONLINE_EVIDENCE_ENABLED", "true")
    before = _leftovers()
    response = TestClient(main.app).post(
        "/research/online-evidence",
        json={"question": "What is the boiling point of water at sea level?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "content_checked_retrieval_only"
    assert body["research_report_complete"] is False
    sources = body["evidence"]["sources"]
    assert all(s["status"] in _VALID_STATUSES for s in sources)
    assert body["source_status_summary"]["source_count"] == len(sources)
    assert all(s["failure_reason"] for s in sources if s["status"] != "retrieved")

    excerpts = {x["excerpt_id"]: x for x in body["evidence"]["excerpts"]}
    source_ids = {s["source_id"] for s in sources}
    for claim in body["evidence"]["claims"]:
        assert claim["citations"], "a claim without a citation must not be returned"
        for citation in claim["citations"]:
            assert excerpts[citation["excerpt_id"]]["source_id"] in source_ids

    assert _leftovers() == before
