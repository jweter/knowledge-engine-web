"""Characterization of today's mandatory dependencies for a one-request research report.

These tests PIN CURRENT BEHAVIOUR; they do not endorse it. See docs/web_ask_report_dependency_audit.md. A later
slice that removes a dependency (for example the mandatory local model) must change the matching test deliberately.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from knowledge_engine_web import ai_orchestration
from knowledge_engine_web.ai_orchestration import (
    AIOrchestrationError,
    evaluate_ai_capability,
    run_ai_orchestration,
)
from knowledge_engine_web.config import Settings
from knowledge_engine_web.discovery_orchestration import evaluate_discovery_capability


def _ready(tmp_path: Path, **override: object) -> Settings:
    sources = tmp_path / "sources.csv"
    evidence = tmp_path / "evidence.jsonl"
    sources.write_text("source_id,title\n", encoding="utf-8")
    evidence.write_text("", encoding="utf-8")
    payload: dict[str, object] = {
        "llm_model": "qwen2.5:1.5b",
        "sources_path": str(sources),
        "evidence_records_path": str(evidence),
        "research_papers_dir": str(tmp_path / "research-papers"),
        "session_db_path": str(tmp_path / "sessions.sqlite3"),
        "federated_discovery_ledger_root": str(tmp_path / "ledger"),
        "ke_executable": sys.executable,
    }
    payload.update(override)
    return Settings(_env_file=None, **payload)


def test_a_research_report_requires_a_configured_local_model_even_when_everything_else_is_ready(
    tmp_path: Path,
) -> None:
    capability = evaluate_ai_capability(_ready(tmp_path, llm_model=None))

    assert not capability.available and capability.reason_code == "model_not_configured"


def test_the_model_check_comes_first_so_it_hides_every_other_missing_dependency(
    tmp_path: Path,
) -> None:
    settings = _ready(
        tmp_path,
        llm_model=None,
        sources_path=None,
        evidence_records_path=None,
        ke_executable="missing-ke-command",
    )

    assert evaluate_ai_capability(settings).reason_code == "model_not_configured"


def test_without_a_model_the_orchestrator_refuses_before_any_model_client_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("a model client must not be constructed without a configured model")

    monkeypatch.setattr(ai_orchestration, "OllamaLLM", forbidden)

    with pytest.raises(AIOrchestrationError):
        run_ai_orchestration(_ready(tmp_path, llm_model=None), "What does the evidence say?")


def test_the_grounded_completion_policy_asserts_a_model(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        ai_orchestration._build_grounded_completion_policy(_ready(tmp_path, llm_model=None))


@pytest.mark.parametrize(
    ("override", "reason_code"),
    [
        ({"ke_executable": "missing-ke-command"}, "core_cli_unavailable"),
        ({"federated_discovery_ledger_root": "missing-parent/ledger"}, "ledger_root_unavailable"),
        ({"discovery_ledger_storage_mode": "persistent"}, "persistent_ledger_root_unavailable"),
    ],
)
def test_discovery_prerequisites_are_checked_statically_with_stable_reason_codes(
    tmp_path: Path, override: dict[str, object], reason_code: str
) -> None:
    capability = evaluate_discovery_capability(_ready(tmp_path, **override))

    assert not capability.available and capability.reason_code == reason_code


def test_a_discovery_problem_makes_the_whole_report_unavailable_with_the_discovery_reason(
    tmp_path: Path,
) -> None:
    capability = evaluate_ai_capability(
        _ready(tmp_path, federated_discovery_ledger_root="missing-parent/ledger")
    )

    assert not capability.available and capability.reason_code == "ledger_root_unavailable"


def test_the_ready_baseline_is_available_and_the_capability_check_creates_no_storage(
    tmp_path: Path,
) -> None:
    capability = evaluate_ai_capability(_ready(tmp_path))

    assert capability.available and capability.reason_code is None
    assert not (tmp_path / "research-papers").exists() and not (tmp_path / "ledger").exists()
    assert not (tmp_path / "sessions.sqlite3").exists()
