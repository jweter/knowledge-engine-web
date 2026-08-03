from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_engine_web.relationship_reader import (
    RelationshipRecordsError,
    list_relationship_records_for_evidence_record_id,
)


def _write_jsonl(path: Path, *records: dict[str, object]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def _record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": "0.1",
        "relationship_id": "rel-1",
        "source_evidence_record_id": "ev-1",
        "target_evidence_record_id": "ev-2",
        "relationship_type": "supports",
        "rationale": "Both trials report the same direction of effect.",
        "provenance": {"created_by": "manual review", "method": "reviewed both PICO fields"},
        "created_for_milestone": "M56",
    }
    base.update(overrides)
    return base


def test_returns_an_empty_list_when_the_file_does_not_exist(tmp_path: Path) -> None:
    path = tmp_path / "missing.jsonl"
    assert list_relationship_records_for_evidence_record_id(path, "ev-1") == []


def test_returns_an_empty_list_for_an_unmatched_id(tmp_path: Path) -> None:
    path = tmp_path / "relationship_records.jsonl"
    _write_jsonl(path, _record())

    assert list_relationship_records_for_evidence_record_id(path, "ev-does-not-exist") == []


def test_matches_when_the_id_is_the_source(tmp_path: Path) -> None:
    path = tmp_path / "relationship_records.jsonl"
    _write_jsonl(path, _record(source_evidence_record_id="ev-1", target_evidence_record_id="ev-2"))

    records = list_relationship_records_for_evidence_record_id(path, "ev-1")

    assert len(records) == 1
    assert records[0].relationship_id == "rel-1"
    assert records[0].source_evidence_record_id == "ev-1"
    assert records[0].target_evidence_record_id == "ev-2"


def test_matches_when_the_id_is_the_target(tmp_path: Path) -> None:
    path = tmp_path / "relationship_records.jsonl"
    _write_jsonl(path, _record(source_evidence_record_id="ev-1", target_evidence_record_id="ev-2"))

    records = list_relationship_records_for_evidence_record_id(path, "ev-2")

    assert len(records) == 1
    assert records[0].relationship_id == "rel-1"


def test_returns_the_records_display_fields(tmp_path: Path) -> None:
    path = tmp_path / "relationship_records.jsonl"
    _write_jsonl(path, _record())

    records = list_relationship_records_for_evidence_record_id(path, "ev-1")

    assert len(records) == 1
    record = records[0]
    assert record.relationship_type == "supports"
    assert record.rationale == "Both trials report the same direction of effect."
    assert record.provenance == {
        "created_by": "manual review",
        "method": "reviewed both PICO fields",
    }
    assert record.created_for_milestone == "M56"


def test_defaults_missing_provenance_to_an_empty_dict(tmp_path: Path) -> None:
    path = tmp_path / "relationship_records.jsonl"
    _write_jsonl(
        path,
        {
            "relationship_id": "rel-1",
            "source_evidence_record_id": "ev-1",
            "target_evidence_record_id": "ev-2",
            "relationship_type": "supports",
        },
    )

    records = list_relationship_records_for_evidence_record_id(path, "ev-1")

    assert records[0].provenance == {}
    assert records[0].created_for_milestone is None


def test_returns_every_matching_record(tmp_path: Path) -> None:
    path = tmp_path / "relationship_records.jsonl"
    _write_jsonl(
        path,
        _record(relationship_id="rel-1", source_evidence_record_id="ev-1"),
        _record(relationship_id="rel-2", target_evidence_record_id="ev-1"),
        _record(
            relationship_id="rel-3",
            source_evidence_record_id="ev-other",
            target_evidence_record_id="ev-another",
        ),
    )

    records = list_relationship_records_for_evidence_record_id(path, "ev-1")

    assert [record.relationship_id for record in records] == ["rel-1", "rel-2"]


def test_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "relationship_records.jsonl"
    path.write_text("\n" + json.dumps(_record()) + "\n\n", encoding="utf-8")

    records = list_relationship_records_for_evidence_record_id(path, "ev-1")

    assert len(records) == 1


def test_raises_on_a_malformed_json_line(tmp_path: Path) -> None:
    path = tmp_path / "relationship_records.jsonl"
    path.write_text("not json\n", encoding="utf-8")

    with pytest.raises(RelationshipRecordsError):
        list_relationship_records_for_evidence_record_id(path, "ev-1")
