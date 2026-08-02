#!/usr/bin/env python3
"""Build a small, committable alpha-deployment snapshot from `core`'s full database.

`core`'s real database is hundreds of megabytes -- mostly raw paper text and
embeddings this web app never reads. Render's Docker build clones this repo
directly from GitHub with no way to run a pre-build script, so the old
approach (a gitignored `./data/` populated locally before `docker build`)
can never reach Render's build machine; see docs/deployment.md's "Alpha
hosting (Render)" section. This script instead copies only the tables the
web app actually queries -- small enough to commit to the repo, so a plain
`git clone` already has it.

Table list must match knowledge_engine_web/graph_reader.py's
_GRAPH_TABLE_NAMES plus "papers" (also read there), plus "journals" --
not read directly, but SQLAlchemy's reflection follows papers.journal_id's
foreign key and errors if the referenced table isn't present. Keep in
sync with graph_reader.py and with core's actual schema.

Also copies `paper_search`, the FTS5 virtual table
`knowledge_engine_web/retrieval.py` queries for the /ask page -- handled
separately from TABLE_NAMES below since it is a virtual table (its
shadow tables aren't real content to copy row-for-row) and its rows
must keep the same rowid as `papers.id` for retrieval.py's
`JOIN papers p ON p.id = paper_search.rowid` to resolve correctly.

Only `title`/`abstract` content is copied into it, not `body_text`/
`raw_text` -- those two columns hold each paper's full parsed text and
dominate the size of `core`'s real database (~120 MB across today's
corpus, vs ~1.3 MB for title+abstract). The FTS5 table still declares
all four columns, matching `core`'s schema exactly so `retrieval.py`'s
`bm25(paper_search, 5.0, 3.0, 1.0, 0.5)` call (one weight per column,
copied verbatim from `core`'s own `SearchService`) needs no changes --
`body_text`/`raw_text` are just always empty here. This means the
alpha's /ask search only matches title/abstract text, not full body
text; a real `body_text`-backed index is what a live connection to
`core` (not a committed snapshot) will eventually restore.

Usage: scripts/build_alpha_snapshot.py <core-db-path> <output-db-path>
  e.g. scripts/build_alpha_snapshot.py \\
         /path/to/knowledge-engine-core/data/knowledge_engine.sqlite3 \\
         data/knowledge_engine.sqlite3
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

TABLE_NAMES = (
    "graph_concepts",
    "graph_claims",
    "graph_claim_concepts",
    "graph_claim_relationships",
    "graph_citations",
    "papers",
    "journals",
)

FTS_TABLE_NAME = "paper_search"
FTS_INDEXED_COLUMNS = ("title", "abstract")


def build_snapshot(source_path: Path, dest_path: Path) -> None:
    if dest_path.exists():
        dest_path.unlink()

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    dest = sqlite3.connect(dest_path)

    try:
        placeholders = ",".join("?" for _ in TABLE_NAMES)
        schema_rows = source.execute(
            f"SELECT name, type, sql FROM sqlite_master "
            f"WHERE tbl_name IN ({placeholders}) AND sql IS NOT NULL "
            f"ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END",
            TABLE_NAMES,
        ).fetchall()

        found_tables = {name for name, kind, _ in schema_rows if kind == "table"}
        missing = set(TABLE_NAMES) - found_tables
        if missing:
            raise SystemExit(f"Source database is missing expected tables: {sorted(missing)}")

        for _, _, sql in schema_rows:
            dest.execute(sql)

        for table in TABLE_NAMES:
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            placeholders = ",".join("?" for _ in rows[0])
            dest.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)

        _copy_full_text_index(source, dest)

        dest.commit()
    finally:
        source.close()
        dest.close()


def _copy_full_text_index(source: sqlite3.Connection, dest: sqlite3.Connection) -> None:
    """Recreate `paper_search` in `dest`, preserving each row's `papers.id` rowid.

    Copied via the FTS5 table's own row interface (`SELECT`/`INSERT`),
    not a raw shadow-table copy -- shadow tables encode SQLite's
    internal FTS5 segment/index bookkeeping, which isn't a stable
    format to depend on across databases or SQLite versions.
    """

    create_sql = source.execute(
        "SELECT sql FROM sqlite_master WHERE name = ? AND type = 'table'", (FTS_TABLE_NAME,)
    ).fetchone()
    if create_sql is None:
        raise SystemExit(f"Source database is missing expected table: {FTS_TABLE_NAME!r}")

    dest.execute(create_sql[0])

    columns = ", ".join(FTS_INDEXED_COLUMNS)
    rows = source.execute(f"SELECT rowid, {columns} FROM {FTS_TABLE_NAME}").fetchall()
    if not rows:
        return
    value_placeholders = ",".join(["?"] * (len(FTS_INDEXED_COLUMNS) + 1) + ["''", "''"])
    dest.executemany(
        f"INSERT INTO {FTS_TABLE_NAME}(rowid, {columns}, body_text, raw_text) "
        f"VALUES ({value_placeholders})",
        rows,
    )


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        raise SystemExit(1)

    source_path = Path(sys.argv[1])
    dest_path = Path(sys.argv[2])
    if not source_path.is_file():
        raise SystemExit(f"Not found: {source_path}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    build_snapshot(source_path, dest_path)
    size_kb = dest_path.stat().st_size / 1024
    print(f"Wrote {dest_path} ({size_kb:.0f} KB, tables: {', '.join(TABLE_NAMES)})")


if __name__ == "__main__":
    main()
