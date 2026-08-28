"""Prepare deploy-time metadata and durable alpha research state.

The committed Render image contains a read-only-ish point-in-time snapshot for
normal Web retrieval. Research Copilot additionally needs a writable Evidence
Record file and ``sources.csv`` metadata. This module prepares those inputs
without pretending the image contains a complete Core runtime.

A real persistent root must already exist. The seeding path never creates that
root, so an ephemeral deployment cannot accidentally satisfy the persistence
contract merely by creating ``/var/data`` itself.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AlphaWorkspaceError(RuntimeError):
    """The alpha research workspace could not be prepared safely."""


@dataclass(frozen=True)
class SeedResult:
    """Paths made ready inside an operator-provided persistent root."""

    evidence_path: Path
    sources_path: Path
    research_papers_dir: Path
    discovery_ledger_root: Path


def build_sources_snapshot(database_path: Path, output_path: Path) -> int:
    """Build Core-compatible ``sources.csv`` from the committed paper snapshot.

    Core's public CLI contract requires only ``doi`` and ``title`` columns for
    this display metadata overlay. Rows without a DOI cannot participate in the
    DOI-keyed overlay and are omitted. Duplicate DOI spellings collapse through
    a small normalization step so the generated file stays deterministic.
    """

    if not database_path.is_file():
        raise AlphaWorkspaceError(f"Snapshot database is not a file: {database_path}")

    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise AlphaWorkspaceError("Could not open the snapshot database read-only.") from exc

    try:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(papers)").fetchall()
        }
        missing = {"doi", "title"} - columns
        if missing:
            raise AlphaWorkspaceError(
                "Snapshot papers table is missing required column(s): " + ", ".join(sorted(missing))
            )
        rows = connection.execute(
            "SELECT doi, title FROM papers "
            "WHERE doi IS NOT NULL AND trim(doi) <> '' "
            "ORDER BY lower(doi), rowid"
        ).fetchall()
    except sqlite3.Error as exc:
        raise AlphaWorkspaceError("Could not read paper metadata from the snapshot database.") from exc
    finally:
        connection.close()

    records: list[tuple[str, str]] = []
    seen: set[str] = set()
    for doi_value, title_value in rows:
        doi = _normalize_doi(str(doi_value))
        if not doi or doi in seen:
            continue
        seen.add(doi)
        records.append((doi, str(title_value or "").strip()))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", newline="", encoding="utf-8", dir=output_path.parent, delete=False
    ) as handle:
        temporary_path = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=("doi", "title"), lineterminator="\n")
        writer.writeheader()
        for doi, title in records:
            writer.writerow({"doi": doi, "title": title})
    temporary_path.replace(output_path)
    return len(records)


def seed_persistent_workspace(snapshot_root: Path, persistent_root: Path) -> SeedResult:
    """Seed durable Research Copilot files into an existing persistent mount.

    Baseline Evidence Records are merged by ``evidence_record_id`` rather than
    overwriting the durable file. This preserves records promoted by earlier
    research runs while allowing later image snapshots to contribute newly
    committed baseline records after a redeploy.
    """

    if not persistent_root.is_dir():
        raise AlphaWorkspaceError("Persistent research root is not mounted as a directory.")

    baseline_evidence = snapshot_root / "evidence_records.jsonl"
    baseline_sources = snapshot_root / "sources.csv"
    if not baseline_evidence.is_file() or not baseline_sources.is_file():
        raise AlphaWorkspaceError("Alpha image is missing required research seed files.")

    evidence_path = persistent_root / "evidence_records.jsonl"
    sources_path = persistent_root / "sources.csv"
    _merge_evidence_records(baseline_evidence, evidence_path)
    _atomic_copy(baseline_sources, sources_path)

    research_papers_dir = persistent_root / "research_papers"
    discovery_ledger_root = persistent_root / "federated_discovery_runs"
    research_papers_dir.mkdir(exist_ok=True)
    discovery_ledger_root.mkdir(exist_ok=True)

    return SeedResult(
        evidence_path=evidence_path,
        sources_path=sources_path,
        research_papers_dir=research_papers_dir,
        discovery_ledger_root=discovery_ledger_root,
    )


def _merge_evidence_records(baseline_path: Path, durable_path: Path) -> None:
    baseline_lines, baseline_ids = _validated_jsonl(baseline_path)
    if not durable_path.exists():
        _atomic_write_lines(durable_path, baseline_lines)
        return
    if not durable_path.is_file():
        raise AlphaWorkspaceError("Durable Evidence Record path is not a regular file.")

    durable_lines, durable_ids = _validated_jsonl(durable_path)
    missing_lines = [
        line for line, record_id in zip(baseline_lines, baseline_ids, strict=True)
        if record_id not in durable_ids
    ]
    if missing_lines:
        _atomic_write_lines(durable_path, [*durable_lines, *missing_lines])


def _validated_jsonl(path: Path) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    record_ids: list[str] = []
    seen: set[str] = set()
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise AlphaWorkspaceError(f"Could not read JSONL seed file: {path.name}") from exc

    for line_number, raw_line in enumerate(raw_lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload: Any = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AlphaWorkspaceError(
                f"{path.name} contains invalid JSON on line {line_number}."
            ) from exc
        if not isinstance(payload, dict):
            raise AlphaWorkspaceError(f"{path.name} line {line_number} is not a JSON object.")
        record_id = payload.get("evidence_record_id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise AlphaWorkspaceError(
                f"{path.name} line {line_number} has no evidence_record_id."
            )
        normalized_id = record_id.strip()
        if normalized_id in seen:
            continue
        seen.add(normalized_id)
        lines.append(line)
        record_ids.append(normalized_id)
    return lines, record_ids


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=destination.parent, delete=False) as handle:
        temporary_path = Path(handle.name)
        with source.open("rb") as source_handle:
            shutil.copyfileobj(source_handle, handle)
    temporary_path.replace(destination)


def _atomic_write_lines(destination: Path, lines: list[str]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent, delete=False) as handle:
        temporary_path = Path(handle.name)
        for line in lines:
            handle.write(line)
            handle.write("\n")
    temporary_path.replace(destination)


def _normalize_doi(value: str) -> str:
    normalized = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            break
    return normalized


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sources = subparsers.add_parser("build-sources")
    sources.add_argument("--database", type=Path, required=True)
    sources.add_argument("--output", type=Path, required=True)

    seed = subparsers.add_parser("seed")
    seed.add_argument("--snapshot-root", type=Path, required=True)
    seed.add_argument("--persistent-root", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        if args.command == "build-sources":
            count = build_sources_snapshot(args.database, args.output)
            print(f"Prepared {count} DOI metadata rows at {args.output}.")
        else:
            result = seed_persistent_workspace(args.snapshot_root, args.persistent_root)
            print(f"Prepared persistent research workspace at {result.evidence_path.parent}.")
    except AlphaWorkspaceError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
