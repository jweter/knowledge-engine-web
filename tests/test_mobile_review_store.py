from __future__ import annotations

from pathlib import Path

from knowledge_engine_web.mobile_review_store import (
    NOTES_MAX_LENGTH,
    read_mobile_review,
    record_mobile_review,
)


def test_read_returns_none_for_unknown_session(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    assert read_mobile_review(str(session_db), "no-such-session") is None


def test_record_then_read_round_trips(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    record_mobile_review(str(session_db), "session-1", "PASS", "Looked correct on iPhone Safari.")
    stored = read_mobile_review(str(session_db), "session-1")

    assert stored is not None
    assert stored.review == "PASS"
    assert stored.notes == "Looked correct on iPhone Safari."
    assert stored.reviewed_at


def test_recording_again_overwrites_the_prior_verdict(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    record_mobile_review(str(session_db), "session-1", "FLAG", "First pass, looked off.")
    record_mobile_review(str(session_db), "session-1", "PASS", "Confirmed correct on retest.")
    stored = read_mobile_review(str(session_db), "session-1")

    assert stored is not None
    assert stored.review == "PASS"
    assert stored.notes == "Confirmed correct on retest."


def test_notes_are_truncated_to_the_maximum_length(tmp_path: Path) -> None:
    session_db = tmp_path / "sessions.sqlite3"

    record_mobile_review(str(session_db), "session-1", "FAIL", "x" * (NOTES_MAX_LENGTH + 500))
    stored = read_mobile_review(str(session_db), "session-1")

    assert stored is not None
    assert len(stored.notes) == NOTES_MAX_LENGTH
