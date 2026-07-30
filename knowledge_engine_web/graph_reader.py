"""Read-only summary of `core`'s Phase 4 knowledge graph.

Reads `core`'s SQLite database directly via SQLAlchemy table reflection
-- never by importing `knowledge_engine` (see `docs/web_design.md`'s
Decision section) and never by redeclaring `core`'s schema by hand, so
this stays correct as `core`'s own schema evolves rather than drifting
out of sync silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, MetaData, Table, func, inspect, select
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class GraphSummary:
    """The same corpus-wide counts `ke graph-report`'s no-filter mode prints."""

    concepts_total: int
    concepts_by_source: dict[str, int]
    claims_total: int
    claim_concept_edges_total: int
    relationship_edges_total: int
    citation_edges_total: int


@dataclass(frozen=True)
class ClaimListItem:
    """One row of `GET /claims`'s listing."""

    id: int
    evidence_record_id: str
    created_at: str


@dataclass(frozen=True)
class ConceptEdge:
    """One concept linked to a claim, preserving which PICO role produced the edge."""

    edge_role: str
    label: str
    source: str
    source_reference_id: str | None
    definition: str | None


@dataclass(frozen=True)
class RelationshipEdge:
    """One relationship edge touching a claim, as source or target."""

    relationship_type: str
    direction: str
    rationale: str
    other_evidence_record_id: str


@dataclass(frozen=True)
class ClaimDetail:
    """The same detail `ke graph-report --evidence-record-id` prints."""

    id: int
    evidence_record_id: str
    created_at: str
    concepts: list[ConceptEdge] = field(default_factory=list)
    relationships: list[RelationshipEdge] = field(default_factory=list)


_GRAPH_TABLE_NAMES = (
    "graph_concepts",
    "graph_claims",
    "graph_claim_concepts",
    "graph_claim_relationships",
    "graph_citations",
)


def _reflect_graph_tables(engine: Engine) -> dict[str, Table]:
    """Reflect whichever graph tables actually exist on this `core` database.

    A database predating M46 (no graph tables) or M47 (no `graph_citations`
    yet) is a real, expected state, not an error -- callers key into this
    dict with `.get(name)` and treat a missing table as "nothing here yet."
    """

    existing_table_names = set(inspect(engine).get_table_names())
    metadata = MetaData()
    return {
        name: Table(name, metadata, autoload_with=engine)
        for name in _GRAPH_TABLE_NAMES
        if name in existing_table_names
    }


def read_graph_summary(engine: Engine) -> GraphSummary:
    """Return the graph's current row counts, or all zeros if the graph tables don't exist yet."""

    tables = _reflect_graph_tables(engine)

    with engine.connect() as connection:
        concepts_by_source: dict[str, int] = {}
        if (concepts := tables.get("graph_concepts")) is not None:
            rows = connection.execute(
                select(concepts.c.source, func.count()).group_by(concepts.c.source)
            ).all()
            concepts_by_source = {str(source): int(count) for source, count in rows}

        return GraphSummary(
            concepts_total=sum(concepts_by_source.values()),
            concepts_by_source=concepts_by_source,
            claims_total=_count_rows(connection, tables.get("graph_claims")),
            claim_concept_edges_total=_count_rows(connection, tables.get("graph_claim_concepts")),
            relationship_edges_total=_count_rows(
                connection, tables.get("graph_claim_relationships")
            ),
            citation_edges_total=_count_rows(connection, tables.get("graph_citations")),
        )


def list_claims(engine: Engine) -> list[ClaimListItem]:
    """Return every claim, ordered by ID, or an empty list if the graph doesn't exist yet."""

    tables = _reflect_graph_tables(engine)
    claims = tables.get("graph_claims")
    if claims is None:
        return []

    with engine.connect() as connection:
        rows = connection.execute(
            select(claims.c.id, claims.c.evidence_record_id, claims.c.created_at).order_by(
                claims.c.id
            )
        ).all()
    return [
        ClaimListItem(
            id=row.id, evidence_record_id=row.evidence_record_id, created_at=row.created_at
        )
        for row in rows
    ]


def read_claim_detail(engine: Engine, evidence_record_id: str) -> ClaimDetail | None:
    """Return one claim's concepts (by PICO role) and relationship edges, or `None` if not found.

    Mirrors `ke graph-report --evidence-record-id`'s content exactly,
    read via SQL joins instead of `core`'s `GraphRepository`.
    """

    tables = _reflect_graph_tables(engine)
    claims = tables.get("graph_claims")
    if claims is None:
        return None

    with engine.connect() as connection:
        claim_row = connection.execute(
            select(claims.c.id, claims.c.evidence_record_id, claims.c.created_at).where(
                claims.c.evidence_record_id == evidence_record_id
            )
        ).first()
        if claim_row is None:
            return None

        concepts = _read_concept_edges(connection, tables, claim_row.id)
        relationships = _read_relationship_edges(connection, tables, claim_row.id)

        return ClaimDetail(
            id=claim_row.id,
            evidence_record_id=claim_row.evidence_record_id,
            created_at=claim_row.created_at,
            concepts=concepts,
            relationships=relationships,
        )


def _read_concept_edges(
    connection: Connection, tables: dict[str, Table], claim_id: int
) -> list[ConceptEdge]:
    claim_concepts = tables.get("graph_claim_concepts")
    concepts = tables.get("graph_concepts")
    if claim_concepts is None or concepts is None:
        return []

    rows = connection.execute(
        select(
            claim_concepts.c.edge_role,
            concepts.c.label,
            concepts.c.source,
            concepts.c.source_reference_id,
            concepts.c.definition,
        )
        .select_from(claim_concepts.join(concepts, claim_concepts.c.concept_id == concepts.c.id))
        .where(claim_concepts.c.claim_id == claim_id)
        .order_by(claim_concepts.c.edge_role, concepts.c.id)
    ).all()
    return [
        ConceptEdge(
            edge_role=row.edge_role,
            label=row.label,
            source=row.source,
            source_reference_id=row.source_reference_id,
            definition=row.definition,
        )
        for row in rows
    ]


def _read_relationship_edges(
    connection: Connection, tables: dict[str, Table], claim_id: int
) -> list[RelationshipEdge]:
    relationships = tables.get("graph_claim_relationships")
    claims = tables.get("graph_claims")
    if relationships is None or claims is None:
        return []

    edges: list[tuple[int, RelationshipEdge]] = []
    for direction, own_column, other_column in (
        ("source", relationships.c.source_claim_id, relationships.c.target_claim_id),
        ("target", relationships.c.target_claim_id, relationships.c.source_claim_id),
    ):
        rows = connection.execute(
            select(
                relationships.c.id,
                relationships.c.relationship_type,
                relationships.c.rationale,
                claims.c.evidence_record_id.label("other_evidence_record_id"),
            )
            .select_from(relationships.join(claims, claims.c.id == other_column))
            .where(own_column == claim_id)
        ).all()
        edges.extend(
            (
                row.id,
                RelationshipEdge(
                    relationship_type=row.relationship_type,
                    direction=direction,
                    rationale=row.rationale,
                    other_evidence_record_id=row.other_evidence_record_id,
                ),
            )
            for row in rows
        )

    edges.sort(key=lambda item: item[0])
    return [edge for _relationship_id, edge in edges]


def _count_rows(connection: Connection, table: Table | None) -> int:
    if table is None:
        return 0
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())
