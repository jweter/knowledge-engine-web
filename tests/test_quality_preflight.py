from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import quality_preflight


def test_fix_gates_normalize_before_validation() -> None:
    gates = quality_preflight.fix_gates("python-test")
    assert [gate.name for gate in gates] == ["format_fix", "lint_fix", "format_after_fix"]
    assert gates[0].args == ("python-test", "-m", "ruff", "format", ".")
    assert gates[1].args == ("python-test", "-m", "ruff", "check", "--fix", ".")


def test_quality_gates_match_python_ci_order() -> None:
    gates = quality_preflight.quality_gates("python-test")
    assert [gate.name for gate in gates] == [
        "format",
        "lint",
        "typing",
        "tests",
        "dependency_audit",
        "diff_hygiene",
    ]


def test_fix_mode_runs_fixes_before_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(args: tuple[str, ...], *, check: bool) -> SimpleNamespace:
        assert check is False
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(quality_preflight.subprocess, "run", fake_run)

    assert quality_preflight.main(["--fix"]) == 0
    expected = [
        *(gate.args for gate in quality_preflight.fix_gates()),
        *(gate.args for gate in quality_preflight.quality_gates()),
    ]
    assert calls == expected


def test_docker_mode_runs_after_python_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(args: tuple[str, ...], *, check: bool) -> SimpleNamespace:
        assert check is False
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(quality_preflight.subprocess, "run", fake_run)

    assert quality_preflight.main(["--docker"]) == 0
    assert calls[-1] == quality_preflight.docker_gates()[0].args
