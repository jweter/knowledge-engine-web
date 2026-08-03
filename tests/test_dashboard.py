from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import insert

from knowledge_engine_web.dashboard import build_evidence_intelligence_dashboard
from tests._fixtures import build_engine, create_graph_tables


def _write_evidence(path: Path, *records: dict[str, object]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def _evidence_record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "study_type": "randomized_controlled_trial",
        "extraction_method": "manual_human_review",
        "review_status": "reviewed",
        "review_checklist": {"source_verified": True},
        "limitations": ["A limitation."],
        "uncertainty_notes": "An uncertainty.",
    }
    base.update(overrides)
    return base


def test_returns_zero_claims_for_an_empty_graph(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    create_graph_tables(engine)
    evidence_path = tmp_path / "evidence_records.jsonl"

    summary = build_evidence_intelligence_dashboard(engine, evidence_path)

    assert summary.claims_total == 0
    assert summary.claims_with_evidence_configured == 0
    assert summary.mean_quality_score is None


def test_skips_claims_with_no_evidence_record_on_file(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    evidence_path = tmp_path / "evidence_records.jsonl"

    summary = build_evidence_intelligence_dashboard(engine, evidence_path)

    assert summary.claims_total == 1
    assert summary.claims_with_evidence_configured == 0


def test_aggregates_quality_and_confidence_across_configured_claims(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]),
            [
                {"id": 1, "evidence_record_id": "ev-1"},
                {"id": 2, "evidence_record_id": "ev-2"},
                {"id": 3, "evidence_record_id": "ev-3"},
            ],
        )
        connection.execute(
            insert(metadata.tables["graph_claim_relationships"]),
            [
                {
                    "id": 1,
                    "relationship_id": "rel-1",
                    "source_claim_id": 1,
                    "target_claim_id": 2,
                    "relationship_type": "supports",
                    "rationale": "Because.",
                },
                {
                    "id": 2,
                    "relationship_id": "rel-2",
                    "source_claim_id": 1,
                    "target_claim_id": 3,
                    "relationship_type": "supports",
                    "rationale": "Also because.",
                },
            ],
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    _write_evidence(
        evidence_path,
        _evidence_record(evidence_record_id="ev-1"),
        _evidence_record(evidence_record_id="ev-2"),
    )

    summary = build_evidence_intelligence_dashboard(engine, evidence_path)

    assert summary.claims_total == 3
    # claim 3 has no evidence-record content configured, so it is skipped
    # entirely and never contributes to any aggregate below.
    assert summary.claims_with_evidence_configured == 2
    assert summary.mean_quality_score is not None
    assert sum(summary.quality_bucket_counts.values()) == 2
    assert sum(summary.confidence_reliability_counts.values()) == 2
    # claim 1 has two relationship edges (enough for a real Claim
    # Confidence score); claim 2 has only one (still "insufficient").
    assert summary.not_yet_assessable_count == 1


def test_unconnected_claim_counts_as_not_yet_assessable(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    _write_evidence(evidence_path, _evidence_record(evidence_record_id="ev-1"))

    summary = build_evidence_intelligence_dashboard(engine, evidence_path)

    assert summary.claims_with_evidence_configured == 1
    assert summary.not_yet_assessable_count == 1
