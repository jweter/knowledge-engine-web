from __future__ import annotations

import json
import os
import signal
import subprocess
import urllib.request
from pathlib import Path

import pytest

from knowledge_engine_web import unattended_worker as worker
from knowledge_engine_web.unattended_verification_contract import WorkerRequest, WorkerResult


def request(**overrides: object) -> WorkerRequest:
    payload: dict[str, object] = {
        "request_id": "req-1",
        "repository": worker.REPOSITORY,
        "branch": "main",
        "exact_sha": "a" * 40,
        "requested_checks": ("preflight",),
        "environment_id": "jeremy-laptop",
        "created_at_utc": "2026-09-13T23:30:00Z",
    }
    payload.update(overrides)
    return WorkerRequest.model_validate(payload)


def test_runtime_consumes_authoritative_worker_request_contract(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    expected = request(requested_checks=("preflight", "ollama_health"))
    path.write_text(expected.model_dump_json(), encoding="utf-8")

    loaded = worker.load_request(path)

    assert isinstance(loaded, WorkerRequest)
    assert loaded == expected


def test_normalize_origin_accepts_https_and_ssh() -> None:
    assert worker.origin_is_expected("https://github.com/jweter/knowledge-engine-web.git")
    assert worker.origin_is_expected("https://github.com/jweter/knowledge-engine-web")
    assert worker.origin_is_expected("git@github.com:jweter/knowledge-engine-web.git")
    assert not worker.origin_is_expected("https://github.com/example/other.git")


def test_sanitize_text_removes_paths_and_secret_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/example")))
    text = f"{tmp_path}/file token=secret password:abc /home/example/data"
    sanitized = worker.sanitize_text(text, repo_root=tmp_path)
    assert str(tmp_path) not in sanitized
    assert "secret" not in sanitized
    assert "password:abc" not in sanitized
    assert "/home/example" not in sanitized
    assert "<REPO_ROOT>" in sanitized
    assert "<REDACTED>" in sanitized


def test_sanitize_text_removes_json_and_dict_style_secrets(tmp_path: Path) -> None:
    text = (
        '{"api_key": "example-not-a-real-secret-000111"}'
        " headers={'Authorization': 'Bearer example-not-a-real-secret-000111'}"
    )
    sanitized = worker.sanitize_text(text, repo_root=tmp_path)
    assert "example-not-a-real-secret-000111" not in sanitized
    assert "Bearer" not in sanitized
    assert "<REDACTED>" in sanitized


def test_sanitize_text_removes_underscore_prefixed_secret_env_vars(tmp_path: Path) -> None:
    text = "GITHUB_TOKEN=example-not-a-real-token-000111222"
    sanitized = worker.sanitize_text(text, repo_root=tmp_path)
    assert "example-not-a-real-token-000111222" not in sanitized
    assert "<REDACTED>" in sanitized


def test_sanitize_text_removes_url_embedded_credentials(tmp_path: Path) -> None:
    # A non-standard scheme keeps this fixture from resembling a real HTTPS
    # credential URL while still exercising the generic "://user:pass@" match.
    text = "example-remote://user:example-not-a-real-token-000111222@example.invalid/org/repo.git"
    sanitized = worker.sanitize_text(text, repo_root=tmp_path)
    assert "example-not-a-real-token-000111222" not in sanitized
    assert "<REDACTED>" in sanitized


def test_sanitize_text_removes_unquoted_bearer_token(tmp_path: Path) -> None:
    # Raw HTTP header traces (curl -v, requests/urllib debug logs, git's
    # GIT_CURL_VERBOSE output) render "Authorization: Bearer <token>" unquoted.
    # The unquoted fallback previously only consumed the "Bearer" scheme word,
    # leaving the actual credential exposed in the sanitized text.
    text = 'curl -H "Authorization: Bearer example-not-a-real-secret-000111"'
    sanitized = worker.sanitize_text(text, repo_root=tmp_path)
    assert "example-not-a-real-secret-000111" not in sanitized
    assert "Bearer" not in sanitized
    assert "<REDACTED>" in sanitized


@pytest.mark.parametrize(
    "auth_header",
    [
        # Basic auth: base64(user:pass) is the actual credential.
        "Authorization: Basic dXNlcjpzdXBlcnNlY3JldHBhc3N3b3Jk",
        # Digest auth: the response hash is proof of password knowledge.
        'Authorization: Digest username="x", response="deadbeefcafefeed"',
        # AWS SigV4: multi-token scheme, credential/signature after the scheme word.
        "Authorization: AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/"
        "20260921/us-east-1/s3/aws4_request, SignedHeaders=host, "
        "Signature=abcdef0123456789",
        # NTLM: base64 security-blob credential.
        "Authorization: NTLM TlRMTVNTUAABAAAAB4IIogAAAAAAAAAAAAAAAAAAAAAGAbEdAAAADw==",
    ],
)
def test_sanitize_text_removes_unquoted_non_bearer_scheme_credentials(
    tmp_path: Path, auth_header: str
) -> None:
    # PR #184 fixed the leak for the "Bearer" scheme specifically, but the same
    # unquoted "Authorization: <scheme> <credential>" shape leaks the credential
    # for every other scheme word too -- the fallback must not special-case one
    # scheme name.
    text = f'curl -H "{auth_header}"'
    sanitized = worker.sanitize_text(text, repo_root=tmp_path)
    assert "REDACTED" in sanitized
    for leaked in (
        "dXNlcjpzdXBlcnNlY3JldHBhc3N3b3Jk",
        "deadbeefcafefeed",
        "AKIAIOSFODNN7EXAMPLE",
        "abcdef0123456789",
        "TlRMTVNTUAABAAAAB4IIogAAAAAAAAAAAAAAAAAAAAAGAbEdAAAADw==",
    ):
        assert leaked not in sanitized


def test_sanitize_text_leaves_unrelated_key_value_text_alone(tmp_path: Path) -> None:
    text = "primary_key: 42 tokenizer_output=fine"
    sanitized = worker.sanitize_text(text, repo_root=tmp_path)
    assert sanitized == text


def test_acquire_lock_reclaims_stale_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / worker.LOCK_NAME
    lock.write_text("99999999", encoding="ascii")
    monkeypatch.setattr(worker, "pid_is_alive", lambda pid: False)
    fd, acquired = worker.acquire_lock(tmp_path)
    assert acquired is True
    assert fd is not None
    try:
        assert int(lock.read_text(encoding="ascii")) == os.getpid()
    finally:
        worker.release_lock(tmp_path, fd)
    assert not lock.exists()


def test_acquire_lock_reclaims_malformed_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / worker.LOCK_NAME
    lock.write_text("", encoding="ascii")
    monkeypatch.setattr("knowledge_engine_web.unattended_worker.time.sleep", lambda _: None)
    fd, acquired = worker.acquire_lock(tmp_path)
    assert acquired is True
    assert fd is not None
    try:
        assert int(lock.read_text(encoding="ascii")) == os.getpid()
    finally:
        worker.release_lock(tmp_path, fd)


def test_acquire_lock_defers_when_owner_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / worker.LOCK_NAME
    lock.write_text("1234", encoding="ascii")
    monkeypatch.setattr(worker, "pid_is_alive", lambda pid: True)
    fd, acquired = worker.acquire_lock(tmp_path)
    assert acquired is False
    assert fd is None


def test_validate_checkout_fails_closed_on_wrong_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    values = iter(
        [
            "https://github.com/jweter/knowledge-engine-web.git",
            "main",
            "b" * 40,
        ]
    )
    monkeypatch.setattr(worker, "git_output", lambda *args, **kwargs: next(values))

    with pytest.raises(RuntimeError, match="Checkout identity mismatch"):
        worker.validate_checkout(tmp_path, request(), environment_id="jeremy-laptop")


def test_validate_checkout_fails_closed_on_wrong_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    values = iter(
        [
            "https://github.com/jweter/knowledge-engine-web.git",
            "feature/other",
        ]
    )
    monkeypatch.setattr(worker, "git_output", lambda *args, **kwargs: next(values))

    with pytest.raises(RuntimeError, match="Checkout branch mismatch"):
        worker.validate_checkout(tmp_path, request(), environment_id="jeremy-laptop")


def test_validate_checkout_fails_closed_on_dirty_tracked_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    values = iter(
        [
            "https://github.com/jweter/knowledge-engine-web.git",
            "main",
            "a" * 40,
            " M engineering/preflight.py",
        ]
    )
    monkeypatch.setattr(worker, "git_output", lambda *args, **kwargs: next(values))

    with pytest.raises(RuntimeError, match="modified tracked files"):
        worker.validate_checkout(tmp_path, request(), environment_id="jeremy-laptop")


def test_validate_checkout_fails_closed_on_untracked_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    values = iter(
        [
            "https://github.com/jweter/knowledge-engine-web.git",
            "main",
            "a" * 40,
            "",
            "unexpected.py",
        ]
    )
    monkeypatch.setattr(worker, "git_output", lambda *args, **kwargs: next(values))

    with pytest.raises(RuntimeError, match="untracked files"):
        worker.validate_checkout(tmp_path, request(), environment_id="jeremy-laptop")


def test_validate_checkout_fails_closed_on_wrong_environment(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="worker environment mismatch"):
        worker.validate_checkout(tmp_path, request(), environment_id="different-laptop")


def test_validate_checkout_fails_closed_on_wrong_repository(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="request repository must be"):
        worker.validate_checkout(
            tmp_path,
            request(repository="jweter/knowledge-engine-core"),
            environment_id="jeremy-laptop",
        )


def test_posix_group_termination_resolves_capabilities_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, object]] = []
    monkeypatch.setattr(
        os,
        "killpg",
        lambda pid, sig: calls.append((pid, sig)),
        raising=False,
    )
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)

    worker._terminate_posix_process_group(1234)

    assert calls == [(1234, 9)]


