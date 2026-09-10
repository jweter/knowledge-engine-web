"""Privacy-safe evidence helpers for Mobile Product Reality review.

This module deliberately consumes already-produced Web/Core/AI response metadata. It does
not duplicate research, retrieval, or provenance logic in the browser-facing layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ReviewState = Literal["UNREVIEWED", "PASS", "FAIL", "FLAG"]


@dataclass(frozen=True)
class MobileSmokeEvidence:
    """Traceable, sanitized evidence for one mobile end-to-end smoke review."""

    web_commit: str
    scenario_id: str
    question_reference: str
    response_state: str
    evidence_count: int
    provenance_traceable: bool
    review: ReviewState = "UNREVIEWED"
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.web_commit.strip():
            raise ValueError("web_commit is required")
        if not self.scenario_id.strip():
            raise ValueError("scenario_id is required")
        if not self.question_reference.strip():
            raise ValueError("question_reference is required")
        if self.evidence_count < 0:
            raise ValueError("evidence_count cannot be negative")

    @property
    def automated_evidence_state(self) -> str:
        """Fail closed when a response has no inspectable provenance."""
        if self.response_state != "ANSWERED":
            return "NOT_ANSWERED"
        if self.evidence_count == 0 or not self.provenance_traceable:
            return "INSUFFICIENT_EVIDENCE"
        return "EVIDENCE_PRESENT"

    def public_payload(self) -> dict[str, object]:
        """Return only the sanitized review contract; never raw source payloads."""
        payload = asdict(self)
        payload["automated_evidence_state"] = self.automated_evidence_state
        payload["remaining_acceptance_debt"] = [
            "human_mobile_safari_review" if self.review == "UNREVIEWED" else ""
        ]
        payload["remaining_acceptance_debt"] = [
            item for item in payload["remaining_acceptance_debt"] if item
        ]
        return payload
