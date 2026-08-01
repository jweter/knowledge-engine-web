"""Tests for scripts/build_alpha_snapshot.py.

The existing fixture helpers in tests/_fixtures.py don't declare
`papers.journal_id`'s foreign key to `journals` -- that's exactly what
broke the alpha's first real Render deploy (SQLAlchemy's reflection
follows foreign keys and errors if the referenced table is missing),
so a synthetic source database with the real foreign key is built here
instead, matching `core`'s actual schema more closely than the shared
fixtures do.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from types import ModuleType

from sqlalchemy import MetaData, Table, create_engine


def _load_build_alpha_snapshot() -> ModuleType:
    script_path = Path(__file__).parent.parent / "scripts" / "build_alpha_snapshot.py"
    spec = importlib.util.spec_from_file_location("build_alpha_snapshot", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_alpha_snapshot = _load_build_alpha_snapshot()


def _create_core_like_source(path: Path) -> None:
    """Build a source database with the real foreign-key shape `core` has."""

    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE journals (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            doi TEXT,
            journal_id INTEGER REFERENCES journals(id)
        );
        CREATE TABLE graph_concepts (id INTEGER PRIMARY KEY, label TEXT NOT NULL);
        CREATE TABLE graph_claims (
            id INTEGER PRIMARY KEY, evidence_record_id TEXT NOT NULL
        );
        CREATE TABLE graph_claim_concepts (
            id INTEGER PRIMARY KEY,
            claim_id INTEGER REFERENCES graph_claims(id),
            concept_id INTEGER REFERENCES graph_concepts(id)
        );
        CREATE TABLE graph_claim_relationships (
            id INTEGER PRIMARY KEY,
            source_claim_id INTEGER REFERENCES graph_claims(id),
            target_claim_id INTEGER REFERENCES graph_claims(id)
        );
        CREATE TABLE graph_citations (
            id INTEGER PRIMARY KEY,
            citing_paper_id INTEGER REFERENCES papers(id),
            cited_paper_id INTEGER REFERENCES papers(id)
        );
        CREATE TABLE irrelevant_table (id INTEGER PRIMARY KEY);

        INSERT INTO journals VALUES (1, 'Journal of Testing');
        INSERT INTO papers VALUES (1, 'A real paper title', '10.1000/xyz', 1);
        INSERT INTO graph_concepts VALUES (1, 'semaglutide');
        INSERT INTO graph_claims VALUES (1, 'ev-test-001');
        INSERT INTO graph_claim_concepts VALUES (1, 1, 1);
        INSERT INTO irrelevant_table VALUES (1);
        """
    )
    conn.commit()
    conn.close()


def test_snapshot_is_reflectable_by_sqlalchemy(tmp_path: Path) -> None:
    """The exact failure mode from the first Render deploy: reflection must not raise."""

    source_path = tmp_path / "source.sqlite3"
    dest_path = tmp_path / "snapshot.sqlite3"
    _create_core_like_source(source_path)

    build_alpha_snapshot.build_snapshot(source_path, dest_path)

    engine = create_engine(f"sqlite:///{dest_path}")
    metadata = MetaData()
    papers = Table("papers", metadata, autoload_with=engine)
    assert {c.name for c in papers.columns} == {"id", "title", "doi", "journal_id"}


def test_snapshot_omits_tables_the_web_app_never_reads(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    dest_path = tmp_path / "snapshot.sqlite3"
    _create_core_like_source(source_path)

    build_alpha_snapshot.build_snapshot(source_path, dest_path)

    conn = sqlite3.connect(dest_path)
    table_names = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    conn.close()
    assert "irrelevant_table" not in table_names
    assert table_names == set(build_alpha_snapshot.TABLE_NAMES)


def test_snapshot_preserves_row_data(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    dest_path = tmp_path / "snapshot.sqlite3"
    _create_core_like_source(source_path)

    build_alpha_snapshot.build_snapshot(source_path, dest_path)

    conn = sqlite3.connect(dest_path)
    title = conn.execute("SELECT title FROM papers WHERE id = 1").fetchone()[0]
    conn.close()
    assert title == "A real paper title"


def test_missing_expected_table_raises(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    dest_path = tmp_path / "snapshot.sqlite3"
    conn = sqlite3.connect(source_path)
    conn.execute("CREATE TABLE papers (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    try:
        build_alpha_snapshot.build_snapshot(source_path, dest_path)
    except SystemExit as exc:
        assert "missing expected tables" in str(exc)
    else:
        raise AssertionError("expected SystemExit for a source database missing tables")
