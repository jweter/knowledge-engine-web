"""Privacy-safe evidence helpers for Mobile Product Reality review.

This module deliberately consumes already-produced Web/Core/AI response metadata. It does
not duplicate research, retrieval, or provenance logic in the browser-facing layer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256
from re import fullmatch
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from knowledge_engine_web.research_jobs import ResearchJobView

ReviewState = Literal["UNREVIEWED", "PASS", "FAIL", "FLAG"]
MOBILE_REVIEW_STATES: tuple[ReviewState, ...] = ("PASS", "FAIL", "FLAG")


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
    review_build_commit: str = ""
    review_build_identity_verified: bool = False

    def __post_init__(self) -> None:
        if not self.web_commit.strip():
            raise ValueError("web_commit is required")
        if not self.scenario_id.strip():
            raise ValueError("scenario_id is required")
        if fullmatch(r"sha256:[0-9a-fA-F]{64}", self.question_reference) is None:
            raise ValueError("question_reference must be a sha256 digest reference")
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

    @property
    def review_is_authoritative(self) -> bool:
        """A recorded verdict counts as authoritative only against a known exact build.

        A PASS/FAIL/FLAG recorded while `web_build_identity` could only return
        its placeholder is real human input and stays recorded (see
        `mobile_review_store`'s append-only history) -- it just cannot be
        treated as a settled Product Reality result until it is known exactly
        which local or deployed build produced the answer it judged.
        """
        return self.review != "UNREVIEWED" and self.review_build_identity_verified

    def public_payload(self) -> dict[str, object]:
        """Return only the sanitized review contract; never raw source payloads."""
        debt: list[str] = []
        if self.review == "UNREVIEWED":
            debt.append("human_mobile_safari_review")
        elif not self.review_build_identity_verified:
            debt.append("exact_build_identity")
        payload: dict[str, object] = {
            "web_commit": self.web_commit,
            "scenario_id": self.scenario_id,
            "question_reference": self.question_reference,
            "response_state": self.response_state,
            "evidence_count": self.evidence_count,
            "provenance_traceable": self.provenance_traceable,
            "review": self.review,
            "review_build_commit": self.review_build_commit,
            "review_authoritative": self.review_is_authoritative,
            "automated_evidence_state": self.automated_evidence_state,
            "remaining_acceptance_debt": debt,
        }
        return payload


UNVERIFIED_BUILD_IDENTITY = "unknown-build"


def web_build_identity() -> str:
    """Return this deployment's exact commit identity, or an honest placeholder.

    Render sets `RENDER_GIT_COMMIT` on every deployed service automatically --
    checked first because it is populated automatically and cannot go stale.
    `KE_WEB_BUILD_COMMIT` is the equivalent operator-set identity (e.g. a
    local `git rev-parse HEAD`) for the zero-additional-cost/local Research
    runtime that is this project's authoritative path while paid hosted
    Research infrastructure stays intentionally deferred (see
    `docs/project-status.yaml`). Neither present means no real identity
    exists -- this returns a fixed, unmistakable placeholder rather than a
    fabricated SHA.
    """

    commit = os.environ.get("RENDER_GIT_COMMIT", "").strip()
    if commit:
        return commit
    commit = os.environ.get("KE_WEB_BUILD_COMMIT", "").strip()
    return commit if commit else UNVERIFIED_BUILD_IDENTITY


def build_identity_is_verified(web_commit: str) -> bool:
    """A human verdict is only authoritative against an exact build identity.

    True for any real deployed (`RENDER_GIT_COMMIT`) or explicitly
    operator-set local (`KE_WEB_BUILD_COMMIT`) commit `web_build_identity`
    can return; false for its placeholder, which is never itself a build
    identity no matter how it is quoted back.
    """

    return bool(web_commit.strip()) and web_commit != UNVERIFIED_BUILD_IDENTITY


def question_reference(question: str) -> str:
    """Derive a privacy-safe, non-reversible reference for a submitted question."""

    digest = sha256(question.strip().encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def mobile_smoke_evidence_from_job(
    job: ResearchJobView,
    *,
    web_commit: str,
    scenario_id: str,
    review: ReviewState = "UNREVIEWED",
    notes: str = "",
    review_build_commit: str = "",
    review_build_identity_verified: bool = False,
) -> MobileSmokeEvidence:
    """Derive sanitized mobile smoke evidence from one durable Web research job.

    Consumes only the already-persisted, already-verified job presentation
    payload (`research_jobs._presentation_payload`) -- never raw provider
    output, narrative text, or an unpromoted candidate. Evidence count and
    provenance come from the same `ResearchReport` evidence-id lists Layer 2
    already renders, so this cannot disagree with what the reviewer just saw
    on the page.
    """

    result = job.result or {}
    report_build = result.get("research_report")
    report = report_build.get("report") if isinstance(report_build, dict) else None

    if (
        job.status == "completed"
        and isinstance(report_build, dict)
        and report_build.get("available")
    ):
        response_state = "ANSWERED"
    else:
        response_state = "NOT_ANSWERED"

    evidence_count = 0
    if isinstance(report, dict):
        indexed = report.get("indexed_before_run_evidence_ids") or []
        acquired = report.get("acquired_during_run_evidence_ids") or []
        evidence_count = len(indexed) + len(acquired)
    provenance_traceable = evidence_count > 0

    return MobileSmokeEvidence(
        web_commit=web_commit,
        scenario_id=scenario_id,
        question_reference=question_reference(job.question),
        response_state=response_state,
        evidence_count=evidence_count,
        provenance_traceable=provenance_traceable,
        review=review,
        notes=notes,
        review_build_commit=review_build_commit,
        review_build_identity_verified=review_build_identity_verified,
    )
