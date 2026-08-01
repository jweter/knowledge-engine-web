from __future__ import annotations

from knowledge_engine_web.evidence_intelligence import (
    EvidenceQuality,
    compute_claim_confidence,
    compute_evidence_consensus,
    compute_evidence_coverage,
    compute_evidence_quality,
    render_synthesis,
)
from knowledge_engine_web.evidence_reader import EvidenceRecordDetail
from knowledge_engine_web.graph_reader import RelationshipEdge


def _evidence(**overrides: object) -> EvidenceRecordDetail:
    defaults: dict[str, object] = {
        "evidence_record_id": "ev-1",
        "research_question": None,
        "claim_text": None,
        "evidence_direction": None,
        "study_type": "randomized_controlled_trial",
        "source_type": None,
        "source_title": None,
        "source_doi": None,
        "population": None,
        "intervention": None,
        "comparator": None,
        "outcome": None,
        "result_summary": None,
        "short_source_excerpt": None,
        "limitations": ["A limitation."],
        "uncertainty_notes": "An uncertainty.",
        "confidence_note": None,
        "extraction_method": "manual_human_review",
        "extraction_status": "draft_manual_prototype",
        "review_status": "draft",
        "review_checklist": {"source_verified": True},
    }
    defaults.update(overrides)
    return EvidenceRecordDetail(**defaults)  # type: ignore[arg-type]


def _relationship(relationship_type: str) -> RelationshipEdge:
    return RelationshipEdge(
        relationship_type=relationship_type,
        direction="source",
        rationale="Because.",
        other_evidence_record_id="ev-other",
    )


def test_evidence_quality_manual_scores_higher_than_automated() -> None:
    manual = compute_evidence_quality(_evidence())
    automated = compute_evidence_quality(
        _evidence(extraction_method="m52-evidence-classification-v1", review_checklist={})
    )

    assert manual.manually_reviewed is True
    assert automated.manually_reviewed is False
    assert manual.score > automated.score


def test_evidence_quality_penalizes_missing_limitations() -> None:
    complete = compute_evidence_quality(_evidence())
    incomplete = compute_evidence_quality(_evidence(limitations=[], uncertainty_notes=None))

    assert incomplete.score < complete.score


def test_evidence_consensus_insufficient_below_two_edges() -> None:
    consensus = compute_evidence_consensus([_relationship("supports")])

    assert consensus.score is None
    assert consensus.reliability == "insufficient"


def test_evidence_consensus_computes_ratio() -> None:
    consensus = compute_evidence_consensus(
        [_relationship("supports"), _relationship("supports"), _relationship("contradicts")]
    )

    assert consensus.relationship_edge_count == 3
    assert consensus.score == 67
    assert consensus.reliability == "moderate"


def test_evidence_consensus_excludes_supersedes() -> None:
    consensus = compute_evidence_consensus(
        [_relationship("supersedes"), _relationship("supersedes")]
    )

    assert consensus.relationship_edge_count == 0
    assert consensus.reliability == "insufficient"


def test_claim_confidence_not_computed_when_consensus_insufficient() -> None:
    quality = compute_evidence_quality(_evidence())
    consensus = compute_evidence_consensus([_relationship("supports")])

    confidence = compute_claim_confidence([quality], consensus)

    assert confidence.score is None
    assert confidence.reliability == "insufficient"


def test_claim_confidence_multiplies_rather_than_averages() -> None:
    high = EvidenceQuality(
        evidence_record_id="ev-1",
        score=100,
        study_design_tier="meta_analysis",
        manually_reviewed=True,
    )
    low = EvidenceQuality(
        evidence_record_id="ev-2",
        score=20,
        study_design_tier="case_report",
        manually_reviewed=False,
    )
    consensus = compute_evidence_consensus(
        [_relationship("supports"), _relationship("supports"), _relationship("supports")]
    )

    confidence = compute_claim_confidence([high, low], consensus)

    assert confidence.mean_evidence_quality == 60
    assert confidence.score == 60


def test_evidence_coverage_percentage() -> None:
    coverage = compute_evidence_coverage(total_records=155, records_in_relationship=7)

    assert coverage.percentage == 5


def test_render_synthesis_insufficient_consensus_omits_confidence() -> None:
    quality = compute_evidence_quality(_evidence())
    consensus = compute_evidence_consensus([_relationship("supports")])
    confidence = compute_claim_confidence([quality], consensus)
    coverage = compute_evidence_coverage(total_records=155, records_in_relationship=7)

    lines = "\n".join(
        render_synthesis(
            consensus=consensus, quality=quality, confidence=confidence, coverage=coverage
        )
    )

    assert "not yet assessable" in lines


def test_render_synthesis_agreement_denominator_excludes_non_agreement_edges() -> None:
    quality = compute_evidence_quality(_evidence())
    consensus = compute_evidence_consensus(
        [_relationship("supports"), _relationship("supports"), _relationship("contextualizes")]
    )
    confidence = compute_claim_confidence([quality, quality], consensus)
    coverage = compute_evidence_coverage(total_records=155, records_in_relationship=7)

    lines = "\n".join(
        render_synthesis(
            consensus=consensus, quality=quality, confidence=confidence, coverage=coverage
        )
    )

    # Regression test for a real bug caught via a live web smoke test: 3
    # eligible edges exist, but only 2 (both supports) participate in the
    # agreement ratio -- the third is contextualizes. "X of Y agree" must
    # use supports + contradicts as the denominator, not the total
    # eligible-edge count.
    assert "(2 of 2 agree)" in lines
    assert "(2 of 3 agree)" not in lines
