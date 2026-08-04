import json
from pathlib import Path

from knowledge_engine_web.snapshot_metadata import read_snapshot_metadata


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": "2026-08-03T17:10:12Z",
        "corpus_id": "glp1_weight_loss",
        "core_commit": "a" * 40,
        "evidence_records_sha256": f"sha256:{'b' * 64}",
        "relationship_records_sha256": None,
        "relationship_records_note": "Not included.",
        "claims_count": 154,
        "relationships_count": 11,
        "citations_count": 5,
    }


def test_read_snapshot_metadata_accepts_version_one(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    result = read_snapshot_metadata(path)

    assert result.unavailable_reason is None
    assert result.metadata is not None
    assert result.metadata.corpus_id == "glp1_weight_loss"
    assert result.metadata.claims_count == 154


def test_read_snapshot_metadata_rejects_boolean_version(tmp_path: Path) -> None:
    payload = _payload()
    payload["schema_version"] = True
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = read_snapshot_metadata(path)

    assert result.metadata is None
    assert result.unavailable_reason == "Snapshot metadata is unavailable or invalid."


def test_read_snapshot_metadata_reports_missing_file_without_path(
    tmp_path: Path,
) -> None:
    result = read_snapshot_metadata(tmp_path / "private" / "snapshot.json")

    assert result.metadata is None
    assert result.unavailable_reason == "Snapshot metadata is not available."
