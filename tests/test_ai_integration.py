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
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest
from knowledge_engine_ai.copilot.run_research_question import run_research_question
from knowledge_engine_ai.sessions.repository import SessionRepository, new_connection

from knowledge_engine_web.config import Settings

_EVIDENCE_REPORT_PAYLOAD = {
    "schema_version": 1,
    "question": "PLACEHOLDER",
    "sources_path": "sources.csv",
    "evidence_path": "evidence.jsonl",
    "evidence_summary": {
        "total": 1,
        "draft": 0,
        "reviewed": 1,
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
                }
            ],
        }
    ],
    "disclaimer": "This report is retrieval plus recorded evidence only.",
}


class _FakeLLM:
    def generate(self, prompt: str, *, max_tokens: int = 400) -> str:
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


def test_run_research_question_is_callable_with_web_settings(tmp_path: Path) -> None:
    sources = tmp_path / "sources.csv"
    evidence = tmp_path / "evidence.jsonl"
    sources.write_text("")
    evidence.write_text("")
    session_db = tmp_path / "research_sessions.db"

    settings = Settings(
        sources_path=str(sources),
        evidence_records_path=str(evidence),
        session_db_path=str(session_db),
        llm_model="qwen2.5:1.5b",
    )
    assert settings.sources_path is not None
    assert settings.evidence_records_path is not None

    session_repository = SessionRepository(new_connection(settings.session_db_path))
    fake_ke = _write_fake_ke_executable(tmp_path)

    result = run_research_question(
        "does semaglutide reduce body weight",
        session_repository=session_repository,
        sources=Path(settings.sources_path),
        evidence=Path(settings.evidence_records_path),
        llm=_FakeLLM(),
        ke_executable=str(fake_ke),
    )

    assert result.narrative == "Semaglutide reduced body weight [ev-1]."
    assert result.verification is not None
    assert result.verification.is_clean
    assert result.close_result.status.value == "completed"

    # The session really persisted to the configured SQLite path -- not
    # just an in-memory result -- proving `session_db_path` is wired for
    # real, not merely accepted and ignored.
    assert session_db.exists()
    reopened = SessionRepository(new_connection(str(session_db)))
    persisted = reopened.get_session(result.session_id)
    assert persisted is not None
    assert persisted.user_question_original == "does semaglutide reduce body weight"


def test_settings_new_fields_default_to_none_and_a_local_data_path() -> None:
    settings = Settings(_env_file=None)

    assert settings.sources_path is None
    assert settings.session_db_path == "data/research_sessions.db"


@pytest.mark.parametrize(
    ("env_var", "value", "attribute"),
    [
        ("KE_WEB_SOURCES_PATH", "/tmp/x/sources.csv", "sources_path"),
        ("KE_WEB_SESSION_DB_PATH", "/tmp/x/sessions.db", "session_db_path"),
    ],
)
def test_settings_new_fields_read_from_env(
    monkeypatch: pytest.MonkeyPatch, env_var: str, value: str, attribute: str
) -> None:
    monkeypatch.setenv(env_var, value)

    settings = Settings(_env_file=None)

    assert getattr(settings, attribute) == value
