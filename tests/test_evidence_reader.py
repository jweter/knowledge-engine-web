from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_engine_web.evidence_reader import (
    EvidenceRecordsError,
    count_evidence_records,
    list_evidence_records_for_doi,
    read_evidence_record,
)


def _write_jsonl(path: Path, *records: dict[str, object]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_read_evidence_record_returns_none_when_the_file_does_not_exist(tmp_path: Path) -> None:
    assert read_evidence_record(tmp_path / "missing.jsonl", "ev-1") is None


def test_read_evidence_record_returns_none_for_an_unmatched_id(tmp_path: Path) -> None:
    path = tmp_path / "evidence_records.jsonl"
    _write_jsonl(path, {"evidence_record_id": "ev-1", "claim_text": "Some claim."})

    assert read_evidence_record(path, "ev-does-not-exist") is None


def test_read_evidence_record_returns_the_matching_records_fields(tmp_path: Path) -> None:
    path = tmp_path / "evidence_records.jsonl"
    _write_jsonl(
        path,
        {"evidence_record_id": "ev-other", "claim_text": "Not this one."},
        {
            "evidence_record_id": "ev-1",
            "research_question": "Does X reduce Y?",
            "claim_text": "X reduces Y.",
            "evidence_direction": "supports",
            "study_type": "randomized_controlled_trial",
            "source_type": "paper",
            "source_title": "A Trial of X",
            "source_doi": "10.1000/example",
            "population": "Adults with Y.",
            "intervention": "X, once weekly.",
            "comparator": "Placebo.",
            "outcome": "Change in Y.",
            "result_summary": "X reduced Y by 10% versus placebo.",
            "short_source_excerpt": "Y was reduced by 10%.",
            "limitations": ["Single trial.", "Short follow-up."],
            "uncertainty_notes": "Needs replication.",
            "confidence_note": "High confidence the extraction is accurate.",
            "extraction_method": "manual_human_review",
            "extraction_status": "draft_manual_prototype",
            "review_status": "draft",
        },
    )

    detail = read_evidence_record(path, "ev-1")

    assert detail is not None
    assert detail.evidence_record_id == "ev-1"
    assert detail.research_question == "Does X reduce Y?"
    assert detail.claim_text == "X reduces Y."
    assert detail.evidence_direction == "supports"
    assert detail.result_summary == "X reduced Y by 10% versus placebo."
    assert detail.limitations == ["Single trial.", "Short follow-up."]
    assert detail.confidence_note == "High confidence the extraction is accurate."


def test_read_evidence_record_defaults_missing_optional_fields(tmp_path: Path) -> None:
    path = tmp_path / "evidence_records.jsonl"
    _write_jsonl(path, {"evidence_record_id": "ev-1"})

    detail = read_evidence_record(path, "ev-1")

    assert detail is not None
    assert detail.claim_text is None
    assert detail.limitations == []


def test_read_evidence_record_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "evidence_records.jsonl"
    path.write_text(
        '\n{"evidence_record_id": "ev-1", "claim_text": "X."}\n\n',
        encoding="utf-8",
    )

    detail = read_evidence_record(path, "ev-1")

    assert detail is not None
    assert detail.claim_text == "X."


def test_read_evidence_record_raises_on_a_malformed_json_line(tmp_path: Path) -> None:
    path = tmp_path / "evidence_records.jsonl"
    path.write_text("not json\n", encoding="utf-8")

    with pytest.raises(EvidenceRecordsError):
        read_evidence_record(path, "ev-1")


def test_read_evidence_record_captures_review_checklist(tmp_path: Path) -> None:
    path = tmp_path / "evidence_records.jsonl"
    _write_jsonl(
        path,
        {
            "evidence_record_id": "ev-1",
            "review_checklist": {"source_verified": True, "doi_verified": True},
        },
    )

    detail = read_evidence_record(path, "ev-1")

    assert detail is not None
    assert detail.review_checklist == {"source_verified": True, "doi_verified": True}


def test_read_evidence_record_defaults_missing_review_checklist(tmp_path: Path) -> None:
    path = tmp_path / "evidence_records.jsonl"
    _write_jsonl(path, {"evidence_record_id": "ev-1"})

    detail = read_evidence_record(path, "ev-1")

    assert detail is not None
    assert detail.review_checklist == {}


def test_count_evidence_records_returns_zero_when_the_file_does_not_exist(tmp_path: Path) -> None:
    assert count_evidence_records(tmp_path / "missing.jsonl") == 0


def test_count_evidence_records_counts_non_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "evidence_records.jsonl"
    _write_jsonl(
        path,
        {"evidence_record_id": "ev-1"},
        {"evidence_record_id": "ev-2"},
        {"evidence_record_id": "ev-3"},
    )

    assert count_evidence_records(path) == 3


def test_list_evidence_records_for_doi_returns_an_empty_list_when_the_file_does_not_exist(
    tmp_path: Path,
) -> None:
    assert list_evidence_records_for_doi(tmp_path / "missing.jsonl", "10.1000/example") == []


def test_list_evidence_records_for_doi_returns_an_empty_list_for_an_unmatched_doi(
    tmp_path: Path,
) -> None:
    path = tmp_path / "evidence_records.jsonl"
    _write_jsonl(path, {"evidence_record_id": "ev-1", "source_doi": "10.1000/other"})

    assert list_evidence_records_for_doi(path, "10.1000/example") == []


def test_list_evidence_records_for_doi_returns_every_matching_record(tmp_path: Path) -> None:
    path = tmp_path / "evidence_records.jsonl"
    _write_jsonl(
        path,
        {"evidence_record_id": "ev-1", "source_doi": "10.1000/example", "claim_text": "First."},
        {"evidence_record_id": "ev-2", "source_doi": "10.1000/other", "claim_text": "Unrelated."},
        {"evidence_record_id": "ev-3", "source_doi": "10.1000/example", "claim_text": "Second."},
    )

    records = list_evidence_records_for_doi(path, "10.1000/example")

    assert [record.evidence_record_id for record in records] == ["ev-1", "ev-3"]


def test_list_evidence_records_for_doi_normalizes_the_doi_before_comparing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "evidence_records.jsonl"
    _write_jsonl(
        path,
        {"evidence_record_id": "ev-1", "source_doi": "https://doi.org/10.1000/EXAMPLE"},
    )

    records = list_evidence_records_for_doi(path, "10.1000/example")

    assert [record.evidence_record_id for record in records] == ["ev-1"]


def test_list_evidence_records_for_doi_raises_on_a_malformed_json_line(tmp_path: Path) -> None:
    path = tmp_path / "evidence_records.jsonl"
    path.write_text("not json\n", encoding="utf-8")

    with pytest.raises(EvidenceRecordsError):
        list_evidence_records_for_doi(path, "10.1000/example")
