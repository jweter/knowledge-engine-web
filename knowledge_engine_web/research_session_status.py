"""Read-only polling view over knowledge-engine-ai's durable Research Session store.

WEB-GQR-4 (`docs/general_question_research_loop_v1.md`): the Ask UI must move
toward a durable job/session polling model rather than extending HTTP request
timeouts indefinitely, with session identity and stage progress surviving
refresh/redeploy where persistent storage is configured.

The durable source of truth already exists in knowledge-engine-ai's
``SessionRepository``. This module is a strictly read-only projection of that
same SQLite store, opened ``mode=ro``. Besides stage/status metadata, it may
return the final synthesis text and citation identities *only* when the durable
session status is ``completed``. A blocked or otherwise unreleased session can
therefore never leak a draft narrative merely because a synthesis event exists.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_STAGE_LABELS: dict[str, str] = {
    "retrieval_and_evidence_intelligence": "Searching indexed evidence",
    "contradiction_oriented_retrieval": "Searching indexed evidence",
    "evidence_map": "Searching indexed evidence",
    "statistical_verification": "Searching indexed evidence",
    "federated_discovery": "Indexed evidence is thin; expanding the literature search",
    "citation_snowball": "Searching scholarly providers",
    "acquisition_plan": "Validating and acquiring eligible sources",
    "grounded_acquisition": "Validating and acquiring eligible sources",
    "grounded_extraction": "Extracting grounded evidence",
    "grounded_reretrieval": "Re-checking the original question against the enlarged evidence base",
    "synthesis": "Preparing and verifying a source-grounded answer",
}

# Mirrors knowledge-engine-ai's non-resumable terminal states. BLOCKED is
# intentionally not terminal there because a durable session may be resumed.
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "superseded"})
_ACTIVE_STATUSES = frozenset({"pending", "running"})


@dataclass(frozen=True)
class SessionStatusView:
    """One session's durably recorded progress, as of the moment it was read.

    ``last_completed_stage`` names the most recent completed ResearchEvent,
    never a guessed in-flight stage. ``execution_finished`` is distinct from
    ``terminal``: a BLOCKED/AWAITING session is resumable in AI's lifecycle,
    but the HTTP-started execution that produced it is no longer actively
    running and a browser polling loop should stop spinning.

    ``released_narrative`` and its citation IDs are populated only for a
    COMPLETED session whose latest synthesis event succeeded.
    """

    session_id: str
    question: str
    status: str
    last_completed_stage: str | None
    terminal: bool
    execution_finished: bool
    created_at: str
    updated_at: str
    event_count: int
    latest_workflow_node: str | None
    recorded_duration_ms: int
    released_narrative: str | None = None
    released_source_ids: tuple[str, ...] = ()
    released_source_dois: tuple[str, ...] = ()


def read_session_status(session_db_path: str, session_id: str) -> SessionStatusView | None:
    """Return ``session_id``'s durable state, or ``None`` if the store/session is unreadable."""

    database_path = Path(session_db_path)
    if not database_path.is_file():
        return None

    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    except sqlite3.DatabaseError:
        return None

    try:
        connection.row_factory = sqlite3.Row
        try:
            session_row = connection.execute(
                "SELECT session_id, user_question_original, status, created_at, updated_at "
                "FROM research_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None:
                return None

            event_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(research_events)").fetchall()
            }
            source_dois_expression = (
                "source_dois" if "source_dois" in event_columns else "'[]' AS source_dois"
            )
            duration_expression = (
                "duration_ms" if "duration_ms" in event_columns else "NULL AS duration_ms"
            )
            event_rows = connection.execute(
                "SELECT workflow_node, validation_status, notes, source_ids, "
                f"{source_dois_expression}, {duration_expression} "
                "FROM research_events WHERE session_id = ? ORDER BY sequence_number",
                (session_id,),
            ).fetchall()
        except sqlite3.DatabaseError:
            return None
    finally:
        connection.close()

    latest_workflow_node = str(event_rows[-1]["workflow_node"]) if event_rows else None
    status = str(session_row["status"])
    last_completed_stage = (
        _STAGE_LABELS.get(latest_workflow_node, f"Researching ({latest_workflow_node})")
        if latest_workflow_node is not None
        else None
    )
    recorded_duration_ms = sum(
        int(row["duration_ms"])
        for row in event_rows
        if row["duration_ms"] is not None and int(row["duration_ms"]) >= 0
    )

    released_narrative: str | None = None
    released_source_ids: tuple[str, ...] = ()
    released_source_dois: tuple[str, ...] = ()
    if status == "completed":
        synthesis_rows = tuple(
            row
            for row in event_rows
            if row["workflow_node"] == "synthesis" and row["validation_status"] == "succeeded"
        )
        if synthesis_rows:
            synthesis = synthesis_rows[-1]
            notes = synthesis["notes"]
            if isinstance(notes, str) and notes.strip():
                released_narrative = notes
                released_source_ids = _json_string_tuple(synthesis["source_ids"])
                released_source_dois = _json_string_tuple(synthesis["source_dois"])

    return SessionStatusView(
        session_id=str(session_row["session_id"]),
        question=str(session_row["user_question_original"]),
        status=status,
        last_completed_stage=last_completed_stage,
        terminal=status in _TERMINAL_STATUSES,
        execution_finished=status not in _ACTIVE_STATUSES,
        created_at=str(session_row["created_at"]),
        updated_at=str(session_row["updated_at"]),
        event_count=len(event_rows),
        latest_workflow_node=latest_workflow_node,
        recorded_duration_ms=recorded_duration_ms,
        released_narrative=released_narrative,
        released_source_ids=released_source_ids,
        released_source_dois=released_source_dois,
    )


def _json_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        return ()
    return tuple(payload)


__all__ = ["SessionStatusView", "read_session_status"]
