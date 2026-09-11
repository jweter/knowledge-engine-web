import pytest

from knowledge_engine_web.mobile_product_reality import (
    MobileSmokeEvidence,
    mobile_smoke_evidence_from_job,
    question_reference,
    web_build_identity,
)
from knowledge_engine_web.research_jobs import ResearchJobView

QUESTION_REF = "sha256:" + ("a" * 64)


def _job(
    *,
    status: str = "completed",
    question: str = "Does Monster Energy raise blood pressure?",
    result: dict[str, object] | None = None,
) -> ResearchJobView:
    return ResearchJobView(
        session_id="session-1",
        research_question_id="monster-question",
        question=question,
        status=status,
        created_at="2026-09-11T00:00:00+00:00",
        updated_at="2026-09-11T00:00:00+00:00",
        visitor_error=None,
        result=result,
    )


def test_mobile_smoke_evidence_keeps_human_review_separate() -> None:
    evidence = MobileSmokeEvidence(
        web_commit="abc123",
        scenario_id="iphone-smoke-1",
        question_reference=QUESTION_REF,
        response_state="ANSWERED",
        evidence_count=3,
        provenance_traceable=True,
    )

    payload = evidence.public_payload()

    assert payload["automated_evidence_state"] == "EVIDENCE_PRESENT"
    assert payload["review"] == "UNREVIEWED"
    assert payload["remaining_acceptance_debt"] == ["human_mobile_safari_review"]


def test_mobile_smoke_evidence_fails_closed_without_traceable_evidence() -> None:
    evidence = MobileSmokeEvidence(
        web_commit="abc123",
        scenario_id="iphone-smoke-2",
        question_reference=QUESTION_REF,
        response_state="ANSWERED",
        evidence_count=2,
        provenance_traceable=False,
    )

    assert evidence.automated_evidence_state == "INSUFFICIENT_EVIDENCE"


def test_reviewed_evidence_does_not_publish_free_form_notes() -> None:
    evidence = MobileSmokeEvidence(
        web_commit="abc123",
        scenario_id="iphone-smoke-3",
        question_reference=QUESTION_REF,
        response_state="ANSWERED",
        evidence_count=1,
        provenance_traceable=True,
        review="FLAG",
        notes="Private reviewer note that must stay local.",
    )

    payload = evidence.public_payload()

    assert payload["remaining_acceptance_debt"] == []
    assert "notes" not in payload


def test_question_reference_rejects_raw_question_text() -> None:
    try:
        MobileSmokeEvidence(
            web_commit="abc123",
            scenario_id="iphone-smoke-4",
            question_reference="What private thing did the user ask?",
            response_state="ANSWERED",
            evidence_count=1,
            provenance_traceable=True,
        )
    except ValueError as exc:
        assert "sha256 digest" in str(exc)
    else:
        raise AssertionError("raw question text must be rejected")


def test_question_reference_is_deterministic_and_never_the_raw_text() -> None:
    reference = question_reference("Does Monster Energy raise blood pressure?")

    assert reference.startswith("sha256:")
    assert len(reference) == len("sha256:") + 64
    assert "Monster" not in reference
    assert reference == question_reference("Does Monster Energy raise blood pressure?")


def test_web_build_identity_reads_render_git_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123def")

    assert web_build_identity() == "abc123def"


def test_web_build_identity_falls_back_when_not_deployed_on_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)

    assert web_build_identity() == "unknown-build"


def test_mobile_evidence_from_completed_job_with_report_is_answered_and_traceable() -> None:
    job = _job(
        result={
            "research_report": {
                "available": True,
                "error_code": None,
                "report": {
                    "indexed_before_run_evidence_ids": ["ev-1", "ev-2"],
                    "acquired_during_run_evidence_ids": ["ev-3"],
                },
            }
        }
    )

    evidence = mobile_smoke_evidence_from_job(job, web_commit="abc123", scenario_id="ask-session")

    assert evidence.response_state == "ANSWERED"
    assert evidence.evidence_count == 3
    assert evidence.provenance_traceable is True
    assert evidence.automated_evidence_state == "EVIDENCE_PRESENT"
    assert evidence.question_reference == question_reference(job.question)


def test_mobile_evidence_from_completed_job_without_report_fails_closed() -> None:
    job = _job(
        result={
            "research_report": {
                "available": False,
                "error_code": "base_answer_not_releaseable",
                "report": None,
            }
        }
    )

    evidence = mobile_smoke_evidence_from_job(job, web_commit="abc123", scenario_id="ask-session")

    assert evidence.response_state == "NOT_ANSWERED"
    assert evidence.evidence_count == 0
    assert evidence.provenance_traceable is False


def test_mobile_evidence_from_non_terminal_job_is_not_answered() -> None:
    job = _job(status="running", result=None)

    evidence = mobile_smoke_evidence_from_job(job, web_commit="abc123", scenario_id="ask-session")

    assert evidence.response_state == "NOT_ANSWERED"
    assert evidence.automated_evidence_state == "NOT_ANSWERED"


def test_mobile_evidence_from_completed_job_missing_report_key_fails_closed() -> None:
    job = _job(result={"research_state": "researched_answer"})

    evidence = mobile_smoke_evidence_from_job(job, web_commit="abc123", scenario_id="ask-session")

    assert evidence.response_state == "NOT_ANSWERED"
    assert evidence.evidence_count == 0
