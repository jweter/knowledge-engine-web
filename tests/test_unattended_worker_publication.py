from __future__ import annotations

import subprocess
from pathlib import Path

from knowledge_engine_web.unattended_verification_contract import WorkerResult
from knowledge_engine_web.unattended_worker_publication import publish_sanitized_result


def _result() -> WorkerResult:
    return WorkerResult(
        request_id="private-request-id",
        repository="jweter/knowledge-engine-web",
        exact_sha="a" * 40,
        environment_id="jeremy-private-windows-machine",
        status="FAIL",
        completed_at_utc="2026-09-16T12:00:00+00:00",
        summary=(
            "preflight: Canonical preflight failed after 5.300s. Last output: "
            "ruff check failed in knowledge_engine_web/example.py:42"
        ),
        failure_class="TEST_FAILURE",
    )


def test_publication_is_noop_off_windows(tmp_path: Path) -> None:
    assert (
        publish_sanitized_result(_result(), tmp_path, os_name="posix") == "LOCAL_ONLY_NON_WINDOWS"
    )
    assert not (tmp_path / "github-publication.json").exists()


def test_publication_exposes_failure_summary_without_machine_identity(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    status = publish_sanitized_result(
        _result(),
        tmp_path,
        os_name="nt",
        which=lambda _name: "gh.exe",
        runner=runner,
    )

    assert status == "PUBLISHED"
    assert len(calls) == 2
    body = calls[1][calls[1].index("--body") + 1]
    assert "Canonical preflight failed after 5.300s" in body
    assert "TEST_FAILURE" in body
    assert "aaaaaaaaaaaa" in body
    assert "private-request-id" not in body
    assert "jeremy-private-windows-machine" not in body
    assert calls[1][calls[1].index("--repo") + 1] == "jweter/knowledge-engine-web"
    assert "160" in calls[1]


def test_publication_deduplicates_exact_same_result(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    first = publish_sanitized_result(
        _result(),
        tmp_path,
        os_name="nt",
        which=lambda _name: "gh.exe",
        runner=runner,
    )
    calls.clear()
    second = publish_sanitized_result(
        _result(),
        tmp_path,
        os_name="nt",
        which=lambda _name: "gh.exe",
        runner=runner,
    )

    assert first == "PUBLISHED"
    assert second == "UNCHANGED"
    assert calls == []


def test_publication_failure_does_not_change_worker_result(tmp_path: Path) -> None:
    result = _result()

    def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[1:3] == ["auth", "status"]:
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="offline")

    status = publish_sanitized_result(
        result,
        tmp_path,
        os_name="nt",
        which=lambda _name: "gh.exe",
        runner=runner,
    )

    assert status == "LOCAL_ONLY"
    assert result.status == "FAIL"
    assert result.failure_class == "TEST_FAILURE"
