"""Run Knowledge Engine Web's deterministic local quality gates in CI order.

Invoke from the repository root with:

    poetry run python scripts/quality_preflight.py

The script intentionally stops at the first failing gate so the first actionable
failure stays visible. GitHub Actions (`.github/workflows/quality.yml`'s
`checks` job) remains the authoritative merge gate; this script only mirrors
its deterministic, Poetry-managed steps so a connector/agent-authored change
can be validated locally before a PR is opened or updated. It deliberately
does not attempt the `docker` job (image build + container smoke test) --
that job is not Poetry-managed and CI itself is the right place to run it.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class QualityGate:
    """One deterministic repository quality gate."""

    name: str
    args: tuple[str, ...]


def quality_gates(python_executable: str = sys.executable) -> tuple[QualityGate, ...]:
    """Return the canonical local gate sequence, in the same order as CI's
    `checks` job."""
    return (
        QualityGate(
            "format",
            (python_executable, "-m", "ruff", "format", "--check", "."),
        ),
        QualityGate(
            "lint",
            (python_executable, "-m", "ruff", "check", "."),
        ),
        QualityGate(
            "typing",
            (python_executable, "-m", "mypy", "knowledge_engine_web", "tests"),
        ),
        QualityGate(
            "tests",
            (python_executable, "-m", "pytest"),
        ),
        QualityGate(
            "dependency_audit",
            (python_executable, "-m", "pip_audit"),
        ),
        QualityGate(
            "diff_hygiene",
            ("git", "diff", "--check"),
        ),
    )


def run_preflight(gates: Sequence[QualityGate] | None = None) -> int:
    """Run gates in order, stopping at the first non-zero return code."""
    selected = tuple(gates) if gates is not None else quality_gates()
    for gate in selected:
        print(f"\n=== quality preflight: {gate.name} ===", flush=True)
        completed = subprocess.run(gate.args, check=False)  # noqa: S603
        if completed.returncode != 0:
            print(
                f"Quality preflight stopped: {gate.name} failed "
                f"with exit code {completed.returncode}.",
                file=sys.stderr,
            )
            return completed.returncode
    print("\nQuality preflight passed.")
    return 0


def main() -> None:
    """CLI entrypoint."""
    raise SystemExit(run_preflight())


if __name__ == "__main__":
    main()
