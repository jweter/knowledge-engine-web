from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import insert

from knowledge_engine_web.whats_changed import build_whats_changed_summary
from tests._fixtures import build_engine, create_graph_tables


def _write_evidence(path: Path, *records: dict[str, object]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_build_whats_changed_summary_splits_new_from_existing(tmp_path: Path) -> None:
    now = datetime(2026, 8, 3, tzinfo=UTC)
    old = (now - timedelta(days=30)).isoformat()
    recent = (now - timedelta(days=1)).isoformat()

    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]),
            [
                {"id": 1, "evidence_record_id": "ev-1", "created_at": old},
                {"id": 2, "evidence_record_id": "ev-2", "created_at": old},
                {"id": 3, "evidence_record_id": "ev-3", "created_at": recent},
            ],
        )
        connection.execute(
            insert(metadata.tables["graph_claim_relationships"]),
            [
                {
                    "id": 1,
                    "relationship_id": "rel-old",
                    "source_claim_id": 1,
                    "target_claim_id": 2,
                    "relationship_type": "supports",
                    "rationale": "Old edge.",
                    "created_at": old,
                },
                {
                    "id": 2,
                    "relationship_id": "rel-new",
                    "source_claim_id": 1,
                    "target_claim_id": 3,
                    "relationship_type": "supports",
                    "rationale": "New edge.",
                    "created_at": recent,
                },
            ],
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    _write_evidence(
        evidence_path,
        {
            "evidence_record_id": "ev-1",
            "study_type": "randomized_controlled_trial",
            "extraction_method": "manual_human_review",
            "review_checklist": {"source_verified": True},
            "limitations": ["A limitation."],
            "uncertainty_notes": "An uncertainty.",
        },
        {
            "evidence_record_id": "ev-2",
            "study_type": "randomized_controlled_trial",
            "extraction_method": "manual_human_review",
            "review_checklist": {"source_verified": True},
            "limitations": ["A limitation."],
            "uncertainty_notes": "An uncertainty.",
        },
        {
            "evidence_record_id": "ev-3",
            "study_type": "randomized_controlled_trial",
            "extraction_method": "m52-evidence-classification-v1",
            "review_checklist": {},
            "limitations": [],
            "uncertainty_notes": None,
        },
    )

    summary = build_whats_changed_summary(engine, evidence_path, window_days=7, now=now)

    assert summary.window_days == 7
    assert summary.evidence_configured is True
    # ev-1/ev-2 are older than the 7-day window; ev-3 and its edge are new.
    assert [claim.evidence_record_id for claim in summary.new_claims] == ["ev-3"]
    assert [edge.relationship_id for edge in summary.new_relationships] == ["rel-new"]
    assert summary.claims_total_before == 2
    assert summary.claims_total_after == 3
    # ev-3 is automated (lower rigor, no limitations/uncertainty bonus), so
    # adding it must pull the corpus-wide mean quality down, not up.
    assert summary.mean_quality_before is not None
    assert summary.mean_quality_after is not None
    assert summary.mean_quality_after < summary.mean_quality_before
    # Before the window: only ev-1/ev-2 existed, and rel-old already
    # connected both of them -- full coverage. After: ev-3 also touches an
    # edge (rel-new), so coverage is still full even though the
    # denominator grew.
    assert summary.coverage_before.total_records == 2
    assert summary.coverage_before.records_in_relationship == 2
    assert summary.coverage_after.total_records == 3
    assert summary.coverage_after.records_in_relationship == 3


def test_build_whats_changed_summary_without_evidence_path(tmp_path: Path) -> None:
    now = datetime(2026, 8, 3, tzinfo=UTC)
    recent = (now - timedelta(days=1)).isoformat()

    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]),
            [{"id": 1, "evidence_record_id": "ev-1", "created_at": recent}],
        )

    summary = build_whats_changed_summary(engine, None, window_days=7, now=now)

    assert summary.evidence_configured is False
    # New claims are a pure graph fact -- shown even without evidence configured.
    assert [claim.evidence_record_id for claim in summary.new_claims] == ["ev-1"]
    assert summary.mean_quality_before is None
    assert summary.mean_quality_after is None
    assert summary.coverage_after.total_records == 0


def test_build_whats_changed_summary_on_empty_graph(tmp_path: Path) -> None:
    now = datetime(2026, 8, 3, tzinfo=UTC)
    engine = build_engine(tmp_path)
    create_graph_tables(engine)
    evidence_path = tmp_path / "evidence_records.jsonl"

    summary = build_whats_changed_summary(engine, evidence_path, window_days=7, now=now)

    assert summary.new_claims == []
    assert summary.new_relationships == []
    assert summary.claims_total_before == 0
    assert summary.claims_total_after == 0
