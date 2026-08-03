import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, MetaData, Table, insert, text

from knowledge_engine_web import main
from knowledge_engine_web.main import app
from tests._fixtures import build_engine, create_graph_tables, create_papers_table


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


def test_claim_detail_page_renders_relationship_provenance_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
                    "rationale": "Both report the same direction.",
                }
            ],
        )
    relationship_path = tmp_path / "relationship_records.jsonl"
    relationship_path.write_text(
        json.dumps(
            {
                "relationship_id": "rel-1",
                "source_evidence_record_id": "ev-1",
                "target_evidence_record_id": "ev-2",
                "relationship_type": "supports",
                "rationale": "Both report the same direction.",
                "provenance": {
                    "created_by": "manual review",
                    "method": "reviewed both PICO fields",
                },
                "created_for_milestone": "M56",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_RELATIONSHIP_RECORDS_PATH", str(relationship_path))

    response = TestClient(app).get("/claims/ev-1")

    assert response.status_code == 200
    assert "rel-1" in response.text
    assert "manual review" in response.text
    assert "reviewed both PICO fields" in response.text
    assert "M56" in response.text


def test_claim_detail_page_omits_relationship_provenance_when_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
                    "rationale": "Both report the same direction.",
                }
            ],
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.delenv("KE_WEB_RELATIONSHIP_RECORDS_PATH", raising=False)

    response = TestClient(app).get("/claims/ev-1")

    assert response.status_code == 200
    assert "supports" in response.text
    assert "Relationship ID:" not in response.text


def test_claim_detail_page_404s_for_an_unknown_evidence_record_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    create_graph_tables(engine)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/claims/ev-does-not-exist")

    assert response.status_code == 404


def test_claim_detail_page_omits_evidence_content_when_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.delenv("KE_WEB_EVIDENCE_RECORDS_PATH", raising=False)

    response = TestClient(app).get("/claims/ev-1")

    assert response.status_code == 200
    assert "KE_WEB_EVIDENCE_RECORDS_PATH" in response.text


def test_claim_detail_page_renders_evidence_record_content_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "evidence_record_id": "ev-1",
                "research_question": "Does X reduce Y?",
                "claim_text": "X reduces Y in adults.",
                "evidence_direction": "supports",
                "population": "Adults with Y.",
                "intervention": "X, once weekly.",
                "comparator": "Placebo.",
                "outcome": "Change in Y.",
                "result_summary": "X reduced Y by 10% versus placebo.",
                "limitations": ["Single trial."],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_EVIDENCE_RECORDS_PATH", str(evidence_path))

    response = TestClient(app).get("/claims/ev-1")

    assert response.status_code == 200
    assert "Does X reduce Y?" in response.text
    assert "X reduces Y in adults." in response.text
    assert "X reduced Y by 10% versus placebo." in response.text
    assert "Single trial." in response.text


def test_claim_detail_page_escapes_evidence_record_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "evidence_record_id": "ev-1",
                "claim_text": "<script>alert(1)</script>",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_EVIDENCE_RECORDS_PATH", str(evidence_path))

    response = TestClient(app).get("/claims/ev-1")

    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_claim_detail_page_shows_not_yet_assessable_with_no_relationships(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "evidence_record_id": "ev-1",
                "study_type": "randomized_controlled_trial",
                "extraction_method": "manual_human_review",
                "review_checklist": {"source_verified": True},
                "limitations": ["A limitation."],
                "uncertainty_notes": "An uncertainty.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_EVIDENCE_RECORDS_PATH", str(evidence_path))

    response = TestClient(app).get("/claims/ev-1")

    assert response.status_code == 200
    assert "Evidence Intelligence" in response.text
    assert "not yet assessable" in response.text
    assert "reliability: insufficient" in response.text
    assert 'class="confidence-gauge"' in response.text
    assert '<div class="gauge-number">--<span class="of100">/100</span></div>' in response.text
    assert "--needle-angle: -90deg" in response.text


def test_claim_detail_page_computes_consensus_with_two_supports_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
                    "source_claim_id": 2,
                    "target_claim_id": 1,
                    "relationship_type": "supports",
                    "rationale": "Same direction, independent trial.",
                },
                {
                    "id": 2,
                    "relationship_id": "rel-2",
                    "source_claim_id": 3,
                    "target_claim_id": 1,
                    "relationship_type": "supports",
                    "rationale": "Same direction, pooled meta-analysis.",
                },
            ],
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    record_common = {
        "study_type": "randomized_controlled_trial",
        "extraction_method": "manual_human_review",
        "review_checklist": {"source_verified": True},
        "limitations": ["A limitation."],
        "uncertainty_notes": "An uncertainty.",
    }
    evidence_path.write_text(
        "\n".join(
            json.dumps({"evidence_record_id": eid, **record_common})
            for eid in ("ev-1", "ev-2", "ev-3")
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_EVIDENCE_RECORDS_PATH", str(evidence_path))

    response = TestClient(app).get("/claims/ev-1")

    assert response.status_code == 200
    assert "100/100" in response.text
    assert "not yet assessable" not in response.text
    # Claim Confidence is a product of mean Evidence Quality (94, not 100 --
    # the two manual-review/uncertainty-note bonus points don't reach a
    # perfect score) and Evidence Consensus (100, both edges agree), so
    # the gauge shows 94, not 100.
    assert '<div class="gauge-number">94<span class="of100">/100</span></div>' in response.text
    assert "--needle-angle: 79.2deg" in response.text
    assert "2 SUPPORTING &middot; 0 CONTRADICTING" in response.text
    # A 94/100 score with only 2 relationship edges must be labeled a low
    # *reliability* tier, never a "low confidence" score -- the two are
    # different axes and must not be conflated (Codex review on PR #22).
    assert "Reliability: Low reliability" in response.text
    assert "(2 relationship edges)" in response.text
    assert "Low confidence" not in response.text


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


def test_paper_detail_page_renders_citation_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    papers_metadata = create_papers_table(engine)
    graph_metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(papers_metadata.tables["papers"]),
            [
                {"id": 1, "title": "Citing Paper", "doi": "10.1/a"},
                {"id": 2, "title": "Cited Paper", "doi": "10.1/b"},
            ],
        )
        connection.execute(
            insert(graph_metadata.tables["graph_citations"]),
            [
                {
                    "id": 1,
                    "citing_paper_id": 1,
                    "cited_paper_id": 2,
                    "raw_citation_text": "1. Cited Paper. doi: 10.1/b",
                }
            ],
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/papers/1")

    assert response.status_code == 200
    assert "Cites (1)" in response.text
    assert "Cited Paper" in response.text


def test_paper_detail_page_404s_for_an_unknown_paper_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    create_papers_table(engine)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/papers/999")

    assert response.status_code == 404


def test_run_binds_to_the_default_host_and_port_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from knowledge_engine_web.main import run

    calls: list[tuple[object, str, int]] = []
    monkeypatch.setattr(
        "uvicorn.run", lambda application, host, port: calls.append((application, host, port))
    )
    monkeypatch.delenv("KE_WEB_HOST", raising=False)
    monkeypatch.delenv("KE_WEB_PORT", raising=False)

    run()

    assert calls == [(app, "127.0.0.1", 8000)]


def test_run_binds_to_a_configured_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    from knowledge_engine_web.main import run

    calls: list[tuple[object, str, int]] = []
    monkeypatch.setattr(
        "uvicorn.run", lambda application, host, port: calls.append((application, host, port))
    )
    monkeypatch.setenv("KE_WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("KE_WEB_PORT", "9000")

    run()

    assert calls == [(app, "0.0.0.0", 9000)]


def test_about_page_renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/about")

    assert response.status_code == 200
    assert "About Knowledge Engine" in response.text
    assert "The seam" in response.text
    assert "https://buymeacoffee.com/Weterjeremy" in response.text


def test_root_redirects_to_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/graph"


def test_roadmap_page_renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/roadmap")

    assert response.status_code == 200
    assert "Roadmap" in response.text
    assert "Not live" in response.text


def test_concept_preview_static_file_is_served(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/static/concept-preview.html")

    assert response.status_code == 200
    assert "Concept preview -- not live." in response.text


def test_reports_index_lists_every_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/reports")

    assert response.status_code == 200
    assert '<a href="/reports/graph">Graph Report</a>' in response.text
    assert '<a href="/reports/relationship-candidates">Relationship Candidates Report</a>' in (
        response.text
    )
    assert '<a href="/reports/unconfirmed-claims">Unconfirmed Claims Report</a>' in response.text
    assert '<a href="/reports/what-changed">What Changed Report</a>' in response.text


def test_graph_report_view_renders_populated_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_concepts"]),
            [{"id": 1, "label": "Semaglutide", "source": "rxnorm"}],
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/reports/graph")

    assert response.status_code == 200
    assert "# Knowledge Engine Graph Report" in response.text
    assert "Concepts: 1 (rxnorm: 1)" in response.text
    assert "Download as Markdown" in response.text


def test_graph_report_download_returns_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_engine(tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/reports/graph.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.startswith("# Knowledge Engine Graph Report")


def test_relationship_candidates_report_view_lists_a_pair(
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

    response = TestClient(app).get("/reports/relationship-candidates")

    assert response.status_code == 200
    assert "# Knowledge Engine Graph Relationship Candidates" in response.text
    assert "ev-a" in response.text
    assert "ev-b" in response.text


def test_unconfirmed_claims_report_view_lists_a_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/reports/unconfirmed-claims")

    assert response.status_code == 200
    assert "# Knowledge Engine Graph Unconfirmed Claims" in response.text
    assert "ev-1" in response.text


def test_whats_changed_report_view_with_no_baseline_yet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv(
        "KE_WEB_WHATS_CHANGED_BASELINE_PATH", str(tmp_path / "does-not-exist-yet.json")
    )

    response = TestClient(app).get("/reports/what-changed")

    assert response.status_code == 200
    assert "# Knowledge Engine What Changed Report" in response.text
    # No baseline captured yet -- honest about having nothing real to
    # diff against, not a fabricated "ev-1 is new" claim.
    assert "No baseline has been captured yet" in response.text
    assert "New claims: 0" in response.text


def test_whats_changed_report_view_lists_a_new_claim_against_a_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]),
            [
                {"id": 1, "evidence_record_id": "ev-baseline"},
                {"id": 2, "evidence_record_id": "ev-new"},
            ],
        )
    baseline_path = tmp_path / "whats_changed_baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "captured_at": "2026-08-01T00:00:00+00:00",
                "claim_evidence_record_ids": ["ev-baseline"],
                "relationship_ids": [],
                "claims_with_evidence_configured": 0,
                "mean_quality_score": None,
                "coverage_records_in_relationship": 0,
                "coverage_total_records": 0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_WHATS_CHANGED_BASELINE_PATH", str(baseline_path))

    response = TestClient(app).get("/reports/what-changed")

    assert response.status_code == 200
    assert "Comparing against the baseline captured: 2026-08-01T00:00:00+00:00" in response.text
    assert "New claims: 1" in response.text
    assert "ev-new" in response.text
    assert "ev-baseline" not in response.text.split("## New Claims")[1].split("##")[0]
    # No KE_WEB_EVIDENCE_RECORDS_PATH configured -- deltas must say so
    # honestly rather than showing a fabricated 0%.
    assert "not configured on this deployment" in response.text


def test_whats_changed_report_download_returns_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_engine(tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv(
        "KE_WEB_WHATS_CHANGED_BASELINE_PATH", str(tmp_path / "does-not-exist-yet.json")
    )

    response = TestClient(app).get("/reports/what-changed.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# Knowledge Engine What Changed Report")


def test_report_view_404s_for_an_unknown_report_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/reports/does-not-exist")

    assert response.status_code == 404


def test_report_download_404s_for_an_unknown_report_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/reports/does-not-exist.md")

    assert response.status_code == 404


def test_graph_report_escapes_a_malicious_concept_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concept `source` value cannot inject HTML into the rendered report page."""

    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_concepts"]),
            [{"id": 1, "label": "Semaglutide", "source": "<script>alert(1)</script>"}],
        )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/reports/graph")

    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_static_stylesheet_is_served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/static/style.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def _create_fts_table_and_paper(
    engine: Engine, *, paper_id: int, title: str, doi: str, abstract: str = ""
) -> None:
    create_papers_table(engine)
    with engine.begin() as connection:
        connection.execute(
            text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS paper_search
                USING fts5(
                    title,
                    abstract,
                    body_text,
                    raw_text,
                    tokenize='porter unicode61'
                )
                """)
        )
        metadata = MetaData()
        papers = Table("papers", metadata, autoload_with=engine)
        connection.execute(insert(papers).values(id=paper_id, title=title, doi=doi))
        connection.execute(
            text(
                "INSERT INTO paper_search(rowid, title, abstract, body_text, raw_text) "
                "VALUES (:id, :title, :abstract, '', '')"
            ),
            {"id": paper_id, "title": title, "abstract": abstract},
        )


def test_ask_page_renders_the_empty_state_with_no_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_engine(tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/ask")

    assert response.status_code == 200
    assert "Ask a research question" in response.text
    assert "Results for" not in response.text


def test_ask_page_reports_no_relevant_papers_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    create_papers_table(engine)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/ask", params={"q": "does metformin reduce glucose"})

    assert response.status_code == 200
    assert "No relevant papers found" in response.text


def test_ask_page_renders_a_matched_paper_without_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    _create_fts_table_and_paper(
        engine,
        paper_id=1,
        title="A Trial of Semaglutide for Body Weight Reduction",
        doi="10.1000/example",
        abstract="Semaglutide reduced body weight versus placebo.",
    )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.delenv("KE_WEB_EVIDENCE_RECORDS_PATH", raising=False)

    response = TestClient(app).get("/ask", params={"q": "does semaglutide reduce body weight"})

    assert response.status_code == 200
    assert "A Trial of Semaglutide for Body Weight Reduction" in response.text
    assert "10.1000/example" in response.text
    assert "No evidence record matched" in response.text


def test_ask_page_renders_evidence_and_intelligence_for_a_matched_paper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    _create_fts_table_and_paper(
        engine,
        paper_id=1,
        title="A Trial of Semaglutide for Body Weight Reduction",
        doi="10.1000/example",
        abstract="Semaglutide reduced body weight versus placebo.",
    )
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "evidence_record_id": "ev-1",
                "source_doi": "10.1000/example",
                "claim_text": "Semaglutide reduced body weight.",
                "extraction_method": "manual_human_review",
                "review_checklist": {"source_verified": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_EVIDENCE_RECORDS_PATH", str(evidence_path))

    response = TestClient(app).get("/ask", params={"q": "does semaglutide reduce body weight"})

    assert response.status_code == 200
    assert "ev-1" in response.text
    assert "Semaglutide reduced body weight." in response.text
    assert "Evidence Quality:" in response.text
    assert "not yet assessable" in response.text  # no relationship edges yet


def test_ask_page_escapes_a_malicious_snippet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    _create_fts_table_and_paper(
        engine,
        paper_id=1,
        title="<script>alert(1)</script> semaglutide",
        doi="10.1000/example",
    )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.delenv("KE_WEB_EVIDENCE_RECORDS_PATH", raising=False)

    response = TestClient(app).get("/ask", params={"q": "semaglutide"})

    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;" in response.text


class _FakeLLM:
    def __init__(self, *, model: str, host: str) -> None:
        self.model = model
        self.host = host

    def generate(self, prompt: str, *, max_tokens: int = 400) -> str:
        assert "does semaglutide reduce body weight" in prompt
        return "Semaglutide reduces body weight [ev-1]."


class _FailingFakeLLM:
    def __init__(self, *, model: str, host: str) -> None:
        pass

    def generate(self, prompt: str, *, max_tokens: int = 400) -> str:
        from knowledge_engine_web.llm import LocalLLMError

        raise LocalLLMError("Could not reach Ollama at http://x: refused.")


def _setup_paper_with_evidence(engine: Engine, tmp_path: Path) -> Path:
    _create_fts_table_and_paper(
        engine,
        paper_id=1,
        title="A Trial of Semaglutide for Body Weight Reduction",
        doi="10.1000/example",
        abstract="Semaglutide reduced body weight versus placebo.",
    )
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "evidence_record_id": "ev-1",
                "source_doi": "10.1000/example",
                "claim_text": "Semaglutide reduced body weight.",
                "extraction_method": "manual_human_review",
                "review_checklist": {"source_verified": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return evidence_path


def test_ask_without_synthesize_shows_no_synthesis_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    evidence_path = _setup_paper_with_evidence(engine, tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_EVIDENCE_RECORDS_PATH", str(evidence_path))
    monkeypatch.setattr(main, "OllamaLLM", _FakeLLM)

    response = TestClient(app).get("/ask", params={"q": "does semaglutide reduce body weight"})

    assert response.status_code == 200
    assert "AI-generated synthesis" not in response.text


def test_ask_synthesize_requires_llm_model_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    evidence_path = _setup_paper_with_evidence(engine, tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_EVIDENCE_RECORDS_PATH", str(evidence_path))
    monkeypatch.delenv("KE_WEB_LLM_MODEL", raising=False)

    response = TestClient(app).get(
        "/ask", params={"q": "does semaglutide reduce body weight", "synthesize": "1"}
    )

    assert response.status_code == 200
    assert "AI-generated synthesis" in response.text
    assert "KE_WEB_LLM_MODEL must be set" in response.text


def test_ask_synthesize_renders_the_grounded_narrative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    evidence_path = _setup_paper_with_evidence(engine, tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_EVIDENCE_RECORDS_PATH", str(evidence_path))
    monkeypatch.setenv("KE_WEB_LLM_MODEL", "qwen2.5:1.5b")
    monkeypatch.setattr(main, "OllamaLLM", _FakeLLM)

    response = TestClient(app).get(
        "/ask", params={"q": "does semaglutide reduce body weight", "synthesize": "1"}
    )

    assert response.status_code == 200
    assert "AI-generated synthesis" in response.text
    assert "Semaglutide reduces body weight [ev-1]." in response.text


def test_ask_synthesize_reports_a_local_llm_error_inline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    evidence_path = _setup_paper_with_evidence(engine, tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_EVIDENCE_RECORDS_PATH", str(evidence_path))
    monkeypatch.setenv("KE_WEB_LLM_MODEL", "qwen2.5:1.5b")
    monkeypatch.setattr(main, "OllamaLLM", _FailingFakeLLM)

    response = TestClient(app).get(
        "/ask", params={"q": "does semaglutide reduce body weight", "synthesize": "1"}
    )

    assert response.status_code == 200
    assert "Could not reach Ollama" in response.text


def test_dashboard_page_shows_not_configured_message_without_evidence_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_engine(tmp_path)
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))

    response = TestClient(app).get("/dashboard")

    assert response.status_code == 200
    assert "Not configured on this server" in response.text


def test_dashboard_page_renders_aggregate_evidence_intelligence_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_claims"]), [{"id": 1, "evidence_record_id": "ev-1"}]
        )
    evidence_path = tmp_path / "evidence_records.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "evidence_record_id": "ev-1",
                "study_type": "randomized_controlled_trial",
                "extraction_method": "manual_human_review",
                "review_checklist": {"source_verified": True},
                "limitations": ["A limitation."],
                "uncertainty_notes": "An uncertainty.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KE_WEB_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("KE_WEB_EVIDENCE_RECORDS_PATH", str(evidence_path))

    response = TestClient(app).get("/dashboard")

    assert response.status_code == 200
    assert "Claims in the graph: 1" in response.text
    assert "Claims with evidence-record content configured: 1" in response.text
    assert "Evidence Quality Distribution" in response.text
    assert "Claim Confidence Reliability" in response.text