def test_posix_group_termination_fails_closed_when_capability_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(os, "killpg", raising=False)
    monkeypatch.delattr(signal, "SIGKILL", raising=False)

    with pytest.raises(RuntimeError, match="process-group termination is unavailable"):
        worker._terminate_posix_process_group(1234)


def test_run_logged_terminates_process_tree_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        pid = 1234
        returncode: int | None = None

        def wait(self, timeout: float | None = None) -> int:
            if self.returncode is None:
                raise subprocess.TimeoutExpired(cmd="preflight", timeout=timeout or 0)
            return self.returncode

        def poll(self) -> int | None:
            return self.returncode

        def kill(self) -> None:
            self.returncode = -9

    fake = FakeProcess()
    terminated: list[int] = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake)

    def terminate(proc: object) -> None:
        terminated.append(proc.pid)  # type: ignore[attr-defined]
        fake.returncode = 124

    monkeypatch.setattr(worker, "_terminate_process_tree", terminate)

    code, _duration, timed_out = worker.run_logged(
        ["python", "engineering/preflight.py"],
        cwd=tmp_path,
        log_path=tmp_path / "preflight.log",
        timeout_seconds=0.01,
    )

    assert timed_out is True
    assert code == 124
    assert terminated == [1234]


def test_run_preflight_missing_script_is_review_required(tmp_path: Path) -> None:
    status, summary, failure_class = worker.run_preflight(tmp_path, tmp_path / "state", 30)
    assert status == "REVIEW_REQUIRED"
    assert failure_class == "POLICY_FAILURE"
    assert "engineering/preflight.py is missing" in summary


