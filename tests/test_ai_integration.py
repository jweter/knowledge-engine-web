"""AI-O13: prove `knowledge_engine_ai.copilot.run_research_question` is

importable and callable from this repo, using this project's own real
`Settings` wiring -- not just a clean import. No `/ask` route change
here (that is AI-O14); this test's only job is proving the dependency
actually works end to end from this project's own process.

CI here has no real `ke` executable or `ollama serve` (this project's
own quality gate never installs `knowledge-engine-core` or runs a local
model) -- a fake `ke` script, invoked as a real subprocess via
`ke_executable=`, stands in for it. That still exercises the real
call chain `run_research_question` makes: a real subprocess spawn, real
JSON parsing, real `SessionRepository` persistence to a real SQLite
file at `Settings().session_db_path`, and a real ISA close-gate
evaluation -- everything except the two things this project cannot
depend on being present in CI (`core` itself, a running local model).

The fixture deliberately contains three indexed EvidenceRecords, meeting the
bounded discovery policy's current adequacy threshold. This keeps this legacy
integration test focused on the baseline indexed path; dedicated GQR tests cover
the thin-coverage discovery/acquisition/grounded-completion path.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest
from knowledge_engine_ai.sessions.repository import SessionRepository, new_connection
from pydantic import ValidationError

from knowledge_engine_web import ai_orchestration
from knowledge_engine_web.ai_orchestration import run_ai_orchestration
from knowledge_engine_web.config import Settings

_EVIDENCE_REPORT_PAYLOAD = {
    "schema_version": 1,
    "question": "PLACEHOLDER",
    "sources_path": "sources.csv",
    "evidence_path": "evidence.jsonl",
    "evidence_summary": {
        "total": 3,
        "draft": 0,
        "reviewed": 3,
        "needs_revision": 0,
        "rejected": 0,
        "unspecified": 0,
        "readiness_note": "ready.",
    },
    "papers": [
        {
            "rank": 1,
            "paper_id": 1,
            "title": "A Trial of Semaglutide",
            "authors": "A. Author",
            "year": "2026",
            "journal": "A Journal",
            "doi": "10.1000/example",
            "source_url": "https://example.org",
            "license_type": "CC BY",
            "metadata_source": "sources.csv",
            "retrieval_score": -1.0,
            "retrieval_snippet": "semaglutide reduced body weight",
            "why_matched": "m",
            "citation": "A Trial of Semaglutide. (2026).",
            "evidence_records": [
                {
                    "evidence_record_id": "ev-1",
                    "claim_text": "Semaglutide reduced body weight.",
                    "evidence_direction": "supports",
                },
                {
                    "evidence_record_id": "ev-2",
                    "claim_text": "Semaglutide improved a second weight endpoint.",
                    "evidence_direction": "supports",
                },
                {
                    "evidence_record_id": "ev-3",
                    "claim_text": "Semaglutide improved a third weight endpoint.",
                    "evidence_direction": "supports",
                },
            ],
        }
    ],
    "disclaimer": "This report is retrieval plus recorded evidence only.",
}


class _FakeLLM:
    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 400,
        timeout_seconds: float | None = None,
    ) -> str:
        del timeout_seconds
        assert "does semaglutide reduce body weight" in prompt
        return "Semaglutide reduced body weight [ev-1]."


def _write_fake_ke_executable(tmp_path: Path) -> Path:
    """A real, standalone executable script -- `ke_executable=` spawns it as

    a real subprocess, the same as a real `ke` install, standing in for
    `knowledge-engine-core` (not installed in this project's CI).
    """

    script = tmp_path / "fake_ke.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"PAYLOAD = {json.dumps(_EVIDENCE_REPORT_PAYLOAD)}\n"
        "if sys.argv[1] == 'evidence-report':\n"
        "    payload = dict(PAYLOAD)\n"
        "    payload['question'] = sys.argv[2]\n"
        "    print(json.dumps(payload))\n"
        "    sys.exit(0)\n"
        "if sys.argv[1] == 'evidence-intelligence':\n"
        "    print('No graph claim found for this record.', file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "sys.exit(f'unexpected command: {sys.argv}')\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    if os.name != "nt":
        return script

    # Windows CreateProcess cannot execute a shebang-based Python file.
    # A command wrapper keeps this a real subprocess test on every platform.
    wrapper = tmp_path / "fake_ke.cmd"
    wrapper.write_text(f'@"{sys.executable}" "{script}" %*\n')
    return wrapper


def test_research_copilot_is_callable_through_the_web_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = tmp_path / "sources.csv"
    evidence = tmp_path / "evidence.jsonl"
    sources.write_text("")
    evidence.write_text("")
    session_db = tmp_path / "research_sessions.db"

    settings = Settings(
        sources_path=str(sources),
        evidence_records_path=str(evidence),
        research_papers_dir=str(tmp_path / "research-papers"),
        session_db_path=str(session_db),
        session_storage_mode="persistent",
        session_persistent_root=str(tmp_path),
        llm_model="qwen2.5:1.5b",
        ke_executable=str(_write_fake_ke_executable(tmp_path)),
    )
    assert settings.sources_path is not None
    assert settings.evidence_records_path is not None

    monkeypatch.setattr(
        ai_orchestration,
        "OllamaLLM",
        lambda *, model, host: _FakeLLM(),
    )
    result = run_ai_orchestration(settings, "does semaglutide reduce body weight")

    assert result.narrative == "Semaglutide reduced body weight [ev-1]."
    assert result.verification is not None
    assert result.verification.is_clean
    assert result.close_result.status.value == "completed"
    assert result.discovery is not None
    assert result.discovery.triggered is False
    assert result.grounded_completion is None

    # The session really persisted to the configured SQLite path -- not
    # just an in-memory result -- proving `session_db_path` is wired for
    # real, not merely accepted and ignored.
    assert session_db.exists()
    reopened = SessionRepository(new_connection(str(session_db)))
    persisted = reopened.get_session(result.session_id)
    assert persisted is not None
    assert persisted.user_question_original == "does semaglutide reduce body weight"


def test_settings_new_fields_default_to_none_and_local_data_paths() -> None:
    settings = Settings(_env_file=None)

    assert settings.sources_path is None
    assert settings.session_db_path == "data/research_sessions.db"
    assert settings.research_papers_dir == "data/research_papers"
    assert settings.session_storage_mode == "local"
    assert settings.session_persistent_root is None
    assert settings.ke_executable == "ke"
    assert settings.ai_request_timeout_seconds == 180.0
    assert settings.ai_max_concurrent_requests == 1
    assert settings.ai_rate_limit_requests == 3
    assert settings.ai_rate_limit_window_seconds == 600.0


@pytest.mark.parametrize(
    ("env_var", "value", "attribute", "expected"),
    [
        ("KE_WEB_SOURCES_PATH", "/tmp/x/sources.csv", "sources_path", "/tmp/x/sources.csv"),
        ("KE_WEB_SESSION_DB_PATH", "/tmp/x/sessions.db", "session_db_path", "/tmp/x/sessions.db"),
        (
            "KE_WEB_RESEARCH_PAPERS_DIR",
            "/tmp/x/research-papers",
            "research_papers_dir",
            "/tmp/x/research-papers",
        ),
        ("KE_WEB_SESSION_STORAGE_MODE", "persistent", "session_storage_mode", "persistent"),
        ("KE_WEB_SESSION_PERSISTENT_ROOT", "/tmp/x", "session_persistent_root", "/tmp/x"),
        ("KE_WEB_KE_EXECUTABLE", "/tmp/x/ke", "ke_executable", "/tmp/x/ke"),
        ("KE_WEB_AI_REQUEST_TIMEOUT_SECONDS", "45", "ai_request_timeout_seconds", 45.0),
        ("KE_WEB_AI_MAX_CONCURRENT_REQUESTS", "2", "ai_max_concurrent_requests", 2),
        ("KE_WEB_AI_RATE_LIMIT_REQUESTS", "4", "ai_rate_limit_requests", 4),
        ("KE_WEB_AI_RATE_LIMIT_WINDOW_SECONDS", "30", "ai_rate_limit_window_seconds", 30.0),
    ],
)
def test_settings_new_fields_read_from_env(
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
    value: str,
    attribute: str,
    expected: object,
) -> None:
    monkeypatch.setenv(env_var, value)

    settings = Settings(_env_file=None)

    assert getattr(settings, attribute) == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ai_request_timeout_seconds", 0),
        ("ai_max_concurrent_requests", 0),
        ("ai_rate_limit_requests", 0),
        ("ai_rate_limit_window_seconds", 0),
    ],
)
def test_ai_guardrail_settings_must_be_positive(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})
