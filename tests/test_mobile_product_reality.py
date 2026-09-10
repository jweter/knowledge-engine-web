from knowledge_engine_web.mobile_product_reality import MobileSmokeEvidence

QUESTION_REF = "sha256:" + ("a" * 64)


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