def _write_junit_report(
    path: Path, *, tests: int, failures: int = 0, errors: int = 0, skipped: int = 0
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<testsuites><testsuite tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}"></testsuite></testsuites>',
        encoding="utf-8",
    )


def test_parse_junit_counts_reads_testsuite_totals(tmp_path: Path) -> None:
    path = tmp_path / "report.xml"
    _write_junit_report(path, tests=6, failures=1, errors=0, skipped=2)
    assert worker._parse_junit_counts(path) == (6, 1, 0, 2)


def test_parse_junit_counts_missing_file_returns_none(tmp_path: Path) -> None:
    assert worker._parse_junit_counts(tmp_path / "missing.xml") is None


def test_parse_junit_counts_malformed_xml_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "report.xml"
    path.write_text("not xml", encoding="utf-8")
    assert worker._parse_junit_counts(path) is None


def test_run_browser_ask_all_skipped_is_environment_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    _write_junit_report(state_dir / "browser-ask-junit.xml", tests=6, skipped=6)
    monkeypatch.setattr(worker, "run_logged", lambda *args, **kwargs: (0, 1.0, False))

    status, summary, failure_class = worker.run_browser_ask(tmp_path, state_dir, 30)

    assert status == "ENVIRONMENT_FAILURE"
    assert failure_class == "ENVIRONMENT_FAILURE"
    assert "no usable Chromium" in summary


