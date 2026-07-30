"""Read-only summary of `core`'s Phase 4 knowledge graph.

Reads `core`'s SQLite database directly via SQLAlchemy table reflection
-- never by importing `knowledge_engine` (see `docs/web_design.md`'s
Decision section) and never by redeclaring `core`'s schema by hand, so
this stays correct as `core`'s own schema evolves rather than drifting
out of sync silently.
"""

from __future__ import annotations

from dataclasses import dataclass

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


_GRAPH_TABLE_NAMES = (
    "graph_concepts",
    "graph_claims",
    "graph_claim_concepts",
    "graph_claim_relationships",
    "graph_citations",
)


def read_graph_summary(engine: Engine) -> GraphSummary:
    """Return the graph's current row counts, or all zeros if the graph tables don't exist yet.

    A `core` database predating M46 (no graph tables at all) or M47 (no
    `graph_citations` yet) is a real, expected state, not an error --
    every missing table's count reports as zero rather than raising.
    """

    existing_table_names = set(inspect(engine).get_table_names())
    metadata = MetaData()
    tables = {
        name: Table(name, metadata, autoload_with=engine)
        for name in _GRAPH_TABLE_NAMES
        if name in existing_table_names
    }

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


def _count_rows(connection: Connection, table: Table | None) -> int:
    if table is None:
        return 0
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())
