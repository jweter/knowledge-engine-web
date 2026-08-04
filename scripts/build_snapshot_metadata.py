"""Build committed, display-safe provenance metadata for the alpha snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def build_metadata(
    *,
    core_root: Path,
    corpus_id: str,
    database: Path,
    evidence: Path,
    output: Path,
    relationships: Path | None = None,
) -> dict[str, object]:
    """Build metadata from snapshot inputs without embedding private paths."""

    relationship_exists = relationships is not None and relationships.is_file()
    relationship_hash = _sha256(relationships) if relationships and relationship_exists else None
    payload: dict[str, object] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "corpus_id": corpus_id,
        "core_commit": _core_commit(core_root),
        "evidence_records_sha256": _sha256(evidence),
        "relationship_records_sha256": relationship_hash,
        "relationship_records_note": (
            None if relationship_exists else "Relationship JSONL was not included in this snapshot."
        ),
        **_graph_counts(database),
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _core_commit(core_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(core_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    commit = result.stdout.strip().lower()
    return commit if result.returncode == 0 and len(commit) == 40 else None


def _graph_counts(database: Path) -> dict[str, int]:
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

        def count(table: str) -> int:
            return (
                int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                if table in tables
                else 0
            )

        return {
            "claims_count": count("graph_claims"),
            "relationships_count": count("graph_claim_relationships"),
            "citations_count": count("graph_citations"),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("core_root", type=Path)
    parser.add_argument("corpus_id")
    parser.add_argument("database", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--relationships", type=Path)
    args = parser.parse_args()
    build_metadata(
        core_root=args.core_root,
        corpus_id=args.corpus_id,
        database=args.database,
        evidence=args.evidence,
        output=args.output,
        relationships=args.relationships,
    )


if __name__ == "__main__":
    main()
