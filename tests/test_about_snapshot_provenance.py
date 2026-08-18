import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_engine_web.main import app


def test_about_page_exposes_complete_snapshot_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata_path = tmp_path / "snapshot_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-08-17T20:00:00Z",
                "corpus_id": "glp1_weight_loss",
                "core_commit": "a" * 40,
                "evidence_records_sha256": "sha256:" + "b" * 64,
                "relationship_records_sha256": "sha256:" + "c" * 64,
                "relationship_records_note": None,
                "claims_count": 154,
                "relationships_count": 32,
                "citations_count": 5,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("KE_WEB_SNAPSHOT_METADATA_PATH", str(metadata_path))

    response = TestClient(app).get("/about")

    assert response.status_code == 200
    assert 'id="snapshot"' in response.text
    assert "Core revision" in response.text
    assert "a" * 40 in response.text
    assert "sha256:" + "b" * 64 in response.text
    assert "sha256:" + "c" * 64 in response.text
    assert "provenance markers, not scientific quality scores" in response.text
