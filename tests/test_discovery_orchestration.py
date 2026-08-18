from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from knowledge_engine_ai.execution import ExecutionBudget
from knowledge_engine_ai.ke_client import KeCommandError

from knowledge_engine_web import discovery_orchestration
from knowledge_engine_web.ai_guardrails import AIRequestGuard
from knowledge_engine_web.config import Settings
from knowledge_engine_web.discovery_orchestration import (
    DiscoveryOrchestrationError,
    evaluate_discovery_capability,
    run_discovery,
    run_guarded_discovery,
)


def _ready_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        ke_executable=sys.executable,
        federated_discovery_ledger_root=str(tmp_path / "ledger"),
    )


def test_discovery_capability_is_available_when_all_static_prerequisites_exist(
    tmp_path: Path,
) -> None:
    capability = evaluate_discovery_capability(_ready_settings(tmp_path))

    assert capability.available
    assert capability.reason_code is None


def test_discovery_capability_check_does_not_create_the_ledger_root(tmp_path: Path) -> None:
    settings = _ready_settings(tmp_path)
    ledger_root = Path(settings.federated_discovery_ledger_root)

    assert evaluate_discovery_capability(settings).available
    assert not ledger_root.exists()


def test_render_blueprint_declares_web_frd_1_guardrail_defaults() -> None:
    blueprint = (Path(__file__).parents[1] / "render.yaml").read_text(encoding="utf-8")

    assert "KE_WEB_DISCOVERY_REQUEST_TIMEOUT_SECONDS" in blueprint
    assert "KE_WEB_DISCOVERY_MAX_CONCURRENT_REQUESTS" in blueprint
    assert "KE_WEB_DISCOVERY_RATE_LIMIT_REQUESTS" in blueprint
    assert "KE_WEB_DISCOVERY_RATE_LIMIT_WINDOW_SECONDS" in blueprint


@pytest.mark.parametrize(
    ("override", "reason_code"),
    [
        ({"ke_executable": "missing-ke-command-for-test"}, "core_cli_unavailable"),
        (
            {"federated_discovery_ledger_root": "missing-parent/ledger"},
            "ledger_root_unavailable",
        ),
    ],
)
def test_discovery_capability_fails_closed_with_a_stable_reason(
    tmp_path: Path, override: dict[str, str], reason_code: str
) -> None:
    settings = _ready_settings(tmp_path)
    payload = settings.model_dump()
    payload.update(override)

    capability = evaluate_discovery_capability(Settings(_env_file=None, **payload))

    assert not capability.available
    assert capability.reason_code == reason_code
    assert capability.visitor_message is not None
    assert "KE_WEB_" not in capability.visitor_message


def test_run_discovery_wires_current_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _ready_settings(tmp_path)
    settings = Settings(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "federated_openalex_api_key": "openalex-key",
                "federated_semantic_scholar_api_key": "s2-key",
                "discovery_request_timeout_seconds": 42.0,
            }
        ),
    )
    expected = SimpleNamespace(search_run_id="run-123")
    captured: dict[str, object] = {}

    def fake_federated_discover(query: str, **kwargs: object) -> object:
        captured["query"] = query
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(discovery_orchestration, "federated_discover", fake_federated_discover)

    result = run_discovery(settings, "GLP-1 weight loss")

    assert result.search_run_id == "run-123"
    assert captured["query"] == "GLP-1 weight loss"
    assert captured["ledger_root"] == Path(settings.federated_discovery_ledger_root)
    assert captured["ke_executable"] == sys.executable
    assert captured["openalex_api_key"] == "openalex-key"
    assert captured["semantic_scholar_api_key"] == "s2-key"
    execution_budget = captured["execution_budget"]
    assert isinstance(execution_budget, ExecutionBudget)
    assert execution_budget.remaining_seconds() <= 42.0


def test_run_discovery_sanitizes_runtime_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _ready_settings(tmp_path)

    def fail(query: str, **kwargs: object) -> None:
        raise KeCommandError(f"private path: {tmp_path}")

    monkeypatch.setattr(discovery_orchestration, "federated_discover", fail)

    with pytest.raises(DiscoveryOrchestrationError) as raised:
        run_discovery(settings, "question")

    assert str(tmp_path) not in str(raised.value)


def test_run_discovery_rejects_an_unavailable_runtime(tmp_path: Path) -> None:
    settings = _ready_settings(tmp_path)
    settings = Settings(
        _env_file=None,
        **(settings.model_dump() | {"ke_executable": "missing-ke-command-for-test"}),
    )

    with pytest.raises(DiscoveryOrchestrationError, match="unavailable"):
        run_discovery(settings, "question")


def test_guarded_discovery_runs_within_the_admitted_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _ready_settings(tmp_path)
    expected = SimpleNamespace(search_run_id="run-123")
    captured: dict[str, object] = {}

    def fake_run(settings: Settings, query: str) -> object:
        captured["settings"] = settings
        captured["query"] = query
        return expected

    monkeypatch.setattr(discovery_orchestration, "run_discovery", fake_run)

    result = run_guarded_discovery(
        settings,
        "question",
        client_key="client-a",
        guard=AIRequestGuard(),
    )

    assert result.search_run_id == "run-123"
    assert captured == {"settings": settings, "query": "question"}
