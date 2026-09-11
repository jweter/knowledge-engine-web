"""Durable storage for one human Mobile Product Reality review per research session.

A review is deliberately keyed to the same durable `session_id` the async
Research job already uses (`research_jobs.py`), in the same session database,
so a phone reviewer's PASS/FAIL/FLAG verdict stays tied to the exact session
that produced the evidence they reviewed -- never a separate, driftable
identity.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_mobile_reviews (
    session_id TEXT PRIMARY KEY,
    review TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL
);
"""

NOTES_MAX_LENGTH = 4000


@dataclass(frozen=True)
class MobileReviewRecord:
    review: str
    notes: str
    reviewed_at: str


def record_mobile_review(
    session_db_path: str, session_id: str, review: str, notes: str
) -> MobileReviewRecord:
    """Persist (or overwrite) the human review for one session."""

    now = datetime.now(UTC).isoformat()
    trimmed_notes = notes.strip()[:NOTES_MAX_LENGTH]
    connection = _new_connection(session_db_path)
    try:
        _ensure_schema(connection)
        connection.execute(
            """
            INSERT INTO web_mobile_reviews (session_id, review, notes, reviewed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                review = excluded.review,
                notes = excluded.notes,
                reviewed_at = excluded.reviewed_at
            """,
            (session_id, review, trimmed_notes, now),
        )
        connection.commit()
    finally:
        connection.close()
    return MobileReviewRecord(review=review, notes=trimmed_notes, reviewed_at=now)


def read_mobile_review(session_db_path: str, session_id: str) -> MobileReviewRecord | None:
    """Read a stored review without creating or mutating the review table."""

    database_path = Path(session_db_path)
    if not database_path.is_file():
        return None
    try:
        connection = sqlite3.connect(
            f"file:{database_path}?mode=ro",
            uri=True,
            timeout=5.0,
        )
    except sqlite3.DatabaseError:
        return None
    connection.row_factory = sqlite3.Row
    try:
        try:
            row = connection.execute(
                "SELECT review, notes, reviewed_at FROM web_mobile_reviews WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        except sqlite3.DatabaseError:
            return None
    finally:
        connection.close()
    if row is None:
        return None
    return MobileReviewRecord(
        review=str(row["review"]), notes=str(row["notes"]), reviewed_at=str(row["reviewed_at"])
    )


def _new_connection(session_db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(session_db_path, timeout=5.0)
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA)


__all__ = [
    "NOTES_MAX_LENGTH",
    "MobileReviewRecord",
    "read_mobile_review",
    "record_mobile_review",
]
