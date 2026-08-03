"""Corpus-wide Evidence Intelligence dashboard: aggregate distributions, not per-claim detail.

`docs/roadmap.md`'s "Planned: Reviewer & Evidence Intelligence Tooling"
section names this as the first item: "a report or `knowledge-engine-web`
page showing the distribution of Evidence Quality scores and Claim
Confidence reliability tiers across the whole corpus, extending M58's
per-claim view to a corpus-wide one." Never a new computation -- reuses
the exact same `compute_evidence_quality`/`compute_evidence_consensus`/
`compute_claim_confidence` functions every claim-detail page already
calls (`evidence_intelligence.py`, `main.py`'s `_compute_evidence_intelligence`),
just run across every claim with configured evidence instead of one.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from knowledge_engine_web.evidence_intelligence import (
    compute_claim_confidence,
    compute_evidence_consensus,
    compute_evidence_quality,
)
from knowledge_engine_web.evidence_reader import read_evidence_record
from knowledge_engine_web.graph_reader import list_claims, read_claim_detail

_QUALITY_BUCKETS = (
    ("80-100", 80, 101),
    ("60-79", 60, 80),
    ("40-59", 40, 60),
    ("20-39", 20, 40),
    ("0-19", 0, 20),
)


@dataclass(frozen=True)
class EvidenceIntelligenceDashboard:
    """Corpus-wide distribution of Evidence Quality scores and Claim Confidence reliability."""

    claims_total: int
    claims_with_evidence_configured: int
    quality_bucket_counts: dict[str, int]
    mean_quality_score: float | None
    confidence_reliability_counts: dict[str, int]
    not_yet_assessable_count: int


def _quality_bucket(score: int) -> str:
    for label, low, high in _QUALITY_BUCKETS:
        if low <= score < high:
            return label
    return _QUALITY_BUCKETS[-1][0]


def build_evidence_intelligence_dashboard(
    engine: Engine, evidence_path: Path
) -> EvidenceIntelligenceDashboard:
    """Aggregate Evidence Quality/Claim Confidence across every claim with evidence configured.

    Skips a claim entirely when `evidence_path` has no record for it --
    matching every existing claim-detail page's "not configured" posture,
    never a guessed or zero score.
    """

    claims = list_claims(engine)
    quality_scores: list[int] = []
    quality_buckets: Counter[str] = Counter()
    reliability_counts: Counter[str] = Counter()
    not_yet_assessable = 0

    for claim in claims:
        evidence = read_evidence_record(evidence_path, claim.evidence_record_id)
        if evidence is None:
            continue

        detail = read_claim_detail(engine, claim.evidence_record_id)
        relationships = detail.relationships if detail is not None else []

        quality = compute_evidence_quality(evidence)
        quality_scores.append(quality.score)
        quality_buckets[_quality_bucket(quality.score)] += 1

        consensus = compute_evidence_consensus(relationships)
        participating_qualities = [quality]
        seen_other_ids: set[str] = set()
        for relationship in relationships:
            if relationship.relationship_type not in ("supports", "contradicts"):
                continue
            other_id = relationship.other_evidence_record_id
            if other_id in seen_other_ids or other_id == claim.evidence_record_id:
                continue
            seen_other_ids.add(other_id)
            other_evidence = read_evidence_record(evidence_path, other_id)
            if other_evidence is not None:
                participating_qualities.append(compute_evidence_quality(other_evidence))
        confidence = compute_claim_confidence(participating_qualities, consensus)

        reliability_counts[confidence.reliability] += 1
        if confidence.score is None:
            not_yet_assessable += 1

    mean_quality = sum(quality_scores) / len(quality_scores) if quality_scores else None

    return EvidenceIntelligenceDashboard(
        claims_total=len(claims),
        claims_with_evidence_configured=len(quality_scores),
        quality_bucket_counts={
            label: quality_buckets.get(label, 0) for label, _, _ in _QUALITY_BUCKETS
        },
        mean_quality_score=mean_quality,
        confidence_reliability_counts=dict(reliability_counts),
        not_yet_assessable_count=not_yet_assessable,
    )
