"""Read-only polling view over knowledge-engine-ai's durable Research Session store.

WEB-GQR-4 (`docs/general_question_research_loop_v1.md`): the Ask UI must move
toward a durable job/session polling model rather than extending HTTP request
timeouts indefinitely, with session identity and stage progress surviving
refresh/redeploy where persistent storage is configured.

That durable storage already exists and does not need to be rebuilt here.
`knowledge-engine-ai`'s ``SessionRepository`` (see ``ai_orchestration.py``)
already persists one ``ResearchSession`` header row plus one ``ResearchEvent``
row per completed workflow step to ``Settings.session_db_path``, committing
each row as the still-synchronous ``/ask?synthesize=1`` request executes --
durable (a real SQLite file, not in-memory), and already covered by the
existing ``session_storage_mode``/``session_persistent_root`` local/persistent
split that lets it survive a Render redeploy when a persistent disk is
provisioned. Building a second, Web-owned session store next to that one
would just create two disagreeing sources of truth for the same identity.

This module is instead a strictly read-only projection of that same store,
opened ``mode=ro`` so this process can never write into it here -- writes stay
exactly where they already are, inside ``run_ai_orchestration``'s own guarded
path. It is the read side a new ``GET /ask/session/{session_id}`` polling
route can use to look up a session's durably recorded progress independently
of the request that created it. Wiring a frontend polling loop onto that
route, and moving execution itself off the request/response cycle and onto a
background task, remain later WEB-GQR-4 slices.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Mirrors docs/general_question_research_loop_v1.md's "Recommended
# visitor-facing progression" list, keyed by the exact workflow_node values
# knowledge-engine-ai's ResearchEvent rows already use (see
# orchestrator/workflow.py, copilot/discovery_policy.py, and
# copilot/run_research_question.py in the pinned knowledge-engine-ai
# dependency). Not an independent guess at stage names: this is the same
# durable vocabulary the session trace already renders on /ask today.
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

# Verbatim from knowledge-engine-ai's SessionStatus.is_terminal_status: a
# status a session cannot resume from. Duplicated as plain strings rather
# than importing the enum so this read-only view has no dependency on the
# rest of that module's write-path machinery.
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "superseded"})


@dataclass(frozen=True)
class SessionStatusView:
    """One session's durably recorded progress, as of the moment it was read.

    `last_completed_stage` names the most recent workflow step this store has
    a *completed* `ResearchEvent` row for -- never a live "currently
    executing" stage, because nothing durably records a step's start, only
    its completion. For a non-terminal (still-running) session this is one
    step behind whatever is actually in flight right now; for a terminal
    session (`terminal` is True) it is exactly the last step that ran. `None`
    means no step has completed yet (the session was just created).
    """

    session_id: str
    question: str
    status: str
    last_completed_stage: str | None
    terminal: bool
    created_at: str
    updated_at: str
    event_count: int
    latest_workflow_node: str | None


def read_session_status(session_db_path: str, session_id: str) -> SessionStatusView | None:
    """Return `session_id`'s durably persisted state, or `None` if it is unknown.

    Returns `None` -- never raises -- both when no session with this ID was
    ever created and when the store itself does not exist yet (a deployment
    where no research session has ever run, or a session store rolled back to
    an unreadable state). Both cases render as the same honest "not found" to
    a caller; a polling client cannot distinguish "never happened" from
    "durable store currently unreadable" and should not be asked to.
    """

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
            event_rows = connection.execute(
                "SELECT workflow_node FROM research_events WHERE session_id = ? "
                "ORDER BY sequence_number",
                (session_id,),
            ).fetchall()
        except sqlite3.DatabaseError:
            # Store exists as a file but is unreadable as this schema -- e.g.
            # an empty/out-of-band file, or (SQLite opens lazily, so this can
            # surface only here rather than at connect() above) a file that
            # is not a database at all. Same honest "not found" either way.
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

    return SessionStatusView(
        session_id=str(session_row["session_id"]),
        question=str(session_row["user_question_original"]),
        status=status,
        last_completed_stage=last_completed_stage,
        terminal=status in _TERMINAL_STATUSES,
        created_at=str(session_row["created_at"]),
        updated_at=str(session_row["updated_at"]),
        event_count=len(event_rows),
        latest_workflow_node=latest_workflow_node,
    )


__all__ = ["SessionStatusView", "read_session_status"]
