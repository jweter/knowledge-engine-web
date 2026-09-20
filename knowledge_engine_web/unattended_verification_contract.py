from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WorkerResultStatus = Literal[
    "PASS",
    "FAIL",
    "REVIEW_REQUIRED",
    "PRODUCT_REALITY_REQUIRED",
    "ENVIRONMENT_FAILURE",
]


class WorkerRequest(BaseModel):
    """Cross-repository request identity for unattended Knowledge Engine verification.

    Field-for-field identical to knowledge-engine-core's
    ``unattended_verification_contract.WorkerRequest`` (anchored by Core issue #493):
    Web deliberately vendors this shape rather than importing Core as a library
    (Web's architecture does not depend on Core's Python package), so a request/result
    JSON document produced by one repository's worker validates against the other's
    schema unchanged. Keep both copies in sync; do not diverge the shape without
    coordinating the change across knowledge-engine-core/web/ai.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    repository: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    exact_sha: str
    request_id: str = Field(min_length=1)
    requested_checks: tuple[str, ...] = Field(min_length=1)
    environment_id: str = Field(min_length=1)
    created_at_utc: str = Field(min_length=1)

    @field_validator("exact_sha")
    @classmethod
    def validate_exact_sha(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 40 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("exact_sha must be a full 40-character hexadecimal commit SHA")
        return normalized

    @field_validator("requested_checks")
    @classmethod
    def validate_requested_checks(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item for item in normalized):
            raise ValueError("requested_checks may not contain empty names")
        if len(set(normalized)) != len(normalized):
            raise ValueError("requested_checks may not contain duplicates")
        return normalized


class WorkerResult(BaseModel):
    """Sanitized machine-readable result returned by an unattended worker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    exact_sha: str
    environment_id: str = Field(min_length=1)
    status: WorkerResultStatus
    completed_at_utc: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=2000)
    artifact_refs: tuple[str, ...] = ()
    failure_class: str | None = None

    @field_validator("exact_sha")
    @classmethod
    def validate_exact_sha(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 40 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("exact_sha must be a full 40-character hexadecimal commit SHA")
        return normalized

    def matches_request(self, request: WorkerRequest) -> bool:
        """Return whether this result can be attributed to the exact request identity."""

        return (
            self.request_id == request.request_id
            and self.repository == request.repository
            and self.exact_sha == request.exact_sha
            and self.environment_id == request.environment_id
        )
