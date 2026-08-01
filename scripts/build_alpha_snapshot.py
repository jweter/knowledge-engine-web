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

        dest.commit()
    finally:
        source.close()
        dest.close()


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
