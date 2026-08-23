"""Run Knowledge Engine Web's local quality gates with optional safe autofix."""

from __future__ import annotations

import argparse
import subprocess as subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class QualityGate:
    """One deterministic repository quality gate."""

    name: str
    args: tuple[str, ...]


def fix_gates(python_executable: str = sys.executable) -> tuple[QualityGate, ...]:
    """Return safe normalization gates used before check-only validation."""
    return (
        QualityGate("format_fix", (python_executable, "-m", "ruff", "format", ".")),
        QualityGate("lint_fix", (python_executable, "-m", "ruff", "check", "--fix", ".")),
        QualityGate("format_after_fix", (python_executable, "-m", "ruff", "format", ".")),
    )


def quality_gates(python_executable: str = sys.executable) -> tuple[QualityGate, ...]:
    """Return the canonical Poetry-managed CI gate sequence."""
    return (
        QualityGate("format", (python_executable, "-m", "ruff", "format", "--check", ".")),
        QualityGate("lint", (python_executable, "-m", "ruff", "check", ".")),
        QualityGate(
            "typing",
            (python_executable, "-m", "mypy", "knowledge_engine_web", "tests"),
        ),
        QualityGate("tests", (python_executable, "-m", "pytest")),
        QualityGate("dependency_audit", (python_executable, "-m", "pip_audit")),
        QualityGate("diff_hygiene", ("git", "diff", "--check")),
    )


def docker_gates() -> tuple[QualityGate, ...]:
    """Return the repository-specific container build gate."""
    return (
        QualityGate(
            "docker_build",
            ("docker", "build", "-t", "knowledge-engine-web-alpha:preflight", "."),
        ),
    )


def run_preflight(gates: Sequence[QualityGate]) -> int:
    """Run gates in order, stopping at the first non-zero return code."""
    for gate in gates:
        print(f"\n=== quality preflight: {gate.name} ===", flush=True)
        completed = subprocess.run(gate.args, check=False)  # noqa: S603
        if completed.returncode != 0:
            print(
                f"Quality preflight stopped: {gate.name} failed "
                f"with exit code {completed.returncode}.",
                file=sys.stderr,
            )
            return completed.returncode
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run optional safe fixes, CI-parity checks, and optionally a Docker build."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="Apply safe Ruff fixes first.")
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Also build the production Docker image after Python gates pass.",
    )
    args = parser.parse_args(argv)

    if args.fix:
        returncode = run_preflight(fix_gates())
        if returncode != 0:
            return returncode

    returncode = run_preflight(quality_gates())
    if returncode != 0:
        return returncode
    if args.docker:
        return run_preflight(docker_gates())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
