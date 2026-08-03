"""Read-only access to `core`'s `RelationshipRecord` JSONL files.

`RelationshipRecord`s are plain JSONL objects `core` appends to a corpus
directory (e.g. `data/corpora/glp1_weight_loss/relationship_records.jsonl`),
never SQL rows -- same "no table for this in `knowledge_engine/models.py`"
fact `evidence_reader.py`'s own module docstring documents for
`EvidenceRecord`s, and the same reason this project reads the JSONL
directly rather than shelling out to `ke`. `core`'s `ke graph-build`
copies a relationship's `relationship_id`/`relationship_type`/`rationale`
into the `graph_claim_relationships` SQL table `graph_reader.py`'s
`RelationshipEdge` already reads and the claim-detail page already
renders -- but not `provenance` (who determined this relationship, and
how: manual review or automated) or `created_for_milestone`, since those
describe the record's own authorship, not a graph-queryable fact. This
module fills exactly that gap, matched against the SQL edge by the
`relationship_id` both share -- see `docs/web_design.md`'s "Decision:
RelationshipRecord rendering" section.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RelationshipRecordsError(RuntimeError):
    """A configured relationship-records file exists but could not be read."""


@dataclass(frozen=True)
class RelationshipRecordDetail:
    """One `RelationshipRecord`'s display fields -- stored fields only, nothing re-derived here."""

    relationship_id: str
    source_evidence_record_id: str
    target_evidence_record_id: str
    relationship_type: str
    rationale: str
    provenance: dict[str, Any]
    created_for_milestone: str | None


def list_relationship_records_for_evidence_record_id(
    path: Path, evidence_record_id: str
) -> list[RelationshipRecordDetail]:
    """Return every `RelationshipRecord` naming `evidence_record_id` as either side of the edge.

    A missing file or no match both return an empty list, matching
    `evidence_reader.read_evidence_record`'s "missing file is a real,
    expected state" posture -- `KE_WEB_RELATIONSHIP_RECORDS_PATH` is an
    optional setting. A malformed line in a file that does exist raises
    `RelationshipRecordsError`, since that is real corruption a caller
    should not silently paper over.
    """

    if not path.exists() or not evidence_record_id:
        return []

    matches: list[RelationshipRecordDetail] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RelationshipRecordsError(f"{path}:{line_number} is not valid JSON.") from exc
            source_id = record.get("source_evidence_record_id")
            target_id = record.get("target_evidence_record_id")
            if evidence_record_id in (source_id, target_id):
                matches.append(_to_detail(record))
    return matches


def _to_detail(record: dict[str, Any]) -> RelationshipRecordDetail:
    provenance = record.get("provenance")
    return RelationshipRecordDetail(
        relationship_id=str(record["relationship_id"]),
        source_evidence_record_id=str(record["source_evidence_record_id"]),
        target_evidence_record_id=str(record["target_evidence_record_id"]),
        relationship_type=str(record["relationship_type"]),
        rationale=str(record.get("rationale", "")),
        provenance=provenance if isinstance(provenance, dict) else {},
        created_for_milestone=record.get("created_for_milestone"),
    )
