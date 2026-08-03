"""Read-only summary of `core`'s Phase 4 knowledge graph.

Reads `core`'s SQLite database directly via SQLAlchemy table reflection
-- never by importing `knowledge_engine` (see `docs/web_design.md`'s
Decision section) and never by redeclaring `core`'s schema by hand, so
this stays correct as `core`'s own schema evolves rather than drifting
out of sync silently.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

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

    relationship_id: str
    relationship_type: str
    direction: str
    rationale: str
    other_evidence_record_id: str
    created_at: str


@dataclass(frozen=True)
class RelationshipListItem:
    """One relationship edge in the graph, both sides resolved to their `evidence_record_id`."""

    relationship_id: str
    relationship_type: str
    source_evidence_record_id: str
    target_evidence_record_id: str
    created_at: str


@dataclass(frozen=True)
class RelationshipCandidate:
    """One claim pair sharing at least one PICO-resolved concept, with no relationship edge yet."""

    claim_a_evidence_record_id: str
    claim_b_evidence_record_id: str
    shared_concept_labels: list[str]


@dataclass(frozen=True)
class PaperCitationEdge:
    """One citation edge and the paper on its other side."""

    paper_id: int
    title: str
    doi: str | None
    raw_citation_text: str


@dataclass(frozen=True)
class PaperDetail:
    """The same detail `ke graph-report --paper-id` prints."""

    id: int
    title: str
    doi: str | None
    cites: list[PaperCitationEdge] = field(default_factory=list)
    cited_by: list[PaperCitationEdge] = field(default_factory=list)


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


def list_unconfirmed_claims(engine: Engine) -> list[ClaimListItem]:
    """Return every claim with zero relationship edges of any type, ordered by ID.

    Mirrors `ke graph-unconfirmed-claims`: the only "gap" this project can
    honestly surface without guessing -- a real structural fact the graph
    already stores, not a judgment about the underlying science. See
    `docs/stability_and_tracking_design.md` in `knowledge-engine-core`.
    """

    tables = _reflect_graph_tables(engine)
    claims = tables.get("graph_claims")
    relationships = tables.get("graph_claim_relationships")
    if claims is None:
        return []
    if relationships is None:
        return list_claims(engine)

    with engine.connect() as connection:
        confirmed_ids = set(
            connection.execute(select(relationships.c.source_claim_id)).scalars()
        ) | set(connection.execute(select(relationships.c.target_claim_id)).scalars())

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
        if row.id not in confirmed_ids
    ]


def list_relationships(engine: Engine) -> list[RelationshipListItem]:
    """Return every relationship edge in the graph, ordered by creation, or `[]` if none exist.

    Unlike `_read_relationship_edges` (per-claim, called twice per edge --
    once from each side), this reads every edge exactly once, both sides
    already resolved to their `evidence_record_id`. Built for corpus-wide
    reporting (`whats_changed.py`) where a per-claim N+1 query pattern
    would be wasteful.
    """

    tables = _reflect_graph_tables(engine)
    relationships = tables.get("graph_claim_relationships")
    claims = tables.get("graph_claims")
    if relationships is None or claims is None:
        return []

    source_claims = claims.alias("source_claims")
    target_claims = claims.alias("target_claims")

    with engine.connect() as connection:
        rows = connection.execute(
            select(
                relationships.c.relationship_id,
                relationships.c.relationship_type,
                relationships.c.created_at,
                source_claims.c.evidence_record_id.label("source_evidence_record_id"),
                target_claims.c.evidence_record_id.label("target_evidence_record_id"),
            )
            .select_from(
                relationships.join(
                    source_claims, relationships.c.source_claim_id == source_claims.c.id
                ).join(target_claims, relationships.c.target_claim_id == target_claims.c.id)
            )
            .order_by(relationships.c.id)
        ).all()
    return [
        RelationshipListItem(
            relationship_id=row.relationship_id,
            relationship_type=row.relationship_type,
            source_evidence_record_id=row.source_evidence_record_id,
            target_evidence_record_id=row.target_evidence_record_id,
            created_at=row.created_at,
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
                relationships.c.relationship_id,
                relationships.c.relationship_type,
                relationships.c.rationale,
                relationships.c.created_at,
                claims.c.evidence_record_id.label("other_evidence_record_id"),
            )
            .select_from(relationships.join(claims, claims.c.id == other_column))
            .where(own_column == claim_id)
        ).all()
        edges.extend(
            (
                row.id,
                RelationshipEdge(
                    relationship_id=row.relationship_id,
                    relationship_type=row.relationship_type,
                    direction=direction,
                    rationale=row.rationale,
                    other_evidence_record_id=row.other_evidence_record_id,
                    created_at=row.created_at,
                ),
            )
            for row in rows
        )

    edges.sort(key=lambda item: item[0])
    return [edge for _relationship_id, edge in edges]


def read_paper_detail(engine: Engine, paper_id: int) -> PaperDetail | None:
    """Return one paper's citation edges, as citer and as cited, or `None` if not found.

    Mirrors `ke graph-report --paper-id`'s content exactly. `papers` is
    reflected separately from `_GRAPH_TABLE_NAMES` -- it predates Phase 4
    and is not itself a graph table, but citation edges reference it.
    """

    existing_table_names = set(inspect(engine).get_table_names())
    if "papers" not in existing_table_names:
        return None

    metadata = MetaData()
    papers = Table("papers", metadata, autoload_with=engine)

    with engine.connect() as connection:
        paper_row = connection.execute(
            select(papers.c.id, papers.c.title, papers.c.doi).where(papers.c.id == paper_id)
        ).first()
        if paper_row is None:
            return None

        cites: list[PaperCitationEdge] = []
        cited_by: list[PaperCitationEdge] = []
        if "graph_citations" in existing_table_names:
            citations = Table("graph_citations", metadata, autoload_with=engine)
            for direction, own_column, other_column in (
                ("cites", citations.c.citing_paper_id, citations.c.cited_paper_id),
                ("cited_by", citations.c.cited_paper_id, citations.c.citing_paper_id),
            ):
                rows = connection.execute(
                    select(
                        papers.c.id,
                        papers.c.title,
                        papers.c.doi,
                        citations.c.raw_citation_text,
                    )
                    .select_from(citations.join(papers, papers.c.id == other_column))
                    .where(own_column == paper_id)
                ).all()
                edges = [
                    PaperCitationEdge(
                        paper_id=row.id,
                        title=row.title,
                        doi=row.doi,
                        raw_citation_text=row.raw_citation_text,
                    )
                    for row in rows
                ]
                if direction == "cites":
                    cites = edges
                else:
                    cited_by = edges

        return PaperDetail(
            id=paper_row.id,
            title=paper_row.title,
            doi=paper_row.doi,
            cites=cites,
            cited_by=cited_by,
        )


def list_relationship_candidates(
    engine: Engine, *, minimum_shared_concepts: int = 1
) -> list[RelationshipCandidate]:
    """Return claim pairs sharing at least `minimum_shared_concepts` concepts.

    Mirrors `ke graph-relationship-candidates` / `core`'s
    `GraphRepository.relationship_candidates` exactly: structural overlap
    only -- never a relationship type or rationale. A pair already linked
    by an existing relationship edge, in either direction, is excluded,
    since a human has already made that call for it. See
    `docs/m49_graph_relationship_candidates.md` in `knowledge-engine-core`.
    """

    tables = _reflect_graph_tables(engine)
    claims = tables.get("graph_claims")
    claim_concepts = tables.get("graph_claim_concepts")
    concepts = tables.get("graph_concepts")
    if claims is None or claim_concepts is None or concepts is None:
        return []

    with engine.connect() as connection:
        claims_by_concept: dict[int, set[int]] = defaultdict(set)
        for concept_id, claim_id in connection.execute(
            select(claim_concepts.c.concept_id, claim_concepts.c.claim_id).distinct()
        ):
            claims_by_concept[concept_id].add(claim_id)

        shared_concepts_by_pair: dict[tuple[int, int], set[int]] = defaultdict(set)
        for concept_id, claim_ids in claims_by_concept.items():
            for claim_a_id, claim_b_id in combinations(sorted(claim_ids), 2):
                shared_concepts_by_pair[(claim_a_id, claim_b_id)].add(concept_id)

        existing_edges: set[frozenset[int]] = set()
        if (relationships := tables.get("graph_claim_relationships")) is not None:
            existing_edges = {
                frozenset((source_id, target_id))
                for source_id, target_id in connection.execute(
                    select(relationships.c.source_claim_id, relationships.c.target_claim_id)
                )
            }

        evidence_ids_by_claim_id: dict[int, str] = {
            row.id: row.evidence_record_id
            for row in connection.execute(select(claims.c.id, claims.c.evidence_record_id))
        }
        labels_by_concept_id: dict[int, str] = {
            row.id: row.label for row in connection.execute(select(concepts.c.id, concepts.c.label))
        }

        ranked_pairs: list[tuple[int, int, int, list[str]]] = []
        for (claim_a_id, claim_b_id), concept_ids in shared_concepts_by_pair.items():
            if len(concept_ids) < minimum_shared_concepts:
                continue
            if frozenset((claim_a_id, claim_b_id)) in existing_edges:
                continue
            labels = [labels_by_concept_id[cid] for cid in sorted(concept_ids)]
            ranked_pairs.append((len(concept_ids), claim_a_id, claim_b_id, labels))

        ranked_pairs.sort(key=lambda item: (-item[0], item[1], item[2]))

    return [
        RelationshipCandidate(
            claim_a_evidence_record_id=evidence_ids_by_claim_id[claim_a_id],
            claim_b_evidence_record_id=evidence_ids_by_claim_id[claim_b_id],
            shared_concept_labels=labels,
        )
        for _count, claim_a_id, claim_b_id, labels in ranked_pairs
    ]


def _count_rows(connection: Connection, table: Table | None) -> int:
    if table is None:
        return 0
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())
