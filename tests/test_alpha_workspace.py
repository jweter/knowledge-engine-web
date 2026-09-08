from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from knowledge_engine_web.alpha_workspace import (
    AlphaWorkspaceError,
    build_sources_snapshot,
    seed_persistent_workspace,
)


def _record(record_id: str, title: str) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "evidence_record_id": record_id,
            "created_at": "2026-09-07T00:00:00+00:00",
            "created_by": "test",
            "title": title,
            "description": "test evidence",
            "source_type": "derived",
            "source_locator": "test",
            "source_version": "1",
            "source_sha256": "a" * 64,
            "content_sha256": "b" * 64,
            "canonical": True,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _write_papers_db(path: Path, rows: list[tuple[str, str]]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE papers (doi TEXT, title TEXT NOT NULL)")
        connection.executemany("INSERT INTO papers (doi, title) VALUES (?, ?)", rows)
        connection.commit()
    finally:
        connection.close()


def test_build_sources_csv_uses_public_papers_metadata(tmp_path: Path) -> None:
    database = tmp_path / "knowledge_engine.sqlite3"
    output = tmp_path / "sources.csv"
    _write_papers_db(database, [("10.2/b", "Beta"), ("10.1/a", "Alpha"), ("", "Skip")])

    count = build_sources_snapshot(database, output)

    assert count == 2
    assert output.read_text(encoding="utf-8").splitlines() == [
        "doi,title",
        "10.1/a,Alpha",
        "10.2/b,Beta",
    ]


def test_seed_creates_durable_workspace_from_snapshot(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshot"
    persistent_root = tmp_path / "persistent"
    snapshot_root.mkdir()
    persistent_root.mkdir()
    (snapshot_root / "sources.csv").write_text("doi,title\n10.1/a,Alpha\n", encoding="utf-8")
    (snapshot_root / "evidence_records.jsonl").write_text(
        _record("ev-base", "baseline") + "\n", encoding="utf-8"
    )

    seed_persistent_workspace(snapshot_root, persistent_root)

    assert (persistent_root / "sources.csv").read_text(
        encoding="utf-8"
    ) == "doi,title\n10.1/a,Alpha\n"
    assert (
        json.loads((persistent_root / "evidence_records.jsonl").read_text(encoding="utf-8"))[
            "evidence_record_id"
        ]
        == "ev-base"
    )


def test_seed_preserves_research_evidence_and_adds_new_snapshot_records(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshot"
    persistent_root = tmp_path / "persistent"
    snapshot_root.mkdir()
    persistent_root.mkdir()
    (snapshot_root / "sources.csv").write_text("doi,title\n10.1/a,Alpha\n", encoding="utf-8")
    (snapshot_root / "evidence_records.jsonl").write_text(
        "\n".join([_record("ev-base-a", "baseline a"), _record("ev-base-b", "baseline b")]) + "\n",
        encoding="utf-8",
    )
    (persistent_root / "evidence_records.jsonl").write_text(
        "\n".join([_record("ev-base-a", "baseline a"), _record("ev-research", "research")]) + "\n",
        encoding="utf-8",
    )

    seed_persistent_workspace(snapshot_root, persistent_root)

    durable_evidence = persistent_root / "evidence_records.jsonl"
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
    assert "KE_WEB_KE_EXECUTABLE=/opt/ke-research/bin/ke-research" in dockerfile
    assert "ke-research-workspace" in startup
    assert 'CMD ["/app/scripts/start-alpha.sh"]' in dockerfile
    assert "alpha_workspace seed" in startup
    assert 'export KE_WEB_EVIDENCE_RECORDS_PATH="$core_workspace/evidence_records.jsonl"' in startup
    assert 'export KE_WEB_SOURCES_PATH="$persistent_root/sources.csv"' in startup