def test_run_browser_ask_missing_report_is_environment_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "run_logged", lambda *args, **kwargs: (0, 1.0, False))

    status, summary, failure_class = worker.run_browser_ask(tmp_path, tmp_path / "state", 30)

    assert status == "ENVIRONMENT_FAILURE"
    assert failure_class == "ENVIRONMENT_FAILURE"
    assert "no readable JUnit report" in summary


def test_run_browser_ask_timeout_is_environment_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "run_logged", lambda *args, **kwargs: (124, 30.0, True))

    status, summary, failure_class = worker.run_browser_ask(tmp_path, tmp_path / "state", 30)

    assert status == "ENVIRONMENT_FAILURE"
    assert failure_class == "ENVIRONMENT_FAILURE"
    assert "timed out" in summary


def test_run_browser_ask_reports_fail_on_real_assertion_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    _write_junit_report(state_dir / "browser-ask-junit.xml", tests=6, failures=1, skipped=0)
    monkeypatch.setattr(worker, "run_logged", lambda *args, **kwargs: (1, 2.0, False))

    status, summary, failure_class = worker.run_browser_ask(tmp_path, state_dir, 30)

    assert status == "FAIL"
    assert failure_class == "TEST_FAILURE"
    assert "1 failure(s), 0 error(s) of 6" in summary


def test_run_browser_ask_reports_pass_when_every_test_ran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    _write_junit_report(state_dir / "browser-ask-junit.xml", tests=6, skipped=0)
    monkeypatch.setattr(worker, "run_logged", lambda *args, **kwargs: (0, 2.0, False))

    status, summary, failure_class = worker.run_browser_ask(tmp_path, state_dir, 30)

    assert status == "PASS"
    assert failure_class is None
    assert "6 real-browser test(s)" in summary


def test_browser_ask_check_is_dispatched_in_execute_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "validate_checkout", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker,
        "run_browser_ask",
        lambda repo_root, state_dir, timeout: ("PASS", "browser ask ok", None),
    )

    result = worker.execute_request(
        request(requested_checks=("browser_ask",)),
        repo_root=tmp_path,
        state_dir=tmp_path / "state",
        environment_id="jeremy-laptop",
        timeout_seconds=30,
    )

    assert result.status == "PASS"
    assert result.summary == "browser_ask: browser ask ok"


