from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path(__file__).parent.parent / "scripts" / "build_snapshot_metadata.py"
    spec = importlib.util.spec_from_file_location("build_snapshot_metadata", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_snapshot_metadata = _load_script()


def test_build_metadata_hashes_inputs_and_reads_graph_counts(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE graph_claims (id INTEGER PRIMARY KEY);
            CREATE TABLE graph_claim_relationships (id INTEGER PRIMARY KEY);
            CREATE TABLE graph_citations (id INTEGER PRIMARY KEY);
            INSERT INTO graph_claims VALUES (1), (2);
            INSERT INTO graph_claim_relationships VALUES (1);
            """
        )
    evidence = tmp_path / "evidence.jsonl"
    evidence.write_bytes(b'{"evidence_record_id":"ev-1"}\n')
    output = tmp_path / "snapshot_metadata.json"

    payload = build_snapshot_metadata.build_metadata(
        core_root=tmp_path,
        corpus_id="pilot",
        database=database,
        evidence=evidence,
        output=output,
    )

    assert payload["core_commit"] is None
    assert payload["claims_count"] == 2
    assert payload["relationships_count"] == 1
    assert payload["citations_count"] == 0
    assert str(payload["evidence_records_sha256"]).startswith("sha256:")
    assert json.loads(output.read_text(encoding="utf-8")) == payload
