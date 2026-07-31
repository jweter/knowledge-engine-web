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


def test_claims_list_page_renders_no_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_engine(tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/claims")

    assert response.status_code == 200
    assert "No claims in the graph yet." in response.text


def test_claims_list_page_links_to_each_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/claims")

    assert response.status_code == 200
    assert '<a href="/claims/ev-1">ev-1</a>' in response.text


def test_claim_detail_page_renders_concepts_and_relationships(
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
            insert(metadata.tables["graph_claims"]),
            [
                {"id": 1, "evidence_record_id": "ev-1"},
                {"id": 2, "evidence_record_id": "ev-2"},
            ],
        )
        connection.execute(
            insert(metadata.tables["graph_claim_concepts"]),
            [{"id": 1, "claim_id": 1, "concept_id": 1, "edge_role": "intervention"}],
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
                    "rationale": "Both report the same direction.",
                }
            ],
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/claims/ev-1")

    assert response.status_code == 200
    assert "intervention" in response.text
    assert "Semaglutide" in response.text
    assert "supports" in response.text
    assert "ev-2" in response.text


def test_claim_detail_page_404s_for_an_unknown_evidence_record_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    create_graph_tables(engine)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/claims/ev-does-not-exist")

    assert response.status_code == 404


def test_unconfirmed_claims_page_excludes_a_claim_with_a_relationship_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]),
            [
                {"id": 1, "evidence_record_id": "ev-confirmed-source"},
                {"id": 2, "evidence_record_id": "ev-confirmed-target"},
                {"id": 3, "evidence_record_id": "ev-unconfirmed"},
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
                    "rationale": "Both report the same direction.",
                }
            ],
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/unconfirmed-claims")

    assert response.status_code == 200
    assert "ev-unconfirmed" in response.text
    assert "ev-confirmed-source" not in response.text
    assert "ev-confirmed-target" not in response.text


def test_unconfirmed_claims_page_renders_when_every_claim_is_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_engine(tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/unconfirmed-claims")

    assert response.status_code == 200
    assert "Every claim in the graph has at least one relationship edge." in response.text


def test_relationship_candidates_page_lists_a_shared_concept_pair(
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
            insert(metadata.tables["graph_claims"]),
            [
                {"id": 1, "evidence_record_id": "ev-a"},
                {"id": 2, "evidence_record_id": "ev-b"},
            ],
        )
        connection.execute(
            insert(metadata.tables["graph_claim_concepts"]),
            [
                {"id": 1, "claim_id": 1, "concept_id": 1, "edge_role": "intervention"},
                {"id": 2, "claim_id": 2, "concept_id": 1, "edge_role": "intervention"},
            ],
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/relationship-candidates")

    assert response.status_code == 200
    assert "ev-a" in response.text
    assert "ev-b" in response.text
    assert "Semaglutide" in response.text


def test_relationship_candidates_page_renders_no_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_engine(tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/relationship-candidates")

    assert response.status_code == 200
    assert "No claim pairs share a concept" in response.text
