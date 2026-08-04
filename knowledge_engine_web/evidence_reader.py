"""Read-only access to `core`'s `EvidenceRecord` JSONL files.

`EvidenceRecord`s are plain JSONL objects `core` appends to a corpus
directory (e.g. `data/corpora/glp1_weight_loss/evidence_records.jsonl`),
never SQL rows -- see `docs/web_design.md`'s "Prerequisite" section and
`core`'s own `knowledge_engine/models.py`, which has no `EvidenceRecord`
table at all. Reading the configured JSONL path directly
(`KE_WEB_EVIDENCE_RECORDS_PATH`) rather than shelling out to `ke
evidence-report --output` keeps this project's whole read path
process-free, matching the direct-SQLite-reflection approach
`graph_reader.py` already uses -- and resolves `web_design.md`'s
deferred Open Question on how this project would read one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class EvidenceRecordsError(RuntimeError):
    """A configured evidence-records file exists but could not be read."""


@dataclass(frozen=True)
class EvidenceRecordDetail:
    """The evidence content behind one claim -- stored fields only, nothing re-derived here."""

    evidence_record_id: str
    research_question: str | None
    claim_text: str | None
    evidence_direction: str | None
    study_type: str | None
    source_type: str | None
    source_title: str | None
    source_doi: str | None
    population: str | None
    intervention: str | None
    comparator: str | None
    outcome: str | None
    result_summary: str | None
    short_source_excerpt: str | None
    limitations: list[str]
    uncertainty_notes: str | None
    confidence_note: str | None
    extraction_method: str | None
    extraction_status: str | None
    review_status: str | None
    review_checklist: dict[str, Any]


def read_evidence_record(path: Path, evidence_record_id: str) -> EvidenceRecordDetail | None:
    """Return one `EvidenceRecord`'s display fields, or `None` if not found.

    A missing file is a real, expected state -- `KE_WEB_EVIDENCE_RECORDS_PATH`
    is an optional setting -- so a missing file or an unmatched ID both
    return `None` rather than raising, matching `graph_reader`'s "missing
    table means empty, not an error" posture. A malformed line in a file
    that does exist raises `EvidenceRecordsError`, since that is real
    corruption a caller should not silently paper over.
    """

    if not path.exists():
        return None

    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceRecordsError(f"{path}:{line_number} is not valid JSON.") from exc
            if record.get("evidence_record_id") == evidence_record_id:
                return _to_detail(record)
    return None


def list_evidence_records_for_doi(path: Path, doi: str) -> list[EvidenceRecordDetail]:
    """Return every `EvidenceRecord` whose `source_doi` matches, normalized for comparison.

    One paper can have several evidence records (e.g. one manually
    reviewed, one automated), matching `core`'s own
    `_index_evidence_records_by_doi`'s one-DOI-to-many-records shape
    (`knowledge_engine/cli.py`) -- ported here rather than imported, same
    reasoning as `retrieval.py`. A missing file or no match both return
    an empty list, matching `read_evidence_record`'s "missing is a real,
    expected state" posture.
    """

    if not path.exists() or not doi:
        return []

    normalized_target = normalize_doi(doi)
    matches: list[EvidenceRecordDetail] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceRecordsError(f"{path}:{line_number} is not valid JSON.") from exc
            record_doi = record.get("source_doi")
            if isinstance(record_doi, str) and normalize_doi(record_doi) == normalized_target:
                matches.append(_to_detail(record))
    return matches


def index_evidence_records_by_doi(path: Path) -> dict[str, tuple[EvidenceRecordDetail, ...]]:
    """Read Evidence Records once and group them by normalized source DOI.

    Retrieval reranking evaluates a bounded set of papers at once. Building one
    immutable index avoids rescanning the JSONL file for every candidate while
    preserving the same corruption behavior as the single-DOI reader.
    """

    if not path.exists():
        return {}

    records_by_doi: dict[str, list[EvidenceRecordDetail]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceRecordsError(f"{path}:{line_number} is not valid JSON.") from exc
            record_doi = record.get("source_doi")
            if not isinstance(record_doi, str) or not record_doi.strip():
                continue
            normalized_doi = normalize_doi(record_doi)
            records_by_doi.setdefault(normalized_doi, []).append(_to_detail(record))

    return {doi: tuple(records) for doi, records in records_by_doi.items()}


def normalize_doi(doi: str) -> str:
    """Normalize a DOI for deterministic comparison, matching `core`'s own `normalize_doi`."""

    return (
        doi.strip()
        .lower()
        .removeprefix("https://doi.org/")
        .removeprefix("http://doi.org/")
        .removeprefix("doi:")
    )


def count_evidence_records(path: Path) -> int:
    """Return the total number of records in an `EvidenceRecord` JSONL file.

    Used only for corpus-relative Evidence Coverage
    (`knowledge_engine_web/evidence_intelligence.py`) -- a missing file
    counts as zero rather than raising, matching `read_evidence_record`'s
    own "missing file is a real, expected state" posture.
    """

    if not path.exists():
        return 0
    count = 0
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            if raw_line.strip():
                count += 1
    return count


def _to_detail(record: dict[str, Any]) -> EvidenceRecordDetail:
    limitations = record.get("limitations")
    review_checklist = record.get("review_checklist")
    return EvidenceRecordDetail(
        evidence_record_id=str(record["evidence_record_id"]),
        research_question=record.get("research_question"),
        claim_text=record.get("claim_text"),
        evidence_direction=record.get("evidence_direction"),
        study_type=record.get("study_type"),
        source_type=record.get("source_type"),
        source_title=record.get("source_title"),
        source_doi=record.get("source_doi"),
        population=record.get("population"),
        intervention=record.get("intervention"),
        comparator=record.get("comparator"),
        outcome=record.get("outcome"),
        result_summary=record.get("result_summary"),
        short_source_excerpt=record.get("short_source_excerpt"),
        limitations=list(limitations) if isinstance(limitations, list) else [],
        uncertainty_notes=record.get("uncertainty_notes"),
        confidence_note=record.get("confidence_note"),
        extraction_method=record.get("extraction_method"),
        extraction_status=record.get("extraction_status"),
        review_status=record.get("review_status"),
        review_checklist=review_checklist if isinstance(review_checklist, dict) else {},
    )
