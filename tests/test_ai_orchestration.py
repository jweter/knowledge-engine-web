from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from knowledge_engine_ai.copilot.discovery_policy import FederatedDiscoveryPolicy
from knowledge_engine_ai.copilot.grounded_completion import GroundedCompletionPolicy
from knowledge_engine_ai.copilot.research_state import ResearchState, ResearchStateResult

from knowledge_engine_web import ai_orchestration
from knowledge_engine_web.ai_guardrails import AIRequestGuard
from knowledge_engine_web.ai_orchestration import (
    AIOrchestrationError,
    evaluate_ai_capability,
    result_reached_execution_limit,
    run_ai_orchestration,
    run_guarded_ai_orchestration,
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
        research_papers_dir=str(tmp_path / "research-papers"),
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
        ({"research_papers_dir": "missing-parent/research-papers"}, "research_papers_unavailable"),
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


def test_ai_capability_requires_writable_evidence_for_grounded_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _ready_settings(tmp_path)
    monkeypatch.setattr(ai_orchestration, "_configured_writable_file", lambda value: None)

    capability = evaluate_ai_capability(settings)

    assert not capability.available
    assert capability.reason_code == "evidence_unavailable"


def test_core_cli_preflight_checks_complete_research_command_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[str] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        assert kwargs["check"] is False
        assert kwargs["timeout"] == ai_orchestration._CORE_COMMAND_HELP_TIMEOUT_SECONDS
        assert argv[0] == "/fake/ke"
        assert argv[2] == "--help"
        commands.append(argv[1])
        return SimpleNamespace(returncode=0)

    ai_orchestration._core_cli_has_required_commands.cache_clear()
    monkeypatch.setattr(ai_orchestration.subprocess, "run", fake_run)

    assert ai_orchestration._core_cli_has_required_commands("/fake/ke")
    assert tuple(commands) == ai_orchestration._RESEARCH_CORE_COMMANDS


def test_hosted_core_cli_preflight_fails_closed_when_command_surface_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _ready_settings(tmp_path)
    settings = Settings(
        _env_file=None,
        **(settings.model_dump() | {"core_cli_command_preflight": True}),
    )
    monkeypatch.setattr(ai_orchestration, "_core_cli_has_required_commands", lambda value: False)

    capability = evaluate_ai_capability(settings)

    assert not capability.available
    assert capability.reason_code == "core_cli_incomplete"


def test_capability_check_does_not_create_runtime_storage(tmp_path: Path) -> None:
    settings = _ready_settings(tmp_path)
    session_db = Path(settings.session_db_path)
    papers_dir = Path(settings.research_papers_dir)

    assert evaluate_ai_capability(settings).available
    assert not session_db.exists()
    assert not papers_dir.exists()


def test_persistent_session_storage_accepts_a_database_inside_the_mount(
    tmp_path: Path,
) -> None:
    persistent_root = tmp_path / "persistent"
    persistent_root.mkdir()
    settings = _ready_settings(tmp_path)
    settings = Settings(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "session_db_path": str(persistent_root / "research_sessions.sqlite3"),
                "session_storage_mode": "persistent",
                "session_persistent_root": str(persistent_root),
            }
        ),
    )

    capability = evaluate_ai_capability(settings)

    assert capability.available
    assert capability.session_storage_mode == "persistent"


@pytest.mark.parametrize("root_value", [None, " "])
def test_persistent_session_storage_requires_a_configured_root(
    tmp_path: Path, root_value: str | None
) -> None:
    settings = _ready_settings(tmp_path)
    settings = Settings(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "session_storage_mode": "persistent",
                "session_persistent_root": root_value,
            }
        ),
    )

    capability = evaluate_ai_capability(settings)

    assert not capability.available
    assert capability.reason_code == "persistent_session_root_unavailable"


def test_persistent_session_storage_rejects_a_database_outside_the_mount(
    tmp_path: Path,
) -> None:
    persistent_root = tmp_path / "persistent"
    persistent_root.mkdir()
    settings = _ready_settings(tmp_path)
    settings = Settings(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "session_storage_mode": "persistent",
                "session_persistent_root": str(persistent_root),
            }
        ),
    )

    capability = evaluate_ai_capability(settings)

    assert not capability.available
    assert capability.reason_code == "persistent_session_path_invalid"


@pytest.mark.parametrize(
    ("database_path", "persistent_root"),
    [
        ("relative/sessions.sqlite3", "relative"),
        ("relative/sessions.sqlite3", None),
    ],
)
def test_persistent_session_storage_rejects_relative_paths(
    tmp_path: Path, database_path: str, persistent_root: str | None
) -> None:
    root_value = persistent_root or str(tmp_path)
    settings = _ready_settings(tmp_path)
    settings = Settings(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "session_db_path": database_path,
                "session_storage_mode": "persistent",
                "session_persistent_root": root_value,
            }
        ),
    )

    capability = evaluate_ai_capability(settings)

    assert not capability.available
    assert capability.reason_code == "persistent_session_path_invalid"


