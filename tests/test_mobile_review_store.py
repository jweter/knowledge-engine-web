from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from knowledge_engine_web.mobile_review_store import (
    NOTES_MAX_LENGTH,
    read_mobile_review,
    read_mobile_review_history,
    record_mobile_review,
)


def _record(
    session_db: Path,
    session_id: str,
    review: str,
    notes: str = "",
    *,
    web_commit: str = "sha-1",
    build_identity_verified: bool = True,
) -> None:
    record_mobile_review(
        str(session_db),
        session_id,
        review,
        notes,
        web_commit=web_commit,
        build_identity_verified=build_identity_verified,
    )


def test_read_returns_none_for_unknown_session(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    assert read_mobile_review(str(session_db), "no-such-session") is None


def test_history_is_empty_for_unknown_session(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    assert read_mobile_review_history(str(session_db), "no-such-session") == []


def test_record_then_read_round_trips(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    _record(session_db, "session-1", "PASS", "Looked correct on iPhone Safari.")
    stored = read_mobile_review(str(session_db), "session-1")

    assert stored is not None
    assert stored.review == "PASS"
    assert stored.notes == "Looked correct on iPhone Safari."
    assert stored.web_commit == "sha-1"
    assert stored.build_identity_verified is True
    assert stored.reviewed_at


def test_recording_again_preserves_the_prior_verdict_in_history(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    _record(session_db, "session-1", "FLAG", "First pass, looked off.", web_commit="sha-1")
    _record(session_db, "session-1", "PASS", "Confirmed correct on retest.", web_commit="sha-2")

    current = read_mobile_review(str(session_db), "session-1")
    assert current is not None
    assert current.review == "PASS"
    assert current.notes == "Confirmed correct on retest."
    assert current.web_commit == "sha-2"

    history = read_mobile_review_history(str(session_db), "session-1")
    assert [entry.review for entry in history] == ["FLAG", "PASS"]
    assert history[0].notes == "First pass, looked off."
    assert history[0].web_commit == "sha-1"
    assert history[1].web_commit == "sha-2"


def test_a_later_pass_never_deletes_an_earlier_fail_or_flag(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    _record(session_db, "session-1", "FAIL", "Broken on first try.")
    _record(session_db, "session-1", "FLAG", "Still suspicious.")
    _record(session_db, "session-1", "PASS", "Fixed and confirmed.")

    history = read_mobile_review_history(str(session_db), "session-1")

    assert [entry.review for entry in history] == ["FAIL", "FLAG", "PASS"]
    assert len(history) == 3


def test_history_is_scoped_per_session(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    _record(session_db, "session-1", "PASS")
    _record(session_db, "session-2", "FAIL")

    assert [entry.review for entry in read_mobile_review_history(str(session_db), "session-1")] == [
        "PASS"
    ]
    assert [entry.review for entry in read_mobile_review_history(str(session_db), "session-2")] == [
        "FAIL"
    ]


def test_build_identity_is_recorded_per_review(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    _record(session_db, "session-1", "PASS", web_commit="", build_identity_verified=False)
    stored = read_mobile_review(str(session_db), "session-1")

    assert stored is not None
    assert stored.web_commit == ""
    assert stored.build_identity_verified is False


def test_notes_are_truncated_to_the_maximum_length(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    _record(session_db, "session-1", "FAIL", "x" * (NOTES_MAX_LENGTH + 500))
    stored = read_mobile_review(str(session_db), "session-1")

    assert stored is not None
    assert len(stored.notes) == NOTES_MAX_LENGTH


def _create_pr144_legacy_database(
    session_db: Path, session_id: str, review: str, notes: str, reviewed_at: str
) -> None:
    """Build the exact PR #144 schema/row, byte-for-byte as that merged code shipped it."""

    connection = sqlite3.connect(str(session_db))
    try:
        connection.execute(
            """
            CREATE TABLE web_mobile_reviews (
                session_id TEXT PRIMARY KEY,
                review TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO web_mobile_reviews (session_id, review, notes, reviewed_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, review, notes, reviewed_at),
        )
        connection.commit()
    finally:
        connection.close()


def test_legacy_pr144_database_migrates_without_losing_prior_review_evidence(
    tmp_path: Path,
) -> None:
    session_db = tmp_path / "sessions.sqlite3"
    session_id = "legacy-session-1"

    # 1 + 2: the exact PR #144 legacy schema, with one already-recorded verdict.
    _create_pr144_legacy_database(
        session_db, session_id, "FAIL", "Broken before this upgrade.", "2026-09-10T12:00:00+00:00"
    )

    # 3 + 4: invoking the current storage path must migrate without losing that row.
    history_after_migration = read_mobile_review_history(str(session_db), session_id)
    assert len(history_after_migration) == 1
    legacy_entry = history_after_migration[0]
    assert legacy_entry.review == "FAIL"
    assert legacy_entry.notes == "Broken before this upgrade."
    assert legacy_entry.reviewed_at == "2026-09-10T12:00:00+00:00"

    # 5: no trustworthy build identity ever existed for this row -- it must read as
    # unverified, never a fabricated one.
    assert legacy_entry.web_commit == ""
    assert legacy_entry.build_identity_verified is False

    # 6: append a new, build-verified verdict after the upgrade.
    record_mobile_review(
        str(session_db),
        session_id,
        "PASS",
        "Fixed and confirmed after migration.",
        web_commit="post-migration-sha",
        build_identity_verified=True,
    )

    # 7: both the legacy and the new verdict remain, in chronological order.
    history = read_mobile_review_history(str(session_db), session_id)
    assert [entry.review for entry in history] == ["FAIL", "PASS"]
    assert history[0].web_commit == ""
    assert history[0].build_identity_verified is False
    assert history[1].web_commit == "post-migration-sha"
    assert history[1].build_identity_verified is True

    current = read_mobile_review(str(session_db), session_id)
    assert current is not None
    assert current.review == "PASS"


def test_migrating_a_legacy_database_via_the_write_path_also_preserves_history(
    tmp_path: Path,
) -> None:
    """The write path (`record_mobile_review`) must self-heal a legacy database too,
    not only the read path -- a phone reviewer's first action after an upgrade may be
    submitting a new verdict rather than reloading the page."""

    session_db = tmp_path / "sessions.sqlite3"
    session_id = "legacy-session-write-path"
    _create_pr144_legacy_database(
        session_db, session_id, "FLAG", "Needs another look.", "2026-09-10T09:00:00+00:00"
    )

    record_mobile_review(
        str(session_db),
        session_id,
        "PASS",
        "Confirmed fine now.",
        web_commit="sha-after-upgrade",
        build_identity_verified=True,
    )

    history = read_mobile_review_history(str(session_db), session_id)
    assert [entry.review for entry in history] == ["FLAG", "PASS"]
    assert history[0].build_identity_verified is False
    assert history[1].build_identity_verified is True


def test_legacy_migration_is_idempotent_across_repeated_read_and_write_calls(
    tmp_path: Path,
) -> None:
    session_db = tmp_path / "sessions.sqlite3"
    session_id = "legacy-session-2"
    _create_pr144_legacy_database(session_db, session_id, "PASS", "", "2026-09-10T12:00:00+00:00")

    # Trigger the migration path repeatedly, via both reads and a write; none of
    # these should fail, duplicate rows, or disturb already-migrated data.
    read_mobile_review_history(str(session_db), session_id)
    read_mobile_review_history(str(session_db), session_id)
    record_mobile_review(
        str(session_db),
        session_id,
        "FLAG",
        "Second look.",
        web_commit="sha-2",
        build_identity_verified=True,
    )
    read_mobile_review_history(str(session_db), session_id)
    read_mobile_review(str(session_db), session_id)

    history = read_mobile_review_history(str(session_db), session_id)
    assert [entry.review for entry in history] == ["PASS", "FLAG"]


def test_legacy_migration_preserves_multiple_sessions(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"
    connection = sqlite3.connect(str(session_db))
    try:
        connection.execute(
            """
            CREATE TABLE web_mobile_reviews (
                session_id TEXT PRIMARY KEY,
                review TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO web_mobile_reviews (session_id, review, notes, reviewed_at) "
            "VALUES (?, ?, ?, ?)",
            [
                ("legacy-a", "PASS", "", "2026-09-10T10:00:00+00:00"),
                ("legacy-b", "FAIL", "Broken.", "2026-09-10T11:00:00+00:00"),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    assert [entry.review for entry in read_mobile_review_history(str(session_db), "legacy-a")] == [
        "PASS"
    ]
    assert [entry.review for entry in read_mobile_review_history(str(session_db), "legacy-b")] == [
        "FAIL"
    ]


def test_migration_refuses_an_unrecognized_schema_rather_than_guess(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"
    connection = sqlite3.connect(str(session_db))
    try:
        connection.execute(
            "CREATE TABLE web_mobile_reviews (session_id TEXT PRIMARY KEY, some_other_column TEXT)"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="unrecognized schema"):
        read_mobile_review_history(str(session_db), "any-session")
