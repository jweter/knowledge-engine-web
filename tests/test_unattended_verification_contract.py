from __future__ import annotations

import pytest
from pydantic import ValidationError

from knowledge_engine_web.unattended_verification_contract import WorkerRequest, WorkerResult

SHA = "a" * 40


def test_worker_request_binds_exact_identity_and_normalizes_sha() -> None:
    request = WorkerRequest(
        repository="jweter/knowledge-engine-web",
        branch="main",
        exact_sha=SHA.upper(),
        request_id="request-1",
        requested_checks=("preflight", "ollama_health"),
        environment_id="windows-worker-1",
        created_at_utc="2026-09-13T12:00:00Z",
    )

    assert request.exact_sha == SHA
    assert request.requested_checks == ("preflight", "ollama_health")


def test_worker_request_rejects_partial_sha_and_duplicate_checks() -> None:
    with pytest.raises(ValidationError):
        WorkerRequest(
            repository="jweter/knowledge-engine-web",
            branch="main",
            exact_sha="abc123",
            request_id="request-1",
            requested_checks=("preflight",),
            environment_id="windows-worker-1",
            created_at_utc="2026-09-13T12:00:00Z",
        )

    with pytest.raises(ValidationError):
        WorkerRequest(
            repository="jweter/knowledge-engine-web",
            branch="main",
            exact_sha=SHA,
            request_id="request-1",
            requested_checks=("preflight", "preflight"),
            environment_id="windows-worker-1",
            created_at_utc="2026-09-13T12:00:00Z",
        )


def test_worker_result_matches_only_exact_request_identity() -> None:
    request = WorkerRequest(
        repository="jweter/knowledge-engine-web",
        branch="main",
        exact_sha=SHA,
        request_id="request-1",
        requested_checks=("preflight",),
        environment_id="windows-worker-1",
        created_at_utc="2026-09-13T12:00:00Z",
    )
    result = WorkerResult(
        request_id="request-1",
        repository="jweter/knowledge-engine-web",
        exact_sha=SHA,
        environment_id="windows-worker-1",
        status="PASS",
        completed_at_utc="2026-09-13T12:03:00Z",
        summary="Web preflight passed on the requested exact head.",
    )

    assert result.matches_request(request)
    assert not result.model_copy(update={"exact_sha": "b" * 40}).matches_request(request)


def test_worker_result_is_fail_closed_to_declared_statuses() -> None:
    with pytest.raises(ValidationError):
        WorkerResult(
            request_id="request-1",
            repository="jweter/knowledge-engine-web",
            exact_sha=SHA,
            environment_id="windows-worker-1",
            status="UNKNOWN",
            completed_at_utc="2026-09-13T12:03:00Z",
            summary="Unclassified result.",
        )


def test_worker_request_schema_matches_knowledge_engine_core_contract() -> None:
    """Web deliberately vendors this contract rather than importing Core as a library.

    Both copies must keep an identical JSON Schema shape (field names, types,
    required-ness) so a WorkerRequest/WorkerResult document produced by one
    repository's worker is a byte-for-byte-compatible document for the other's,
    per knowledge-engine-core issue #493 / knowledge-engine-web issue #160.
    """

    assert WorkerRequest.model_json_schema()["required"] == [
        "repository",
        "branch",
        "exact_sha",
        "request_id",
        "requested_checks",
        "environment_id",
        "created_at_utc",
    ]
    assert WorkerResult.model_json_schema()["required"] == [
        "request_id",
        "repository",
        "exact_sha",
        "environment_id",
        "status",
        "completed_at_utc",
        "summary",
    ]
