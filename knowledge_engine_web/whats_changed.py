""" "What changed" report: new claims, new relationship edges, and aggregate deltas.

`docs/roadmap.md`'s "Planned: Reviewer & Evidence Intelligence Tooling"
section names this as the third item: "a recurring status report (new
claims, new relationship edges, Evidence Quality/Coverage deltas between
two points in time)."

**Revised (Codex review on PR #23):** the first version reconstructed
"before" from each graph row's own `created_at` timestamp. That is
unreliable for the one deployment that actually serves this report:
`core`'s working SQLite database is gitignored and rebuilt from scratch
every session (this project has no persistent host --
`docs/service_boundary_design.md`), so `GraphRepository.get_or_create_claim`
only preserves `created_at` across repeated calls *within one already-
populated database*. Every alpha-snapshot refresh restarts from an empty
database, so every claim and edge gets a fresh `created_at` on every
refresh regardless of true age -- the report would describe "graph
rebuild activity," never real corpus growth. Neither `EvidenceRecord`
nor `RelationshipRecord` carries its own authored/promoted timestamp to
fall back on either.

This version instead diffs the live graph against a small saved
baseline (`WhatsChangedBaseline`, written as JSON), captured from the
about-to-be-replaced snapshot at the start of each alpha refresh
(`scripts/capture_whats_changed_baseline.py`, called from
`scripts/refresh-alpha-snapshot.sh` before the new DB overwrites the
old one). This is not new speculative infrastructure -- it is one more
small file alongside the already-committed, already-refreshed
point-in-time DB snapshot, following the same pattern
`docs/deployment.md`'s "Alpha hosting (Render)" section already
established. "Before" is exactly what the baseline recorded; "after" is
read live, same as before. No baseline yet (a fresh deployment that
hasn't been through a refresh cycle since this report shipped) is a
real, honest state -- shown as such, never guessed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine

from knowledge_engine_web.evidence_intelligence import (
    EvidenceCoverage,
    compute_evidence_coverage,
    compute_evidence_quality,
)
from knowledge_engine_web.evidence_reader import index_evidence_records_by_id
from knowledge_engine_web.graph_reader import (
    ClaimListItem,
    RelationshipListItem,
    list_claims,
    list_relationships,
)

BASELINE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class WhatsChangedBaseline:
    """A saved point-in-time snapshot of graph/evidence state to diff future state against."""

    schema_version: int
    captured_at: str
    claim_evidence_record_ids: list[str]
    relationship_ids: list[str]
    claims_with_evidence_configured: int
    mean_quality_score: float | None
    coverage_records_in_relationship: int
    coverage_total_records: int


def build_whats_changed_baseline(
    engine: Engine, evidence_path: Path, *, now: datetime | None = None
) -> WhatsChangedBaseline:
    """Capture the current graph/evidence state as a baseline for a future diff.

    Mirrors `dashboard.py`'s aggregation (same `compute_evidence_quality`,
    same "touches any relationship edge" coverage definition) -- no new
    computation, just captured for later comparison instead of only
    aggregated in place. Also mirrors `dashboard.py`'s "index the
    evidence file once" fix: a per-claim `read_evidence_record` call
    rescans the whole file from disk, so looping it over every claim in
    the graph turns an O(records) file into an O(claims * records) read
    pattern -- see `evidence_reader.index_evidence_records_by_id`.
    """

    now = now or datetime.now(UTC)
    claims = list_claims(engine)
    relationships = list_relationships(engine)
    evidence_by_id = index_evidence_records_by_id(evidence_path)

    touched: set[str] = set()
    for edge in relationships:
        touched.add(edge.source_evidence_record_id)
        touched.add(edge.target_evidence_record_id)

    quality_scores: list[int] = []
    configured = 0
    covered = 0
    for claim in claims:
        evidence = evidence_by_id.get(claim.evidence_record_id)
        if evidence is None:
            continue
        quality = compute_evidence_quality(evidence)
        configured += 1
        quality_scores.append(quality.score)
        if claim.evidence_record_id in touched:
            covered += 1

    mean_quality = sum(quality_scores) / len(quality_scores) if quality_scores else None

    return WhatsChangedBaseline(
        schema_version=BASELINE_SCHEMA_VERSION,
        captured_at=now.isoformat(),
        claim_evidence_record_ids=sorted(claim.evidence_record_id for claim in claims),
        relationship_ids=sorted(edge.relationship_id for edge in relationships),
        claims_with_evidence_configured=configured,
        mean_quality_score=mean_quality,
        coverage_records_in_relationship=covered,
        coverage_total_records=configured,
    )


def write_baseline_json(baseline: WhatsChangedBaseline, path: Path) -> None:
    """Write a baseline to disk as sorted, stable JSON -- diffable in a real code review."""

    path.write_text(json.dumps(asdict(baseline), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_baseline_json(path: Path) -> WhatsChangedBaseline | None:
    """Read a saved baseline, or `None` if none captured yet -- a real state, not an error."""

    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return WhatsChangedBaseline(**data)


@dataclass(frozen=True)
class WhatsChangedSummary:
    """New graph activity and aggregate deltas since the last captured baseline."""

    baseline_captured_at: str | None
    new_claims: list[ClaimListItem]
    new_relationships: list[RelationshipListItem]
    evidence_configured: bool
    claims_total_before: int | None
    claims_total_after: int
    mean_quality_before: float | None
    mean_quality_after: float | None
    coverage_before: EvidenceCoverage | None
    coverage_after: EvidenceCoverage | None


def build_whats_changed_summary(
    engine: Engine, evidence_path: Path | None, baseline_path: Path
) -> WhatsChangedSummary:
    """Diff the live graph against the saved baseline at `baseline_path`.

    New claims and new relationship edges are pure graph facts, shown
    regardless of `evidence_path`. The aggregate Evidence Quality/Coverage
    deltas need evidence-record content the same way every other Evidence
    Intelligence surface does -- when `evidence_path` is `None`,
    `evidence_configured` is `False` and both deltas are empty rather than
    guessed.
    """

    claims = list_claims(engine)
    relationships = list_relationships(engine)
    baseline = read_baseline_json(baseline_path)

    if baseline is None:
        new_claims: list[ClaimListItem] = []
        new_relationships: list[RelationshipListItem] = []
        claims_total_before = None
    else:
        baseline_claim_ids = set(baseline.claim_evidence_record_ids)
        baseline_relationship_ids = set(baseline.relationship_ids)
        new_claims = [
            claim for claim in claims if claim.evidence_record_id not in baseline_claim_ids
        ]
        new_relationships = [
            edge for edge in relationships if edge.relationship_id not in baseline_relationship_ids
        ]
        claims_total_before = len(baseline.claim_evidence_record_ids)

    if evidence_path is None:
        return WhatsChangedSummary(
            baseline_captured_at=baseline.captured_at if baseline else None,
            new_claims=new_claims,
            new_relationships=new_relationships,
            evidence_configured=False,
            claims_total_before=claims_total_before,
            claims_total_after=len(claims),
            mean_quality_before=None,
            mean_quality_after=None,
            coverage_before=None,
            coverage_after=None,
        )

    touched_all: set[str] = set()
    for edge in relationships:
        touched_all.add(edge.source_evidence_record_id)
        touched_all.add(edge.target_evidence_record_id)

    evidence_by_id = index_evidence_records_by_id(evidence_path)
    quality_scores_after: list[int] = []
    configured_after = 0
    covered_after = 0
    for claim in claims:
        evidence = evidence_by_id.get(claim.evidence_record_id)
        if evidence is None:
            continue
        quality = compute_evidence_quality(evidence)
        configured_after += 1
        quality_scores_after.append(quality.score)
        if claim.evidence_record_id in touched_all:
            covered_after += 1

    mean_after = (
        sum(quality_scores_after) / len(quality_scores_after) if quality_scores_after else None
    )

    return WhatsChangedSummary(
        baseline_captured_at=baseline.captured_at if baseline else None,
        new_claims=new_claims,
        new_relationships=new_relationships,
        evidence_configured=True,
        claims_total_before=claims_total_before,
        claims_total_after=len(claims),
        mean_quality_before=baseline.mean_quality_score if baseline else None,
        mean_quality_after=mean_after,
        coverage_before=(
            compute_evidence_coverage(
                total_records=baseline.coverage_total_records,
                records_in_relationship=baseline.coverage_records_in_relationship,
            )
            if baseline is not None
            else None
        ),
        coverage_after=compute_evidence_coverage(
            total_records=configured_after, records_in_relationship=covered_after
        ),
    )
