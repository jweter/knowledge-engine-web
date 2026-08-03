""" "What changed" report: new claims, new relationship edges, and aggregate deltas.

`docs/roadmap.md`'s "Planned: Reviewer & Evidence Intelligence Tooling"
section names this as the third item: "a recurring status report (new
claims, new relationship edges, Evidence Quality/Coverage deltas between
two points in time)."

This project has no persistent host and no stored historical snapshots
to diff against (see `docs/service_boundary_design.md`) -- but `core`'s
graph rows already carry their own `created_at` timestamp, so a real,
computable "before" state can be reconstructed from a single live query
by filtering on that timestamp, with no new storage. "Before" means "as
of `window_days` ago"; "after" means "right now." Both ends are real
values read from the graph, never estimated or interpolated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine

from knowledge_engine_web.evidence_intelligence import (
    EvidenceCoverage,
    compute_evidence_coverage,
    compute_evidence_quality,
)
from knowledge_engine_web.evidence_reader import read_evidence_record
from knowledge_engine_web.graph_reader import (
    ClaimListItem,
    RelationshipListItem,
    list_claims,
    list_relationships,
)

WHATS_CHANGED_WINDOW_DAYS = 7


@dataclass(frozen=True)
class WhatsChangedSummary:
    """New graph activity and aggregate deltas over the last `window_days`."""

    window_days: int
    since: str
    generated_at: str
    new_claims: list[ClaimListItem]
    new_relationships: list[RelationshipListItem]
    evidence_configured: bool
    claims_total_before: int
    claims_total_after: int
    mean_quality_before: float | None
    mean_quality_after: float | None
    coverage_before: EvidenceCoverage
    coverage_after: EvidenceCoverage


def build_whats_changed_summary(
    engine: Engine,
    evidence_path: Path | None,
    *,
    window_days: int = WHATS_CHANGED_WINDOW_DAYS,
    now: datetime | None = None,
) -> WhatsChangedSummary:
    """Build the "what changed" summary over the last `window_days`.

    New claims and new relationship edges are pure graph facts, shown
    regardless of `evidence_path`. The aggregate Evidence Quality/Coverage
    deltas need evidence-record content the same way every other Evidence
    Intelligence surface does -- when `evidence_path` is `None`,
    `evidence_configured` is `False` and both deltas are empty rather than
    guessed. `coverage_before`/`coverage_after` reuse `dashboard.py`'s
    corpus-wide denominator (claims present in the graph with evidence
    configured), not the single-claim page's evidence-file-wide one --
    the right comparison for a corpus-wide report, same reasoning as
    `dashboard.py`'s own docstring.
    """

    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(days=window_days)).isoformat()

    claims = list_claims(engine)
    relationships = list_relationships(engine)

    new_claims = [claim for claim in claims if claim.created_at >= cutoff]
    new_relationships = [edge for edge in relationships if edge.created_at >= cutoff]
    claims_total_before = sum(1 for claim in claims if claim.created_at < cutoff)

    if evidence_path is None:
        empty_coverage = compute_evidence_coverage(total_records=0, records_in_relationship=0)
        return WhatsChangedSummary(
            window_days=window_days,
            since=cutoff,
            generated_at=now.isoformat(),
            new_claims=new_claims,
            new_relationships=new_relationships,
            evidence_configured=False,
            claims_total_before=claims_total_before,
            claims_total_after=len(claims),
            mean_quality_before=None,
            mean_quality_after=None,
            coverage_before=empty_coverage,
            coverage_after=empty_coverage,
        )

    touched_all: set[str] = set()
    touched_before: set[str] = set()
    for edge in relationships:
        touched_all.add(edge.source_evidence_record_id)
        touched_all.add(edge.target_evidence_record_id)
        if edge.created_at < cutoff:
            touched_before.add(edge.source_evidence_record_id)
            touched_before.add(edge.target_evidence_record_id)

    quality_scores_after: list[int] = []
    quality_scores_before: list[int] = []
    configured_after = 0
    covered_after = 0
    configured_before = 0
    covered_before = 0

    for claim in claims:
        evidence = read_evidence_record(evidence_path, claim.evidence_record_id)
        if evidence is None:
            continue
        quality = compute_evidence_quality(evidence)

        configured_after += 1
        quality_scores_after.append(quality.score)
        if claim.evidence_record_id in touched_all:
            covered_after += 1

        if claim.created_at < cutoff:
            configured_before += 1
            quality_scores_before.append(quality.score)
            if claim.evidence_record_id in touched_before:
                covered_before += 1

    mean_after = (
        sum(quality_scores_after) / len(quality_scores_after) if quality_scores_after else None
    )
    mean_before = (
        sum(quality_scores_before) / len(quality_scores_before) if quality_scores_before else None
    )

    return WhatsChangedSummary(
        window_days=window_days,
        since=cutoff,
        generated_at=now.isoformat(),
        new_claims=new_claims,
        new_relationships=new_relationships,
        evidence_configured=True,
        claims_total_before=claims_total_before,
        claims_total_after=len(claims),
        mean_quality_before=mean_before,
        mean_quality_after=mean_after,
        coverage_before=compute_evidence_coverage(
            total_records=configured_before, records_in_relationship=covered_before
        ),
        coverage_after=compute_evidence_coverage(
            total_records=configured_after, records_in_relationship=covered_after
        ),
    )
