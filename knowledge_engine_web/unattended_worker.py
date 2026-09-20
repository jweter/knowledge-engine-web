from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from .unattended_verification_contract import WorkerRequest, WorkerResult, WorkerResultStatus
from .unattended_worker_publication import publish_sanitized_result

REPOSITORY = "jweter/knowledge-engine-web"
EXPECTED_ORIGIN = "https://github.com/jweter/knowledge-engine-web.git"
LOCK_NAME = "worker.lock"
DEFAULT_TIMEOUT_SECONDS = 3600
MAX_TIMEOUT_SECONDS = 7200
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
# Bounded first slice of issue #160: canonical repository preflight plus a loopback
# Ollama reachability probe (Research capability depends on a local Ollama runtime).
# Browser/service Ask-flow automation is materially larger scope and is a deliberate,
# separate follow-up slice, matching knowledge-engine-core issue #493's own precedent
# of starting with "preflight"/"ollama_health" before adding checks incrementally.
AUTHORIZED_CHECKS = frozenset({"preflight", "ollama_health"})
WINDOWS_CREATE_NEW_PROCESS_GROUP = 0x00000200

# Matches a secret-flavored key (optionally prefixed with other identifier
# segments, e.g. "GITHUB_TOKEN" or "DATABASE_PASSWORD") followed by its value,
# whether the key/value pair is written bare ("token=abc"), as a JSON member
# ('"token": "abc"'), or as a Python dict repr ("'token': 'abc'"). The value
# alternation prefers a quoted span (which may contain internal whitespace,
# e.g. "Bearer <token>") and falls back to a single unquoted token.
_SECRET_KEY_VALUE = re.compile(
    r"(?i)([\"']?)((?:[A-Za-z0-9]+[_-])*(?:authorization|api[_-]?key|token|password))(?(1)\1)"
    r"\s*[:=]\s*(?:([\"'])(.*?)\3|(\S+))"
)
# Strips credentials embedded in a URL's userinfo component (scheme://user:pass@host).
_URL_CREDENTIALS = re.compile(r"(?i)(://)[^\s/@]+:[^\s/@]+@")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def default_state_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "KnowledgeEngine" / "unattended-worker-web"
    return Path.home() / ".knowledge-engine" / "unattended-worker-web"


def normalize_origin(value: str) -> str:
    text = value.strip().replace("\\", "/")
    if text.endswith("/"):
        text = text[:-1]
    if text.startswith("git@github.com:"):
        text = "https://github.com/" + text.removeprefix("git@github.com:")
    return text.lower().removesuffix(".git")


def origin_is_expected(value: str) -> bool:
    return normalize_origin(value) == normalize_origin(EXPECTED_ORIGIN)


def load_request(path: Path) -> WorkerRequest:
    return WorkerRequest.model_validate_json(path.read_text(encoding="utf-8"))


def run_capture(
    args: list[str], *, cwd: Path | None = None, timeout_seconds: float = 30.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def git_output(repo_root: Path, *args: str) -> str:
    proc = run_capture(["git", "-C", str(repo_root), *args], timeout_seconds=60.0)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "git command failed").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail[:500]}")
    return proc.stdout.strip()


