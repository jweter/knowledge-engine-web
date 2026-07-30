from pathlib import Path

from sqlalchemy import insert

from knowledge_engine_web.graph_reader import (
    GraphSummary,
    list_claims,
    read_claim_detail,
    read_graph_summary,
)
from tests._fixtures import build_engine, create_graph_tables


def test_read_graph_summary_on_a_database_with_no_graph_tables_yet(tmp_path: Path) -> None:
    """A `core` database predating M46 has no graph tables at all -- every count is zero."""

    engine = build_engine(tmp_path)

    summary = read_graph_summary(engine)

    assert summary == GraphSummary(
        concepts_total=0,
        concepts_by_source={},
        claims_total=0,
        claim_concept_edges_total=0,
        relationship_edges_total=0,
        citation_edges_total=0,
    )


def test_read_graph_summary_on_a_database_predating_graph_citations(tmp_path: Path) -> None:
    """A `core` database at schema version 8 (M46) has no `graph_citations` table yet (M47)."""

    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine, include_citations=False)

    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_concepts"]),
            [{"id": 1, "label": "Semaglutide", "source": "rxnorm"}],
        )

    summary = read_graph_summary(engine)

    assert summary.citation_edges_total == 0
    assert summary.concepts_total == 1


def test_read_graph_summary_on_a_populated_graph(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)

    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_concepts"]),
            [
                {"id": 1, "label": "Semaglutide", "source": "rxnorm"},
                {"id": 2, "label": "Placebo", "source": "rxnorm"},
                {"id": 3, "label": "Obesity", "source": "mesh"},
            ],
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
            [
                {"id": 1, "claim_id": 1, "concept_id": 1, "edge_role": "intervention"},
                {"id": 2, "claim_id": 1, "concept_id": 2, "edge_role": "comparator"},
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
                }
            ],
        )
        connection.execute(
            insert(metadata.tables["graph_citations"]),
            [{"id": 1, "citing_paper_id": 1, "cited_paper_id": 2}],
        )

    summary = read_graph_summary(engine)

    assert summary.concepts_total == 3
    assert summary.concepts_by_source == {"rxnorm": 2, "mesh": 1}
    assert summary.claims_total == 2
    assert summary.claim_concept_edges_total == 2
    assert summary.relationship_edges_total == 1
    assert summary.citation_edges_total == 1


def test_list_claims_on_a_database_with_no_graph_tables_yet(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)

    assert list_claims(engine) == []


def test_list_claims_returns_every_claim_in_id_order(tmp_path: Path) -> None:
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

    claims = list_claims(engine)

    assert [claim.evidence_record_id for claim in claims] == ["ev-1", "ev-2"]


def test_read_claim_detail_returns_none_for_an_unknown_evidence_record_id(
    tmp_path: Path,
) -> None:
    engine = build_engine(tmp_path)
    create_graph_tables(engine)

    assert read_claim_detail(engine, "ev-does-not-exist") is None


def test_read_claim_detail_groups_concepts_and_relationships(tmp_path: Path) -> None:
    engine = build_engine(tmp_path)
    metadata = create_graph_tables(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(metadata.tables["graph_concepts"]),
            [
                {
                    "id": 1,
                    "label": "Semaglutide",
                    "source": "rxnorm",
                    "definition": "semaglutide; IN",
                },
                {"id": 2, "label": "Placebo", "source": "rxnorm", "definition": None},
            ],
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
            [
                {"id": 1, "claim_id": 1, "concept_id": 1, "edge_role": "intervention"},
                {"id": 2, "claim_id": 1, "concept_id": 2, "edge_role": "comparator"},
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

    detail = read_claim_detail(engine, "ev-1")

    assert detail is not None
    assert detail.evidence_record_id == "ev-1"
    assert [(c.edge_role, c.label) for c in detail.concepts] == [
        ("comparator", "Placebo"),
        ("intervention", "Semaglutide"),
    ]
    assert detail.concepts[1].definition == "semaglutide; IN"
    assert len(detail.relationships) == 1
    assert detail.relationships[0].direction == "source"
    assert detail.relationships[0].other_evidence_record_id == "ev-2"

    other_detail = read_claim_detail(engine, "ev-2")
    assert other_detail is not None
    assert len(other_detail.relationships) == 1
    assert other_detail.relationships[0].direction == "target"
    assert other_detail.relationships[0].other_evidence_record_id == "ev-1"