def test_run_browser_e2e_all_skipped_is_environment_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    _write_junit_report(state_dir / "browser-e2e-junit.xml", tests=120, skipped=120)
    monkeypatch.setattr(worker, "run_logged", lambda *args, **kwargs: (0, 1.0, False))

    status, summary, failure_class = worker.run_browser_e2e(tmp_path, state_dir, 30)

    assert status == "ENVIRONMENT_FAILURE"
    assert failure_class == "ENVIRONMENT_FAILURE"
    assert "no usable Chromium" in summary


def test_run_browser_e2e_missing_report_is_environment_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "run_logged", lambda *args, **kwargs: (0, 1.0, False))

    status, summary, failure_class = worker.run_browser_e2e(tmp_path, tmp_path / "state", 30)

    assert status == "ENVIRONMENT_FAILURE"
    assert failure_class == "ENVIRONMENT_FAILURE"
    assert "no readable JUnit report" in summary


def test_run_browser_e2e_timeout_is_environment_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "run_logged", lambda *args, **kwargs: (124, 30.0, True))

    status, summary, failure_class = worker.run_browser_e2e(tmp_path, tmp_path / "state", 30)

    assert status == "ENVIRONMENT_FAILURE"
    assert failure_class == "ENVIRONMENT_FAILURE"
    assert "timed out" in summary


def test_run_browser_e2e_reports_fail_on_real_assertion_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    _write_junit_report(state_dir / "browser-e2e-junit.xml", tests=120, failures=2, skipped=0)
    monkeypatch.setattr(worker, "run_logged", lambda *args, **kwargs: (1, 5.0, False))

    status, summary, failure_class = worker.run_browser_e2e(tmp_path, state_dir, 30)

    assert status == "FAIL"
    assert failure_class == "TEST_FAILURE"
    assert "2 failure(s), 0 error(s) of 120" in summary


def test_run_browser_e2e_reports_pass_when_every_test_ran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    _write_junit_report(state_dir / "browser-e2e-junit.xml", tests=120, skipped=0)
    monkeypatch.setattr(worker, "run_logged", lambda *args, **kwargs: (0, 5.0, False))

    status, summary, failure_class = worker.run_browser_e2e(tmp_path, state_dir, 30)

    assert status == "PASS"
    assert failure_class is None
    assert "120 real-browser test(s)" in summary


def test_run_browser_e2e_uses_the_browser_e2e_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    _write_junit_report(state_dir / "browser-e2e-junit.xml", tests=1, skipped=0)
    captured: dict[str, object] = {}

    def fake_run_logged(command: list[str], **kwargs: object) -> tuple[int, float, bool]:
        captured["command"] = command
        return (0, 1.0, False)

    monkeypatch.setattr(worker, "run_logged", fake_run_logged)

    worker.run_browser_e2e(tmp_path, state_dir, 30)

    command = captured["command"]
    assert isinstance(command, list)
    assert command[-2:] == ["-m", "browser_e2e"]


def test_browser_e2e_check_is_dispatched_in_execute_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "validate_checkout", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker,
        "run_browser_e2e",
        lambda repo_root, state_dir, timeout: ("PASS", "browser e2e ok", None),
    )

    result = worker.execute_request(
        request(requested_checks=("browser_e2e",)),
        repo_root=tmp_path,
        state_dir=tmp_path / "state",
        environment_id="jeremy-laptop",
        timeout_seconds=30,
    )

    assert result.status == "PASS"
    assert result.summary == "browser_e2e: browser e2e ok"


def test_unsupported_check_returns_review_required_without_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "validate_checkout", lambda *args, **kwargs: None)

    result = worker.execute_request(
        request(requested_checks=("shell",)),
        repo_root=tmp_path,
        state_dir=tmp_path / "state",
        environment_id="jeremy-laptop",
        timeout_seconds=30,
    )

    assert result.status == "REVIEW_REQUIRED"
    assert result.failure_class == "POLICY_FAILURE"
    assert result.matches_request(request(requested_checks=("shell",)))