def test_persistent_session_storage_rejects_a_symlink_escape(tmp_path: Path) -> None:
    persistent_root = tmp_path / "persistent"
    outside = tmp_path / "outside"
    persistent_root.mkdir()
    outside.mkdir()
    link = persistent_root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"This environment cannot create directory symlinks: {exc}")

    settings = _ready_settings(tmp_path)
    settings = Settings(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "session_db_path": str(link / "research_sessions.sqlite3"),
                "session_storage_mode": "persistent",
                "session_persistent_root": str(persistent_root),
            }
        ),
    )

    capability = evaluate_ai_capability(settings)

    assert not capability.available
    assert capability.reason_code == "persistent_session_path_invalid"


def test_render_blueprint_requires_persistent_research_storage() -> None:
    blueprint = (Path(__file__).parents[1] / "render.yaml").read_text(encoding="utf-8")

    assert "KE_WEB_SESSION_STORAGE_MODE" in blueprint
    assert "value: persistent" in blueprint
    assert "KE_WEB_SESSION_PERSISTENT_ROOT" in blueprint
    assert "value: /var/data" in blueprint
    assert "KE_WEB_RESEARCH_PAPERS_DIR" in blueprint
    assert "value: /var/data/research_papers" in blueprint
    assert "KE_WEB_CORE_CLI_COMMAND_PREFLIGHT" in blueprint


def test_render_blueprint_declares_ai_o16_guardrail_defaults() -> None:
    blueprint = (Path(__file__).parents[1] / "render.yaml").read_text(encoding="utf-8")

    assert "KE_WEB_AI_REQUEST_TIMEOUT_SECONDS" in blueprint
    assert "KE_WEB_AI_MAX_CONCURRENT_REQUESTS" in blueprint
    assert "KE_WEB_AI_RATE_LIMIT_REQUESTS" in blueprint
    assert "KE_WEB_AI_RATE_LIMIT_WINDOW_SECONDS" in blueprint


def test_run_ai_orchestration_wires_complete_grounded_research_path(
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

    discovery_policy = cast(FederatedDiscoveryPolicy, captured["discovery_policy"])
    assert discovery_policy.enable_acquisition_plan is True

    completion_policy = cast(GroundedCompletionPolicy, captured["grounded_completion_policy"])
    assert completion_policy.ledger_root == Path(settings.federated_discovery_ledger_root)
    assert completion_policy.papers_dir == Path(settings.research_papers_dir)
    assert completion_policy.grounding_model == "qwen2.5:1.5b"
    assert completion_policy.ledger_root == discovery_policy.ledger_root


def test_guarded_orchestration_passes_deadline_and_attaches_ai_owned_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _ready_settings(tmp_path)
    settings = Settings(
        _env_file=None,
        **(settings.model_dump() | {"ai_request_timeout_seconds": 42.0}),
    )
    captured: dict[str, object] = {}
    expected = SimpleNamespace(session_id="session-123", narrative="arbitrary prose")
    expected_state = ResearchStateResult(
        schema_version=2,
        state=ResearchState.RESEARCH_REQUIRED,
        reason="indexed_coverage_insufficient_bounded_research_started",
        indexed_evidence_record_count=1,
        discovery_triggered=True,
        federated_discovery_attempted=True,
        acquisition_plan_attempted=True,
        grounded_completion_attempted=False,
        grounded_completion_completed=False,
        used_reretrieved_evidence=False,
        promoted_evidence_record_count=0,
        provider_degraded=False,
    )

    def fake_run(
        settings: Settings,
        question: str,
        *,
        timeout_seconds: float | None = None,
    ) -> object:
        captured["question"] = question
        captured["timeout_seconds"] = timeout_seconds
        return expected

    def fake_derive(result: object) -> ResearchStateResult:
        assert result is expected
        return expected_state

    monkeypatch.setattr(ai_orchestration, "run_ai_orchestration", fake_run)
    monkeypatch.setattr(ai_orchestration, "derive_research_state", fake_derive)

    result = run_guarded_ai_orchestration(
        settings,
        "question",
        client_key="client-a",
        guard=AIRequestGuard(),
    )

    assert result.session_id == "session-123"
    assert result.research_state is expected_state
    assert result.research_state.state is ResearchState.RESEARCH_REQUIRED
    assert captured == {"question": "question", "timeout_seconds": 42.0}


def test_result_detects_a_durable_workflow_timeout() -> None:
    timed_out = SimpleNamespace(
        workflow=SimpleNamespace(
            steps=(
                SimpleNamespace(
                    error="`ke evidence-report` exceeded the configured execution time limit."
                ),
            )
        ),
        synthesis_error=None,
    )
    complete = SimpleNamespace(
        workflow=SimpleNamespace(steps=(SimpleNamespace(error=None),)),
        synthesis_error=None,
    )
    model_timed_out = SimpleNamespace(
        workflow=SimpleNamespace(steps=(SimpleNamespace(error=None),)),
        synthesis_error="Ollama at a private endpoint did not respond within 42s.",
    )

    assert result_reached_execution_limit(timed_out)
    assert result_reached_execution_limit(model_timed_out)
    assert not result_reached_execution_limit(complete)


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
