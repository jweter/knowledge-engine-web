"""Read the public snapshot's committed provenance metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SnapshotMetadata:
    """Validated, display-safe identity for one deployed snapshot."""

    generated_at: str
    corpus_id: str
    core_commit: str | None
    evidence_records_sha256: str
    relationship_records_sha256: str | None
    relationship_records_note: str | None
    claims_count: int
    relationships_count: int
    citations_count: int


@dataclass(frozen=True)
class SnapshotMetadataResult:
    metadata: SnapshotMetadata | None
    unavailable_reason: str | None


def read_snapshot_metadata(path: Path) -> SnapshotMetadataResult:
    """Return validated metadata without exposing paths or raising for expected failures."""

    if not path.is_file():
        return SnapshotMetadataResult(None, "Snapshot metadata is not available.")
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        metadata = _validate(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        return SnapshotMetadataResult(None, "Snapshot metadata is unavailable or invalid.")
    return SnapshotMetadataResult(metadata, None)


def _validate(payload: Any) -> SnapshotMetadata:
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int:
        raise ValueError("Invalid metadata envelope")
    if payload["schema_version"] != 1:
        raise ValueError("Unsupported metadata version")

    generated_at = _text(payload, "generated_at")
    parsed_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    if parsed_at.tzinfo is None:
        raise ValueError("generated_at must include a timezone")

    relationship_hash = payload.get("relationship_records_sha256")
    relationship_note = payload.get("relationship_records_note")
    if relationship_hash is not None:
        relationship_hash = _hash(relationship_hash)
    elif not isinstance(relationship_note, str) or not relationship_note.strip():
        raise ValueError("Missing relationship snapshot explanation")

    core_commit = payload.get("core_commit")
    if core_commit is not None and (
        not isinstance(core_commit, str)
        or len(core_commit) != 40
        or any(char not in "0123456789abcdef" for char in core_commit)
    ):
        raise ValueError("Invalid core commit")

    return SnapshotMetadata(
        generated_at=generated_at,
        corpus_id=_text(payload, "corpus_id"),
        core_commit=core_commit,
        evidence_records_sha256=_hash(payload.get("evidence_records_sha256")),
        relationship_records_sha256=relationship_hash,
        relationship_records_note=(
            relationship_note.strip() if isinstance(relationship_note, str) else None
        ),
        claims_count=_count(payload, "claims_count"),
        relationships_count=_count(payload, "relationships_count"),
        citations_count=_count(payload, "citations_count"),
    )


def _text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid {field}")
    return value.strip()


def _hash(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError("Invalid hash")
    if any(char not in "0123456789abcdef" for char in value[7:]):
        raise ValueError("Invalid hash")
    return value


def _count(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {field}")
    return value