def test_ollama_health_unavailable_is_environment_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> object:
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    status, summary, failure_class = worker.run_ollama_health(1)
    assert status == "ENVIRONMENT_FAILURE"
    assert failure_class == "ENVIRONMENT_FAILURE"
    assert "unavailable" in summary


def test_ollama_health_malformed_utf8_is_environment_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"\xff"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: Response())
    status, summary, failure_class = worker.run_ollama_health(1)
    assert status == "ENVIRONMENT_FAILURE"
    assert failure_class == "ENVIRONMENT_FAILURE"
    assert "UnicodeDecodeError" in summary


def test_ollama_health_success_reports_model_count(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"models": [{"name": "a"}, {"name": "b"}]}).encode("utf-8")

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: Response())
    status, summary, failure_class = worker.run_ollama_health(1)
    assert status == "PASS"
    assert failure_class is None
    assert "2 locally listed model" in summary


def test_failure_class_matches_aggregate_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "validate_checkout", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker,
        "run_ollama_health",
        lambda timeout: ("ENVIRONMENT_FAILURE", "offline", "ENVIRONMENT_FAILURE"),
    )
    monkeypatch.setattr(
        worker,
        "run_preflight",
        lambda repo_root, state_dir, timeout: ("FAIL", "tests failed", "TEST_FAILURE"),
    )

    result = worker.execute_request(
        request(requested_checks=("ollama_health", "preflight")),
        repo_root=tmp_path,
        state_dir=tmp_path / "state",
        environment_id="jeremy-laptop",
        timeout_seconds=30,
    )

    assert result.status == "FAIL"
    assert result.failure_class == "TEST_FAILURE"


def test_execute_request_environment_failure_on_invalid_checkout(tmp_path: Path) -> None:
    result = worker.execute_request(
        request(),
        repo_root=tmp_path,
        state_dir=tmp_path / "state",
        environment_id="jeremy-laptop",
        timeout_seconds=30,
    )

    assert result.status == "ENVIRONMENT_FAILURE"
    assert result.failure_class == "ENVIRONMENT_FAILURE"


def test_execute_request_rejects_out_of_range_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timeout_seconds must be between"):
        worker.execute_request(
            request(),
            repo_root=tmp_path,
            state_dir=tmp_path / "state",
            environment_id="jeremy-laptop",
            timeout_seconds=0,
        )


def test_write_result_uses_authoritative_result_schema(tmp_path: Path) -> None:
    evidence = {
        "request_id": "req-1",
        "repository": worker.REPOSITORY,
        "exact_sha": "a" * 40,
        "environment_id": "jeremy-laptop",
        "status": "PASS",
        "completed_at_utc": "2026-09-13T23:31:00Z",
        "summary": "preflight: passed",
    }

    path = tmp_path / "result.json"
    worker.write_result(path, WorkerResult.model_validate(evidence))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["exact_sha"] == "a" * 40
    assert "commit_sha" not in payload
    assert callable(worker.execute_request)


def test_main_reports_review_required_for_unreadable_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.json"
    exit_code = worker.main(
        [
            "--request",
            str(missing),
            "--environment-id",
            "jeremy-laptop",
            "--state-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 2
    assert "invalid WorkerRequest" in capsys.readouterr().err


def test_main_reports_worker_busy_when_lock_is_held(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    (state_dir / worker.LOCK_NAME).write_text(str(os.getpid()), encoding="ascii")

    request_path = tmp_path / "request.json"
    request_path.write_text(request().model_dump_json(), encoding="utf-8")

    exit_code = worker.main(
        [
            "--request",
            str(request_path),
            "--environment-id",
            "jeremy-laptop",
            "--state-dir",
            str(state_dir),
        ]
    )

    assert exit_code == 3
    result = json.loads((state_dir / "latest-result.json").read_text(encoding="utf-8"))
    assert result["failure_class"] == "WORKER_BUSY"
