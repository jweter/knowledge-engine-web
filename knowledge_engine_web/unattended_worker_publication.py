from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .unattended_verification_contract import WorkerResult

_REPOSITORY = "jweter/knowledge-engine-web"
_ISSUE_NUMBER = 160
_STATE_FILE = "github-publication.json"


def _public_payload(result: WorkerResult) -> dict[str, object]:
    return {
        "exact_sha": result.exact_sha,
        "status": result.status,
        "failure_class": result.failure_class,
        "completed_at_utc": result.completed_at_utc,
        # WorkerResult.summary is already produced through the worker's sanitizer.
        # Keep the remote excerpt bounded even if the local result retains more detail.
        "summary": result.summary[:1200],
    }


def _body(payload: dict[str, object]) -> str:
    failure_class = payload["failure_class"] or "none"
    return "\n".join(
        [
            "## Unattended Web verification — sanitized exact-head result",
            "",
            f"- **Exact commit:** `{payload['exact_sha']}`",
            f"- **Result:** **{payload['status']}**",
            f"- **Failure class:** `{failure_class}`",
            f"- **Completed:** {payload['completed_at_utc']}",
            "",
            "### Sanitized worker summary",
            "",
            "```text",
            str(payload["summary"]),
            "```",
            "",
            "The local worker remains the deterministic authority for this execution. "
            "This comment intentionally omits the machine/environment identifier, request ID, "
            "absolute local paths, credentials, private source documents, and raw local logs. "
            "Publication failure cannot promote or demote the verification result.",
        ]
    )


def publish_sanitized_result(
    result: WorkerResult,
    state_dir: Path,
    *,
    os_name: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    """Best-effort remote observability for the local Web verification worker.

    The worker already stores the full local result. This publication surface exists so
    a cached FAIL/ENVIRONMENT_FAILURE on the portfolio ledger is diagnosable without a
    person opening the laptop or copying logs. Only the worker's bounded sanitized summary
    is permitted to leave the machine.
    """

    current_os = os.name if os_name is None else os_name
    if current_os != "nt":
        return "LOCAL_ONLY_NON_WINDOWS"

    state_dir.mkdir(parents=True, exist_ok=True)
    payload = _public_payload(result)
    key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    state_path = state_dir / _STATE_FILE
    try:
        prior = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        prior = {}
    if isinstance(prior, dict) and prior.get("publication_key") == key:
        return "UNCHANGED"

    gh = which("gh.exe") or which("gh")
    if gh is None:
        _write_state(state_path, "LOCAL_ONLY", key, "GitHub CLI is unavailable")
        return "LOCAL_ONLY"

    try:
        auth = runner(
            [gh, "auth", "status"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        _write_state(state_path, "LOCAL_ONLY", key, "GitHub CLI auth check failed")
        return "LOCAL_ONLY"
    if auth.returncode != 0:
        _write_state(state_path, "LOCAL_ONLY", key, "GitHub CLI is not authenticated")
        return "LOCAL_ONLY"

    try:
        posted = runner(
            [
                gh,
                "issue",
                "comment",
                str(_ISSUE_NUMBER),
                "--repo",
                _REPOSITORY,
                "--body",
                _body(payload),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        _write_state(state_path, "LOCAL_ONLY", key, "GitHub issue publication failed")
        return "LOCAL_ONLY"
    if posted.returncode != 0:
        _write_state(state_path, "LOCAL_ONLY", key, "GitHub issue publication was rejected")
        return "LOCAL_ONLY"

    _write_state(state_path, "PUBLISHED", key, "Sanitized result posted to issue #160")
    return "PUBLISHED"


def _write_state(path: Path, status: str, key: str, detail: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": status,
                "detail": detail,
                "publication_key": key,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
