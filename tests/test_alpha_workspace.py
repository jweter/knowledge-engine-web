from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from knowledge_engine_web.alpha_workspace import (
    AlphaWorkspaceError,
    build_sources_snapshot,
    seed_persistent_workspace,
)


def _paper_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            doi TEXT
        );
        INSERT INTO papers VALUES (1, 'First paper', '10.1000/ABC');
        INSERT INTO papers VALUES (2, 'Duplicate spelling', 'https://doi.org/10.1000/abc');
        INSERT INTO papers VALUES (3, 'Second paper', '10.2000/xyz');
        INSERT INTO papers VALUES (4, 'No DOI', NULL);
        """
    )
    connection.commit()
    connection.close()


def _record(record_id: str, claim: str) -> str:
    return json.dumps({"evidence_record_id": record_id, "claim_text": claim})


def test_build_sources_snapshot_is_deterministic_and_deduplicates_dois(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite3"
    output = tmp_path / "sources.csv"
    _paper_database(database)

    count = build_sources_snapshot(database, output)

    assert count == 2
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {"doi": "10.1000/abc", "title": "First paper"},
        {"doi": "10.2000/xyz", "title": "Second paper"},
    ]


def test_build_sources_snapshot_requires_core_overlay_columns(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE papers (id INTEGER PRIMARY KEY, title TEXT NOT NULL)")
    connection.commit()
    connection.close()

    with pytest.raises(AlphaWorkspaceError, match="doi"):
        build_sources_snapshot(database, tmp_path / "sources.csv")


def test_seed_requires_an_existing_persistent_mount(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()

    with pytest.raises(AlphaWorkspaceError, match="not mounted"):
        seed_persistent_workspace(snapshot_root, tmp_path / "missing-persistent-root")


def test_seed_prepares_research_inputs_without_overwriting_durable_evidence(
    tmp_path: Path,
) -> None:
    snapshot_root = tmp_path / "snapshot"
    persistent_root = tmp_path / "persistent"
    snapshot_root.mkdir()
    persistent_root.mkdir()

    (snapshot_root / "sources.csv").write_text(
        "doi,title\n10.1000/a,Snapshot paper\n", encoding="utf-8"
    )
    (snapshot_root / "evidence_records.jsonl").write_text(
        _record("ev-base-a", "baseline A") + "\n", encoding="utf-8"
    )
    durable_evidence = persistent_root / "evidence_records.jsonl"
    durable_evidence.write_text(
        _record("ev-research", "promoted research") + "\n", encoding="utf-8"
    )

    result = seed_persistent_workspace(snapshot_root, persistent_root)

    records = [
        json.loads(line) for line in durable_evidence.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["evidence_record_id"] for record in records] == ["ev-research", "ev-base-a"]
    assert result.evidence_path == durable_evidence
    assert result.sources_path.read_text(encoding="utf-8") == (
        "doi,title\n10.1000/a,Snapshot paper\n"
    )
    assert result.research_papers_dir.is_dir()
    assert result.discovery_ledger_root.is_dir()


def test_reseed_adds_new_baseline_records_and_keeps_prior_research_records(
    tmp_path: Path,
) -> None:
    snapshot_root = tmp_path / "snapshot"
    persistent_root = tmp_path / "persistent"
    snapshot_root.mkdir()
    persistent_root.mkdir()
    (snapshot_root / "sources.csv").write_text("doi,title\n", encoding="utf-8")
    evidence_seed = snapshot_root / "evidence_records.jsonl"
    evidence_seed.write_text(_record("ev-base-a", "baseline A") + "\n", encoding="utf-8")

    seed_persistent_workspace(snapshot_root, persistent_root)
    durable_evidence = persistent_root / "evidence_records.jsonl"
    with durable_evidence.open("a", encoding="utf-8") as handle:
        handle.write(_record("ev-research", "promoted research") + "\n")

    evidence_seed.write_text(
        _record("ev-base-a", "baseline A") + "\n" + _record("ev-base-b", "baseline B") + "\n",
        encoding="utf-8",
    )
    seed_persistent_workspace(snapshot_root, persistent_root)

    records = [
        json.loads(line) for line in durable_evidence.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["evidence_record_id"] for record in records] == [
        "ev-base-a",
        "ev-research",
        "ev-base-b",
    ]


def test_seed_fails_closed_on_corrupt_durable_evidence(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshot"
    persistent_root = tmp_path / "persistent"
    snapshot_root.mkdir()
    persistent_root.mkdir()
    (snapshot_root / "sources.csv").write_text("doi,title\n", encoding="utf-8")
    (snapshot_root / "evidence_records.jsonl").write_text(
        _record("ev-base", "baseline") + "\n", encoding="utf-8"
    )
    durable_evidence = persistent_root / "evidence_records.jsonl"
    durable_evidence.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(AlphaWorkspaceError, match="invalid JSON"):
        seed_persistent_workspace(snapshot_root, persistent_root)

    assert durable_evidence.read_text(encoding="utf-8") == "not-json\n"


def test_dockerfile_builds_sources_and_uses_persistent_aware_startup() -> None:
    root = Path(__file__).parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    startup = (root / "scripts" / "start-alpha.sh").read_text(encoding="utf-8")

    assert "alpha_workspace build-sources" in dockerfile
    assert "KE_WEB_SOURCES_PATH=/app/data/sources.csv" in dockerfile
    assert 'CMD ["/app/scripts/start-alpha.sh"]' in dockerfile
    assert "alpha_workspace seed" in startup
    assert (
        'export KE_WEB_EVIDENCE_RECORDS_PATH="$persistent_root/evidence_records.jsonl"' in startup
    )
    assert 'export KE_WEB_SOURCES_PATH="$persistent_root/sources.csv"' in startup
