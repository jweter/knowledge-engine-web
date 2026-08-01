"""Evidence Intelligence: deterministic, no-LLM confidence scoring.

Independently rebuilds `knowledge-engine-core`'s
`knowledge_engine/evidence_intelligence.py` formula (see
`docs/evidence_intelligence_design.md` in that repository) against this
project's own `EvidenceRecordDetail`/`RelationshipEdge` dataclasses,
rather than importing `knowledge_engine` -- the same "read `core`'s data,
never its code" posture `graph_reader.py`/`report_renderer.py` already
follow (`docs/web_design.md`'s Decision section). The two formulas must
stay in sync by hand; a future shared package is the real fix, not
attempted here.

Every function is a pure computation over already-stored fields -- never
an LLM call, never a guess. Evidence Quality, Evidence Consensus, and
Claim Confidence are three separate numbers that must never collapse
into one; callers must keep them displayed separately.
"""

from __future__ import annotations

from dataclasses import dataclass

from knowledge_engine_web.evidence_reader import EvidenceRecordDetail
from knowledge_engine_web.graph_reader import RelationshipEdge

CLINICAL_MEDICINE_V1 = "clinical_medicine_v1"

_STUDY_DESIGN_WEIGHTS: dict[str, int] = {
    "systematic_review_meta_analysis": 40,
    "meta_analysis": 40,
    "systematic_review": 40,
    "randomized_controlled_trial": 35,
    "cross_over_trial": 35,
    "prospective_observational_cohort": 25,
    "cohort_study": 25,
    "retrospective_observational_cohort": 15,
    "retrospective_study": 15,
    "cross_sectional_study": 15,
    "observational_study": 15,
    "pilot_study": 5,
    "case_report": 5,
}

_MANUAL_EXTRACTION_METHODS = frozenset({"manual_human_review", "manual"})

_CONSENSUS_ELIGIBLE_TYPES = frozenset({"supports", "contradicts", "qualifies", "contextualizes"})


@dataclass(frozen=True)
class EvidenceQuality:
    """How trustworthy is this one `EvidenceRecord`, on its own."""

    evidence_record_id: str
    score: int
    study_design_tier: str
    manually_reviewed: bool


def compute_evidence_quality(evidence: EvidenceRecordDetail) -> EvidenceQuality:
    """Compute Evidence Quality for one evidence record.

    See `evidence_intelligence.py`'s counterpart in `knowledge-engine-core`
    for the full rationale. No `sample_size` term -- that field does not
    exist in `EvidenceRecord` today.
    """

    study_type = evidence.study_type
    design_points = _STUDY_DESIGN_WEIGHTS.get(study_type, 0) if study_type else 0
    tier = (
        study_type
        if study_type in _STUDY_DESIGN_WEIGHTS
        else ("missing" if not study_type else "unrecognized")
    )

    manually_reviewed = evidence.extraction_method in _MANUAL_EXTRACTION_METHODS and bool(
        evidence.review_checklist
    )
    rigor_points = 40 if manually_reviewed else 25

    penalty = 0
    if not evidence.limitations:
        penalty -= 5
    if not evidence.uncertainty_notes:
        penalty -= 5

    raw = max(0, min(80, design_points + rigor_points + penalty))
    score = round(raw * 1.25)

    return EvidenceQuality(
        evidence_record_id=evidence.evidence_record_id,
        score=score,
        study_design_tier=tier,
        manually_reviewed=manually_reviewed,
    )


@dataclass(frozen=True)
class EvidenceConsensus:
    """How consistently the literature agrees, for claims compared to each other at all."""

    relationship_edge_count: int
    supports_count: int
    contradicts_count: int
    agreement_total: int
    score: int | None
    reliability: str


