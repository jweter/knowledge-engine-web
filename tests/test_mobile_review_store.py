from __future__ import annotations

from pathlib import Path

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
