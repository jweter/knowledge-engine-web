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

PR #144 merged first and shipped an earlier, single-row-per-session schema
(`session_id TEXT PRIMARY KEY, review, notes, reviewed_at`, upserted on every
submission). `_ensure_migrated` below detects that exact legacy shape against
any pre-existing database and migrates it, once and atomically, into this
append-only schema before any read or write runs -- see its docstring for why
this is needed and how it stays safe.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS web_mobile_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    review TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    web_commit TEXT NOT NULL DEFAULT '',
    build_identity_verified INTEGER NOT NULL DEFAULT 0,
    reviewed_at TEXT NOT NULL
)
"""
_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_web_mobile_reviews_session
    ON web_mobile_reviews(session_id, id)
"""
_SCHEMA = f"{_CREATE_TABLE_SQL};\n{_CREATE_INDEX_SQL};\n"

# The exact schemas this module must recognize. Any other shape -- including
# one that merely happens to contain a `web_commit` column, or drifted in some
# other way -- is refused rather than guessed at; see
# `_migrate_legacy_schema_if_needed`.
_PR144_LEGACY_COLUMNS = frozenset({"session_id", "review", "notes", "reviewed_at"})
_APPEND_ONLY_COLUMNS = frozenset(
    {"id", "session_id", "review", "notes", "web_commit", "build_identity_verified", "reviewed_at"}
)
_LEGACY_TABLE_NAME = "web_mobile_reviews_pr144_legacy"

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

    _ensure_migrated(session_db_path)
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
    _ensure_migrated(session_db_path)
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


def _ensure_migrated(session_db_path: str) -> None:
    """Migrate a PR #144-era database to the append-only schema, if needed.

    Called before every read and write so a database created by that earlier
    single-row-per-session code self-heals the moment this module touches it,
    rather than requiring a separate operator migration step. Cheap (one
    `PRAGMA table_info` lookup) and idempotent once already migrated -- see
    `_migrate_legacy_schema_if_needed`.

    Uses its own short-lived connection in autocommit mode (`isolation_level
    = None`) so the migration's explicit `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK`
    fully control the transaction: with the default deferred isolation level,
    Python's sqlite3 module implicitly commits any open transaction before a
    DDL statement, which would silently break atomicity across the
    rename/create/copy/drop sequence below.
    """

    connection = sqlite3.connect(session_db_path, timeout=5.0, isolation_level=None)
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        _migrate_legacy_schema_if_needed(connection)
    finally:
        connection.close()


def _table_columns(connection: sqlite3.Connection) -> frozenset[str]:
    return frozenset(
        row[1] for row in connection.execute("PRAGMA table_info(web_mobile_reviews)").fetchall()
    )


def _migrate_legacy_schema_if_needed(connection: sqlite3.Connection) -> None:
    """Migrate a PR #144-era `web_mobile_reviews` table to the append-only schema.

    PR #144 shipped `web_mobile_reviews(session_id TEXT PRIMARY KEY, review,
    notes, reviewed_at)` -- one row per session, overwritten on every
    submission. This module's append-only schema adds `id`/`web_commit`/
    `build_identity_verified` columns and drops the `session_id` primary key
    so history is preserved instead of overwritten. `CREATE TABLE IF NOT
    EXISTS` alone is a no-op against an already-existing legacy table, which
    would silently make every already-recorded review inaccessible: writes
    would fail on the missing columns, and every read helper here fails
    closed to "no review found" on any `sqlite3.DatabaseError` -- exactly the
    kind of silent data loss this project's fail-closed discipline forbids.

    Every migrated row is honestly marked unverified
    (`web_commit=''`, `build_identity_verified=0`): a build identity PR #144
    never recorded cannot be reconstructed after the fact, and fabricating
    one would let a pre-hardening verdict masquerade as authoritative. See
    `mobile_product_reality.build_identity_is_verified`, which already treats
    an empty string as unverified.

    Refuses (raises `RuntimeError`, migrating nothing) rather than guesses
    when `web_mobile_reviews` exists but matches neither the known legacy
    shape nor the exact current one -- silently reinterpreting an
    unrecognized schema is exactly the kind of fabrication this migration
    exists to avoid. Note this checks for the *exact* append-only column set,
    not merely the presence of a `web_commit` column: a table that happens to
    contain that name but is otherwise malformed or drifted must not be
    waved through as already-migrated.

    Concurrency: a first, lock-free `PRAGMA table_info` read decides only
    whether there is nothing to do (no table yet, or already the exact
    current schema) -- both terminal states no other caller can undo, so
    skipping the lock for them is safe. Anything else (the legacy shape, or
    something unrecognized) is not decided from that read; it only means a
    migration *might* be needed. Two concurrent first accesses can both
    observe the legacy shape before either takes the lock. Deciding to
    migrate from that stale read would let a second caller, after the first
    already migrated and committed, re-run the rename/create/copy/drop
    sequence against the now-current table -- silently discarding any
    build-provenance fields recorded in between. So once a migration is
    potentially required, this acquires `BEGIN IMMEDIATE` first and only then
    re-reads `PRAGMA table_info` -- the sole observation trustworthy enough
    to act on, since `BEGIN IMMEDIATE` serializes against any other writer
    already holding or about to take the same lock. If that fresh read shows
    the table already migrated (by whoever held the lock first), this is a
    safe no-op commit. Only if the freshly re-read schema is still exactly
    the legacy shape does the actual migration run, atomically: rename the
    legacy table aside, create the new one, copy every row across, drop the
    renamed table, commit -- or roll back the whole thing on any failure so
    a partial migration can never be observed.
    """

    columns = _table_columns(connection)
    if not columns or columns == _APPEND_ONLY_COLUMNS:
        return  # no such table yet, or already migrated -- both stable, no lock needed

    # From here, a migration might be needed, but the read above is not
    # trustworthy enough to act on: re-check under the lock before altering
    # anything.
    connection.execute("BEGIN IMMEDIATE")
    try:
        columns = _table_columns(connection)
        if not columns or columns == _APPEND_ONLY_COLUMNS:
            # A concurrent caller already migrated (or otherwise resolved
            # this) while this call was waiting for the lock.
            connection.execute("COMMIT")
            return
        if columns != _PR144_LEGACY_COLUMNS:
            raise RuntimeError(
                "web_mobile_reviews has an unrecognized schema "
                f"({sorted(columns)}); refusing to migrate rather than risk silent data loss."
            )

        connection.execute(f"ALTER TABLE web_mobile_reviews RENAME TO {_LEGACY_TABLE_NAME}")
        connection.execute(_CREATE_TABLE_SQL)
        connection.execute(_CREATE_INDEX_SQL)
        connection.execute(
            f"""
            INSERT INTO web_mobile_reviews
                (session_id, review, notes, web_commit, build_identity_verified, reviewed_at)
            SELECT session_id, review, notes, '', 0, reviewed_at
            FROM {_LEGACY_TABLE_NAME}
            """
        )
        connection.execute(f"DROP TABLE {_LEGACY_TABLE_NAME}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


__all__ = [
    "NOTES_MAX_LENGTH",
    "MobileReviewRecord",
    "read_mobile_review",
    "read_mobile_review_history",
    "record_mobile_review",
]