def compute_evidence_consensus(relationships: list[RelationshipEdge]) -> EvidenceConsensus:
    """Compute Evidence Consensus from the relationship edges touching one claim.

    `supersedes` edges do not count toward eligibility -- they retire the
    older claim rather than stating current agreement/disagreement.
    """

    eligible = [
        r.relationship_type
        for r in relationships
        if r.relationship_type in _CONSENSUS_ELIGIBLE_TYPES
    ]
    edge_count = len(eligible)
    supports = eligible.count("supports")
    contradicts = eligible.count("contradicts")
    agreement_total = supports + contradicts

    if edge_count < 2:
        reliability = "insufficient"
    elif edge_count == 2:
        reliability = "low"
    elif edge_count <= 4:
        reliability = "moderate"
    else:
        reliability = "high"

    score = (
        round(supports / agreement_total * 100) if edge_count >= 2 and agreement_total > 0 else None
    )

    return EvidenceConsensus(
        relationship_edge_count=edge_count,
        supports_count=supports,
        contradicts_count=contradicts,
        agreement_total=agreement_total,
        score=score,
        reliability=reliability,
    )


@dataclass(frozen=True)
class ClaimConfidence:
    """Given quality and consensus together, how confident should we be right now."""

    score: int | None
    reliability: str
    mean_evidence_quality: float | None


def compute_claim_confidence(
    participating_qualities: list[EvidenceQuality], consensus: EvidenceConsensus
) -> ClaimConfidence:
    """Combine Evidence Quality and Evidence Consensus -- a product, never an average or max."""

    if consensus.score is None or not participating_qualities:
        return ClaimConfidence(
            score=None, reliability=consensus.reliability, mean_evidence_quality=None
        )

    mean_quality = sum(q.score for q in participating_qualities) / len(participating_qualities)
    score = round((mean_quality / 100) * (consensus.score / 100) * 100)
    return ClaimConfidence(
        score=score, reliability=consensus.reliability, mean_evidence_quality=mean_quality
    )


@dataclass(frozen=True)
class EvidenceCoverage:
    """Corpus-relative coverage: how much of the corpus participates in a confirmed relationship."""

    total_records: int
    records_in_relationship: int
    percentage: int


def compute_evidence_coverage(
    *, total_records: int, records_in_relationship: int
) -> EvidenceCoverage:
    """Compute corpus-relative Evidence Coverage."""

    percentage = round(records_in_relationship / total_records * 100) if total_records else 0
    return EvidenceCoverage(
        total_records=total_records,
        records_in_relationship=records_in_relationship,
        percentage=percentage,
    )


def render_synthesis(
    *,
    consensus: EvidenceConsensus,
    quality: EvidenceQuality,
    confidence: ClaimConfidence,
    coverage: EvidenceCoverage,
) -> list[str]:
    """Render a deterministic, templated synthesis over the computed numbers -- not an LLM call."""

    lines = [
        f"{consensus.relationship_edge_count} relationship(s) recorded for this claim: "
        f"{consensus.supports_count} support, {consensus.contradicts_count} contradict.",
        f"Evidence Quality: {quality.score}/100 ({quality.study_design_tier}, "
        f"{'manually reviewed' if quality.manually_reviewed else 'automated, pending review'}).",
    ]
    if consensus.score is None:
        lines.append(
            f"Evidence Consensus: not yet assessable (reliability: {consensus.reliability})."
        )
        lines.append(
            "Claim Confidence: not yet assessable (needs at least one more relationship edge)."
        )
    else:
        lines.append(
            f"Evidence Consensus: {consensus.score}/100 "
            f"({consensus.supports_count} of {consensus.agreement_total} agree)."
        )
        lines.append(
            f"Claim Confidence: {confidence.score}/100, reliability: {confidence.reliability} "
            f"({consensus.relationship_edge_count} relationships)."
        )
    lines.append(
        f"Evidence coverage: {coverage.records_in_relationship} of {coverage.total_records} "
        f"corpus records ({coverage.percentage}%) participate in a confirmed relationship."
    )
    return lines
