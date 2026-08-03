from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert

from knowledge_engine_web.whats_changed import (
    WhatsChangedBaseline,
    build_whats_changed_baseline,
    build_whats_changed_summary,
    read_baseline_json,
    write_baseline_json,
)
from tests._fixtures import build_engine, create_graph_tables


def _write_evidence(path: Path, *records: dict[str, object]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def _evidence_record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "study_type": "randomized_controlled_trial",
        "extraction_method": "manual_human_review",
        "review_checklist": {"source_verified": True},
        "limitations": ["A limitation."],
        "uncertainty_notes": "An uncertainty.",
    }
    base.update(overrides)
    return base


def test_build_whats_changed_baseline_captures_ids_and_aggregate_state(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]),
            [
                {"id": 1, "evidence_record_id": "ev-1"},
                {"id": 2, "evidence_record_id": "ev-2"},
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
                }
            ],
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    _write_evidence(
        evidence_path,
        _evidence_record(evidence_record_id="ev-1"),
        _evidence_record(evidence_record_id="ev-2"),
    )
    now = datetime(2026, 8, 3, tzinfo=UTC)

    baseline = build_whats_changed_baseline(engine, evidence_path, now=now)

    assert baseline.captured_at == now.isoformat()
    assert baseline.claim_evidence_record_ids == ["ev-1", "ev-2"]
    assert baseline.relationship_ids == ["rel-1"]
    assert baseline.claims_with_evidence_configured == 2
    assert baseline.mean_quality_score is not None
    assert baseline.coverage_records_in_relationship == 2
    assert baseline.coverage_total_records == 2


def test_baseline_json_round_trips(tmp_path: Path) -> None:
    baseline = WhatsChangedBaseline(
        schema_version=1,
        captured_at="2026-08-01T00:00:00+00:00",
        claim_evidence_record_ids=["ev-1"],
        relationship_ids=["rel-1"],
        claims_with_evidence_configured=1,
        mean_quality_score=80.0,
        coverage_records_in_relationship=1,
        coverage_total_records=1,
    )
    path = tmp_path / "whats_changed_baseline.json"

    write_baseline_json(baseline, path)
    loaded = read_baseline_json(path)

    assert loaded == baseline


def test_read_baseline_json_returns_none_when_not_captured_yet(tmp_path: Path) -> None:
    assert read_baseline_json(tmp_path / "does-not-exist.json") is None


def test_build_whats_changed_summary_diffs_against_baseline(tmp_path: Path) -> None:
    baseline = WhatsChangedBaseline(
        schema_version=1,
        captured_at="2026-08-01T00:00:00+00:00",
        claim_evidence_record_ids=["ev-1", "ev-2"],
        relationship_ids=["rel-old"],
        claims_with_evidence_configured=2,
        mean_quality_score=94.0,
        coverage_records_in_relationship=2,
        coverage_total_records=2,
    )
    baseline_path = tmp_path / "baseline.json"
    write_baseline_json(baseline, baseline_path)

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
                    "relationship_id": "rel-old",
                    "source_claim_id": 1,
                    "target_claim_id": 2,
                    "relationship_type": "supports",
                    "rationale": "Old edge.",
                },
                {
                    "id": 2,
                    "relationship_id": "rel-new",
                    "source_claim_id": 1,
                    "target_claim_id": 3,
                    "relationship_type": "supports",
                    "rationale": "New edge.",
                },
            ],
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    _write_evidence(
        evidence_path,
        _evidence_record(evidence_record_id="ev-1"),
        _evidence_record(evidence_record_id="ev-2"),
        _evidence_record(
            evidence_record_id="ev-3",
            extraction_method="m52-evidence-classification-v1",
            review_checklist={},
            limitations=[],
            uncertainty_notes=None,
        ),
    )

    summary = build_whats_changed_summary(engine, evidence_path, baseline_path)

    assert summary.baseline_captured_at == "2026-08-01T00:00:00+00:00"
    # ev-1/ev-2/rel-old were already in the baseline; ev-3 and rel-new are new.
    assert [claim.evidence_record_id for claim in summary.new_claims] == ["ev-3"]
    assert [edge.relationship_id for edge in summary.new_relationships] == ["rel-new"]
    assert summary.claims_total_before == 2
    assert summary.claims_total_after == 3
    assert summary.mean_quality_before == 94.0
    # ev-3 is automated (lower rigor, no limitations/uncertainty bonus), so
    # adding it must pull the corpus-wide mean quality down.
    assert summary.mean_quality_after is not None
    assert summary.mean_quality_after < summary.mean_quality_before
    assert summary.coverage_before is not None
    assert summary.coverage_before.total_records == 2
    assert summary.coverage_before.records_in_relationship == 2
    assert summary.coverage_after is not None
    assert summary.coverage_after.total_records == 3
    assert summary.coverage_after.records_in_relationship == 3


def test_build_whats_changed_summary_with_no_baseline_yet(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    _write_evidence(evidence_path, _evidence_record(evidence_record_id="ev-1"))
    baseline_path = tmp_path / "does-not-exist-yet.json"

    summary = build_whats_changed_summary(engine, evidence_path, baseline_path)

    assert summary.baseline_captured_at is None
    # No baseline to diff against -- nothing is claimed "new" rather than
    # guessing everything currently in the graph is recent.
    assert summary.new_claims == []
    assert summary.new_relationships == []
    assert summary.claims_total_before is None
    assert summary.claims_total_after == 1
    assert summary.mean_quality_before is None
    assert summary.coverage_before is None


def test_build_whats_changed_summary_without_evidence_path(tmp_path: Path) -> None:
    baseline = WhatsChangedBaseline(
        schema_version=1,
        captured_at="2026-08-01T00:00:00+00:00",
        claim_evidence_record_ids=[],
        relationship_ids=[],
        claims_with_evidence_configured=0,
        mean_quality_score=None,
        coverage_records_in_relationship=0,
        coverage_total_records=0,
    )
    baseline_path = tmp_path / "baseline.json"
    write_baseline_json(baseline, baseline_path)

    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )

    summary = build_whats_changed_summary(engine, None, baseline_path)

    assert summary.evidence_configured is False
    # New claims are a pure graph fact -- shown even without evidence configured.
    assert [claim.evidence_record_id for claim in summary.new_claims] == ["ev-1"]
    assert summary.mean_quality_before is None
    assert summary.mean_quality_after is None
    assert summary.coverage_before is None
    assert summary.coverage_after is None
