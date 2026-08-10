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
from knowledge_engine_web.evidence_reader import index_evidence_records_by_id
from knowledge_engine_web.graph_reader import list_claims, list_relationships


@dataclass(frozen=True)
class _TouchingRelationship:
    """The two fields this module's per-claim consensus loop actually reads off an edge."""

    relationship_type: str
    other_evidence_record_id: str


def _index_relationships_by_evidence_record_id(
    engine: Engine,
) -> dict[str, list[_TouchingRelationship]]:
    """Read every relationship edge once and group it by each side's `evidence_record_id`.

    `read_claim_detail` (single-claim pages) re-reflects the graph tables
    and re-queries per call -- correct for one claim, but calling it once
    per claim in a corpus-wide loop measurably hangs once the corpus
    grows past a single-corpus scale (see `docs/deployment.md`'s
    multi-corpus merge): `_reflect_graph_tables` alone does real SQLite
    schema-introspection queries, and doing that thousands of times
    dominates the whole request. `list_relationships` already reads
    every edge in one bulk pass for exactly this reason (its own
    docstring names `whats_changed.py` as the original motivating
    caller); this indexes that same bulk read for both sides of each
    edge instead of adding a second per-claim query path.
    """

    by_id: dict[str, list[_TouchingRelationship]] = {}
    for edge in list_relationships(engine):
        by_id.setdefault(edge.source_evidence_record_id, []).append(
            _TouchingRelationship(edge.relationship_type, edge.target_evidence_record_id)
        )
        by_id.setdefault(edge.target_evidence_record_id, []).append(
            _TouchingRelationship(edge.relationship_type, edge.source_evidence_record_id)
        )
    return by_id


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

    Reads `evidence_path` once into an ID-keyed index rather than calling
    `read_evidence_record` per claim, and reads the graph's relationship
    edges once via `list_relationships` rather than calling
    `read_claim_detail` per claim -- with every claim in the graph
    visited here, either per-claim call turns an O(records)/O(edges)
    read into an O(claims * records)/O(claims * edges) one, which
    measurably hangs once the corpus grows past a single-corpus scale
    (see `docs/deployment.md`'s multi-corpus merge). See
    `evidence_reader.index_evidence_records_by_id` and
    `_index_relationships_by_evidence_record_id` above.
    """

    claims = list_claims(engine)
    evidence_by_id = index_evidence_records_by_id(evidence_path)
    relationships_by_id = _index_relationships_by_evidence_record_id(engine)
    quality_scores: list[int] = []
    quality_buckets: Counter[str] = Counter()
    reliability_counts: Counter[str] = Counter()
    not_yet_assessable = 0

    for claim in claims:
        evidence = evidence_by_id.get(claim.evidence_record_id)
        if evidence is None:
            continue

        relationships = relationships_by_id.get(claim.evidence_record_id, [])

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
            other_evidence = evidence_by_id.get(other_id)
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
