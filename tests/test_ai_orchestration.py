from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from knowledge_engine_web import ai_orchestration
from knowledge_engine_web.ai_orchestration import (
    AIOrchestrationError,
    evaluate_ai_capability,
    run_ai_orchestration,
)
from knowledge_engine_web.config import Settings


def _ready_settings(tmp_path: Path) -> Settings:
    sources = tmp_path / "sources.csv"
    evidence = tmp_path / "evidence.jsonl"
    sources.write_text("source_id,title\n", encoding="utf-8")
    evidence.write_text("", encoding="utf-8")
    return Settings(
        _env_file=None,
        llm_model="qwen2.5:1.5b",
        sources_path=str(sources),
        evidence_records_path=str(evidence),
        session_db_path=str(tmp_path / "sessions.sqlite3"),
        ke_executable=sys.executable,
    )


def test_ai_capability_is_available_when_all_static_prerequisites_exist(
    tmp_path: Path,
) -> None:
    capability = evaluate_ai_capability(_ready_settings(tmp_path))

    assert capability.available
    assert capability.reason_code is None


@pytest.mark.parametrize(
    ("override", "reason_code"),
    [
        ({"llm_model": " "}, "model_not_configured"),
        ({"sources_path": None}, "sources_unavailable"),
        ({"evidence_records_path": None}, "evidence_unavailable"),
        ({"ke_executable": "missing-ke-command-for-test"}, "core_cli_unavailable"),
        ({"session_db_path": "missing-parent/sessions.sqlite3"}, "session_store_unavailable"),
    ],
)
def test_ai_capability_fails_closed_with_a_stable_reason(
    tmp_path: Path, override: dict[str, str | None], reason_code: str
) -> None:
    settings = _ready_settings(tmp_path)
    payload = settings.model_dump()
    payload.update(override)

    capability = evaluate_ai_capability(Settings(_env_file=None, **payload))

    assert not capability.available
    assert capability.reason_code == reason_code
    assert capability.visitor_message is not None
    assert "KE_WEB_" not in capability.visitor_message


def test_capability_check_does_not_create_the_session_database(tmp_path: Path) -> None:
    settings = _ready_settings(tmp_path)
    session_db = Path(settings.session_db_path)

    assert evaluate_ai_capability(settings).available
    assert not session_db.exists()


def test_run_ai_orchestration_wires_current_settings_and_closes_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _ready_settings(tmp_path)
    expected = SimpleNamespace(session_id="session-123")
    captured: dict[str, object] = {}

    class FakeLLM:
        def __init__(self, *, model: str, host: str) -> None:
            captured["model"] = model
            captured["host"] = host

    def fake_run(question: str, **kwargs: object) -> object:
        captured["question"] = question
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(ai_orchestration, "OllamaLLM", FakeLLM)
    monkeypatch.setattr(ai_orchestration, "run_research_question", fake_run)

    result = run_ai_orchestration(settings, "does semaglutide reduce body weight")

    assert result.session_id == expected.session_id
    assert captured["question"] == "does semaglutide reduce body weight"
    assert captured["sources"] == Path(settings.sources_path or "")
    assert captured["evidence"] == Path(settings.evidence_records_path or "")
    assert captured["ke_executable"] == sys.executable
    assert captured["model"] == "qwen2.5:1.5b"


def test_run_ai_orchestration_sanitizes_runtime_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _ready_settings(tmp_path)

    def fail(question: str, **kwargs: object) -> None:
        raise OSError(f"private path: {tmp_path}")

    monkeypatch.setattr(ai_orchestration, "run_research_question", fail)

    with pytest.raises(AIOrchestrationError) as raised:
        run_ai_orchestration(settings, "question")

    assert str(tmp_path) not in str(raised.value)
    assert "Deterministic retrieval results" in str(raised.value)


def test_run_ai_orchestration_rejects_an_unavailable_runtime(tmp_path: Path) -> None:
    settings = _ready_settings(tmp_path)
    settings = Settings(_env_file=None, **(settings.model_dump() | {"llm_model": None}))

    with pytest.raises(AIOrchestrationError, match="unavailable"):
        run_ai_orchestration(settings, "question")