def validate_checkout(repo_root: Path, request: WorkerRequest, *, environment_id: str) -> None:
    if request.repository != REPOSITORY:
        raise RuntimeError(f"request repository must be {REPOSITORY}")
    if request.environment_id != environment_id:
        raise RuntimeError(
            f"worker environment mismatch: expected {request.environment_id}, got {environment_id}"
        )
    if not (repo_root / ".git").exists():
        raise RuntimeError(f"Not a Git checkout: {repo_root}")
    origin = git_output(repo_root, "remote", "get-url", "origin")
    if not origin_is_expected(origin):
        raise RuntimeError(f"Unexpected origin remote: {origin}")
    branch = git_output(repo_root, "branch", "--show-current")
    if branch != request.branch:
        raise RuntimeError(
            f"Checkout branch mismatch: expected {request.branch}, got {branch or '<detached>'}"
        )
    head = git_output(repo_root, "rev-parse", "HEAD").lower()
    if head != request.exact_sha:
        raise RuntimeError(f"Checkout identity mismatch: expected {request.exact_sha}, got {head}")
    dirty = git_output(repo_root, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise RuntimeError("Checkout has modified tracked files; refusing to attest exact SHA")
    untracked = git_output(repo_root, "ls-files", "--others", "--exclude-standard")
    if untracked:
        raise RuntimeError("Checkout has untracked files; refusing to attest exact SHA")


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        proc = run_capture(["tasklist.exe", "/FI", f"PID eq {pid}", "/NH"], timeout_seconds=10.0)
        return proc.returncode == 0 and re.search(rf"\b{pid}\b", proc.stdout) is not None
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_lock(state_dir: Path) -> tuple[int | None, bool]:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / LOCK_NAME
    for attempt in range(3):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            return fd, True
        except FileExistsError:
            try:
                pid = int(path.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                if attempt == 0:
                    time.sleep(0.05)
                    continue
                pid = -1
            if pid_is_alive(pid):
                return None, False
            path.unlink(missing_ok=True)
    return None, False


def release_lock(state_dir: Path, fd: int) -> None:
    try:
        os.close(fd)
    finally:
        (state_dir / LOCK_NAME).unlink(missing_ok=True)


def sanitize_text(text: str, *, repo_root: Path) -> str:
    result = text
    for raw, replacement in (
        (str(repo_root), "<REPO_ROOT>"),
        (str(Path.home()), "%USERPROFILE%"),
    ):
        if raw:
            result = result.replace(raw, replacement)
            result = result.replace(raw.replace("\\", "/"), replacement)
    result = _URL_CREDENTIALS.sub(r"\1<REDACTED>@", result)
    return _SECRET_KEY_VALUE.sub(lambda m: f"{m.group(2)}=<REDACTED>", result)


def write_result(path: Path, result: WorkerResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _terminate_posix_process_group(pid: int) -> None:
    """Terminate a POSIX process group without referencing POSIX-only attrs statically.

    Windows type environments do not expose ``os.killpg`` or ``signal.SIGKILL``.
    Resolve them dynamically only on the POSIX execution path so strict typing on
    Windows remains valid while preserving the existing POSIX process-group kill.
    """
    killpg = getattr(os, "killpg", None)
    sigkill = getattr(signal, "SIGKILL", None)
    if not callable(killpg) or sigkill is None:
        raise RuntimeError("POSIX process-group termination is unavailable")
    killpg(pid, sigkill)


def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30.0,
        )
    else:
        with contextlib.suppress(ProcessLookupError):
            _terminate_posix_process_group(proc.pid)
    try:
        proc.wait(timeout=30.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=30.0)


def run_logged(
    args: list[str], *, cwd: Path, log_path: Path, timeout_seconds: float
) -> tuple[int, float, bool]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with log_path.open("w", encoding="utf-8", errors="replace") as handle:
        if os.name == "nt":
            proc = subprocess.Popen(
                args,
                cwd=str(cwd),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=WINDOWS_CREATE_NEW_PROCESS_GROUP,
            )
        else:
            proc = subprocess.Popen(
                args,
                cwd=str(cwd),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        try:
            code = int(proc.wait(timeout=timeout_seconds))
        except subprocess.TimeoutExpired:
            handle.write(f"\nTIMEOUT after {timeout_seconds:.0f} seconds\n")
            handle.flush()
            _terminate_process_tree(proc)
            code = 124
            timed_out = True
    return code, time.monotonic() - started, timed_out


def log_tail(path: Path, *, repo_root: Path, lines: int = 40) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return sanitize_text("\n".join(content[-lines:]), repo_root=repo_root)


def run_preflight(
    repo_root: Path, state_dir: Path, timeout_seconds: int
) -> tuple[WorkerResultStatus, str, str | None]:
    script = repo_root / "engineering" / "preflight.py"
    if not script.is_file():
        return "REVIEW_REQUIRED", "engineering/preflight.py is missing", "POLICY_FAILURE"
    log_path = state_dir / "logs" / "preflight.log"
    evidence_path = state_dir / "preflight-evidence.json"
    code, duration, timed_out = run_logged(
        [sys.executable, str(script), "--evidence", str(evidence_path)],
        cwd=repo_root,
        log_path=log_path,
        timeout_seconds=float(timeout_seconds),
    )
    if timed_out:
        return "ENVIRONMENT_FAILURE", "Canonical preflight timed out.", "ENVIRONMENT_FAILURE"
    if code != 0:
        tail = log_tail(log_path, repo_root=repo_root)
        summary = f"Canonical preflight failed after {duration:.3f}s."
        if tail:
            summary += f" Last output: {tail[:1200]}"
        return "FAIL", summary, "TEST_FAILURE"
    return "PASS", f"Canonical preflight passed in {duration:.3f}s.", None


def run_ollama_health(timeout_seconds: int) -> tuple[WorkerResultStatus, str, str | None]:
    timeout = min(float(timeout_seconds), 20.0)
    request = urllib.request.Request(
        OLLAMA_TAGS_URL,
        headers={"User-Agent": "KnowledgeEngineWeb-Unattended-Verification/1"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            code = int(response.status)
    except (
        OSError,
        urllib.error.URLError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        elapsed = time.monotonic() - started
        return (
            "ENVIRONMENT_FAILURE",
            f"Ollama health probe unavailable after {elapsed:.3f}s: {type(exc).__name__}.",
            "ENVIRONMENT_FAILURE",
        )
    if code != 200 or not isinstance(payload, dict):
        return (
            "ENVIRONMENT_FAILURE",
            "Ollama health probe returned an unexpected response.",
            "ENVIRONMENT_FAILURE",
        )
    models = payload.get("models")
    model_count = len(models) if isinstance(models, list) else 0
    return (
        "PASS",
        f"Ollama responded successfully with {model_count} locally listed model(s).",
        None,
    )


def _aggregate_status(statuses: list[WorkerResultStatus]) -> WorkerResultStatus:
    if "FAIL" in statuses:
        return "FAIL"
    if "ENVIRONMENT_FAILURE" in statuses:
        return "ENVIRONMENT_FAILURE"
    if "PRODUCT_REALITY_REQUIRED" in statuses:
        return "PRODUCT_REALITY_REQUIRED"
    if "REVIEW_REQUIRED" in statuses:
        return "REVIEW_REQUIRED"
    return "PASS"


def execute_request(
    request: WorkerRequest,
    *,
    repo_root: Path,
    state_dir: Path,
    environment_id: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> WorkerResult:
    if timeout_seconds < 1 or timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
    try:
        validate_checkout(repo_root, request, environment_id=environment_id)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return WorkerResult(
            request_id=request.request_id,
            repository=request.repository,
            exact_sha=request.exact_sha,
            environment_id=request.environment_id,
            status="ENVIRONMENT_FAILURE",
            completed_at_utc=utc_now(),
            summary=sanitize_text(str(exc), repo_root=repo_root)[:2000],
            failure_class="ENVIRONMENT_FAILURE",
        )

    unsupported = sorted(set(request.requested_checks) - AUTHORIZED_CHECKS)
    if unsupported:
        return WorkerResult(
            request_id=request.request_id,
            repository=request.repository,
            exact_sha=request.exact_sha,
            environment_id=request.environment_id,
            status="REVIEW_REQUIRED",
            completed_at_utc=utc_now(),
            summary=f"Unsupported requested check(s): {', '.join(unsupported)}.",
            failure_class="POLICY_FAILURE",
        )

    statuses: list[WorkerResultStatus] = []
    summaries: list[str] = []
    failure_classes: list[str | None] = []
    for check in request.requested_checks:
        if check == "preflight":
            status, summary, failure_class = run_preflight(repo_root, state_dir, timeout_seconds)
        else:
            status, summary, failure_class = run_ollama_health(timeout_seconds)
        statuses.append(status)
        summaries.append(f"{check}: {summary}")
        failure_classes.append(failure_class)

    status = _aggregate_status(statuses)
    failure_class = next(
        (
            current_failure
            for current_status, current_failure in zip(statuses, failure_classes, strict=True)
            if current_status == status and current_failure is not None
        ),
        None,
    )
    summary = " ".join(summaries)[:2000]
    return WorkerResult(
        request_id=request.request_id,
        repository=request.repository,
        exact_sha=request.exact_sha,
        environment_id=request.environment_id,
        status=status,
        completed_at_utc=utc_now(),
        summary=summary,
        failure_class=failure_class,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one bounded unattended Knowledge Engine Web verification request."
    )
    parser.add_argument("--request", type=Path, required=True, help="WorkerRequest JSON document.")
    parser.add_argument(
        "--environment-id", required=True, help="Exact configured worker environment ID."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--result", type=Path, default=None)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_dir = args.state_dir.expanduser().resolve()
    result_path = args.result or state_dir / "latest-result.json"
    try:
        request = load_request(args.request)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REVIEW_REQUIRED: invalid WorkerRequest: {exc}", file=sys.stderr)
        return 2

    lock_fd, acquired = acquire_lock(state_dir)
    if not acquired or lock_fd is None:
        result = WorkerResult(
            request_id=request.request_id,
            repository=request.repository,
            exact_sha=request.exact_sha,
            environment_id=request.environment_id,
            status="REVIEW_REQUIRED",
            completed_at_utc=utc_now(),
            summary="Another unattended worker owns the local execution lease.",
            failure_class="WORKER_BUSY",
        )
        write_result(result_path, result)
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            publish_sanitized_result(result, state_dir)
        return 3

    try:
        result = execute_request(
            request,
            repo_root=args.repo_root.expanduser().resolve(),
            state_dir=state_dir,
            environment_id=args.environment_id,
            timeout_seconds=args.timeout_seconds,
        )
        write_result(result_path, result)
    finally:
        release_lock(state_dir, lock_fd)

    # Remote reporting is deliberately best-effort and non-authoritative. The local
    # WorkerResult has already been finalized and persisted before this call.
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        publish_sanitized_result(result, state_dir)

    if result.status == "PASS":
        return 0
    if result.status in {"REVIEW_REQUIRED", "PRODUCT_REALITY_REQUIRED"}:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
