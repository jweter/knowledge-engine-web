from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert

from knowledge_engine_web.main import app
from tests._fixtures import build_engine, create_graph_tables


def _database_url(tmp_path: Path, name: str = "fixture") -> str:
    return f"sqlite:///{tmp_path / name}.sqlite3"


def test_graph_page_renders_an_empty_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_engine(tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/graph")

    assert response.status_code == 200
    assert "Concepts: 0" in response.text
    assert "Claims: 0" in response.text


def test_graph_page_renders_populated_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_concepts"]),
            [{"id": 1, "label": "Semaglutide", "source": "rxnorm"}],
        )
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/graph")

    assert response.status_code == 200
    assert "Concepts: 1" in response.text
    assert "Claims: 1" in response.text
    assert "rxnorm: 1" in response.text


def test_graph_page_escapes_a_malicious_concept_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concept `source` value cannot inject HTML into the rendered page.

    Regression test mirroring `core`'s own Codex-caught Markdown-injection
    finding on `relationship-report`, redone for this project's actual
    HTML output -- Jinja2's autoescaping should already prevent this, but
    the guarantee is only real if a test actually exercises it.
    """

    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_concepts"]),
            [{"id": 1, "label": "Semaglutide", "source": "<script>alert(1)</script>"}],
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/graph")

    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text
