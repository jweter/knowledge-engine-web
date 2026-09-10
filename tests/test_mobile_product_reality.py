from knowledge_engine_web.mobile_product_reality import MobileSmokeEvidence


def test_mobile_smoke_evidence_keeps_human_review_separate() -> None:
    evidence = MobileSmokeEvidence(
        web_commit="abc123",
        scenario_id="iphone-smoke-1",
        question_reference="sha256:example",
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
        question_reference="sha256:example",
        response_state="ANSWERED",
        evidence_count=2,
        provenance_traceable=False,
    )

    assert evidence.automated_evidence_state == "INSUFFICIENT_EVIDENCE"


def test_reviewed_evidence_does_not_claim_remaining_human_mobile_debt() -> None:
    evidence = MobileSmokeEvidence(
        web_commit="abc123",
        scenario_id="iphone-smoke-3",
        question_reference="sha256:example",
        response_state="ANSWERED",
        evidence_count=1,
        provenance_traceable=True,
        review="FLAG",
        notes="Citation card is difficult to inspect on a narrow viewport.",
    )

    assert evidence.public_payload()["remaining_acceptance_debt"] == []
