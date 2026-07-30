"""Shared fixture-database helpers for tests.

Builds small SQLite databases with plain SQLAlchemy `Table` objects
matching `core`'s real, documented column names (read directly from
`knowledge_engine/models.py` in `knowledge-engine-core`, not imported --
see `docs/web_design.md`'s Decision section on why this project never
imports `knowledge_engine`).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Column, Engine, Integer, MetaData, String, Table, Text, create_engine


def build_engine(tmp_path: Path, name: str = "fixture") -> Engine:
    return create_engine(f"sqlite:///{tmp_path / name}.sqlite3")


def create_graph_tables(engine: Engine, *, include_citations: bool = True) -> MetaData:
    """Create tables matching `core`'s real graph schema, minus what this project never reads."""

    metadata = MetaData()
    Table(
        "graph_concepts",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("label", Text, nullable=False),
        Column("source", String(16), nullable=False),
        Column("source_reference_id", String(64)),
        Column("definition", Text),
    )
    Table(
        "graph_claims",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("evidence_record_id", String(128), nullable=False),
        Column("created_at", String(32), nullable=False, default="2026-01-01T00:00:00Z"),
    )
    Table(
        "graph_claim_concepts",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("claim_id", Integer, nullable=False),
        Column("concept_id", Integer, nullable=False),
        Column("edge_role", String(16), nullable=False),
    )
    Table(
        "graph_claim_relationships",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("relationship_id", String(128), nullable=False),
        Column("source_claim_id", Integer, nullable=False),
        Column("target_claim_id", Integer, nullable=False),
        Column("relationship_type", String(16), nullable=False),
        Column("rationale", Text, nullable=False, default=""),
    )
    if include_citations:
        Table(
            "graph_citations",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("citing_paper_id", Integer, nullable=False),
            Column("cited_paper_id", Integer, nullable=False),
        )
    metadata.create_all(engine)
    return metadata
