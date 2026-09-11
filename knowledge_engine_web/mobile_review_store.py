"""Durable, append-only storage for human Mobile Product Reality reviews.

A review is deliberately keyed to the same durable `session_id` the async
Research job already uses (`research_jobs.py`), in the same session database,
so a phone reviewer's PASS/FAIL/FLAG verdict stays tied to the exact session
that produced the evidence they reviewed -- never a separate, driftable
identity.

Every submission is a new row, never an overwrite of a prior one: an earlier
FAIL or FLAG is real Product Reality evidence, and a later PASS (say, after a
fix) must not erase it from the record. `read_mobile_review` still answers
"what is the current verdict" by returning the most recent row; the full
sequence stays available via `read_mobile_review_history`.

Each row also carries the exact build identity (`web_commit`) that was in
effect when that specific verdict was recorded, and whether that identity was
verified (a real `RENDER_GIT_COMMIT`/`KE_WEB_BUILD_COMMIT`, not the
placeholder `mobile_product_reality.web_build_identity` returns when neither
is configured) -- see `mobile_product_reality.build_identity_is_verified`.
This is captured once, at submission time, rather than recomputed later, so a
verdict's recorded build identity cannot silently drift to whatever happens
to be deployed when someone later reads it back.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_mobile_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    review TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    web_commit TEXT NOT NULL DEFAULT '',
    build_identity_verified INTEGER NOT NULL DEFAULT 0,
    reviewed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_web_mobile_reviews_session
    ON web_mobile_reviews(session_id, id);
"""

NOTES_MAX_LENGTH = 4000


@dataclass(frozen=True)
class MobileReviewRecord:
    review: str
    notes: str
    web_commit: str
    build_identity_verified: bool
    reviewed_at: str


def record_mobile_review(
    session_db_path: str,
    session_id: str,
    review: str,
    notes: str,
    *,
    web_commit: str,
    build_identity_verified: bool,
) -> MobileReviewRecord:
    """Append one human review for this session; never overwrites a prior one."""

    now = datetime.now(UTC).isoformat()
    trimmed_notes = notes.strip()[:NOTES_MAX_LENGTH]
    connection = _new_connection(session_db_path)
    try:
        _ensure_schema(connection)
        connection.execute(
            """
            INSERT INTO web_mobile_reviews
                (session_id, review, notes, web_commit, build_identity_verified, reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, review, trimmed_notes, web_commit, int(build_identity_verified), now),
        )
        connection.commit()
    finally:
        connection.close()
    return MobileReviewRecord(
        review=review,
        notes=trimmed_notes,
        web_commit=web_commit,
        build_identity_verified=build_identity_verified,
        reviewed_at=now,
    )


def read_mobile_review(session_db_path: str, session_id: str) -> MobileReviewRecord | None:
    """Read the most recently recorded review, without creating or mutating the table."""

    history = read_mobile_review_history(session_db_path, session_id)
    return history[-1] if history else None


def read_mobile_review_history(session_db_path: str, session_id: str) -> list[MobileReviewRecord]:
    """Read every review ever recorded for this session, oldest first.

    Prior PASS/FAIL/FLAG verdicts are never overwritten or deleted by
    `record_mobile_review` -- this is how that preserved history stays
    inspectable rather than just sitting inertly in the database.
    """

    database_path = Path(session_db_path)
    if not database_path.is_file():
        return []
    try:
        connection = sqlite3.connect(
            f"file:{database_path}?mode=ro",
            uri=True,
            timeout=5.0,
        )
    except sqlite3.DatabaseError:
        return []
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = connection.execute(
                """
                SELECT review, notes, web_commit, build_identity_verified, reviewed_at
                FROM web_mobile_reviews
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        except sqlite3.DatabaseError:
            return []
    finally:
        connection.close()
    return [
        MobileReviewRecord(
            review=str(row["review"]),
            notes=str(row["notes"]),
            web_commit=str(row["web_commit"]),
            build_identity_verified=bool(row["build_identity_verified"]),
            reviewed_at=str(row["reviewed_at"]),
        )
        for row in rows
    ]


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
    "read_mobile_review_history",
    "record_mobile_review",
]
