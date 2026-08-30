from __future__ import annotations

from pathlib import Path

from knowledge_engine_ai.sessions.models import ResearchEvent, ResearchSession, SessionStatus
from knowledge_engine_ai.sessions.repository import SessionRepository, new_connection

from knowledge_engine_web.research_session_status import read_session_status


def _seed_running_session(db_path: Path, *, session_id: str, question: str) -> None:
    """Write one RUNNING session with one completed workflow event, then close.

    Uses knowledge-engine-ai's own `SessionRepository` -- the same durable
    write path `ai_orchestration.run_ai_orchestration` uses -- rather than
    hand-rolled SQL, so this test exercises the real schema this module reads.
    """

    connection = new_connection(str(db_path))
    try:
        repository = SessionRepository(connection)
        repository.create_session(
            ResearchSession(
                schema_version=1,
                session_id=session_id,
                created_at="2026-08-30T00:00:00+00:00",
                updated_at="2026-08-30T00:00:00+00:00",
                user_question_original=question,
                status=SessionStatus.RUNNING,
            )
        )
        repository.append_event(
            ResearchEvent(
                event_id="event-1",
                session_id=session_id,
                timestamp="2026-08-30T00:00:01+00:00",
                workflow_node="retrieval_and_evidence_intelligence",
                executor_type="deterministic_tool",
                validation_status="succeeded",
                source_ids=(),
                source_dois=(),
                parent_event_ids=(),
            )
        )
    finally:
        connection.close()


def test_unknown_session_id_is_none() -> None:
    assert read_session_status("data/does-not-exist.sqlite3", "no-such-session") is None


def test_missing_store_file_is_none(tmp_path: Path) -> None:
    missing_db = tmp_path / "sessions.sqlite3"
    assert read_session_status(str(missing_db), "any-session") is None


def test_known_session_reports_status_and_latest_stage(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.sqlite3"
    _seed_running_session(db_path, session_id="session-1", question="Does creatine help?")

    view = read_session_status(str(db_path), "session-1")

    assert view is not None
    assert view.session_id == "session-1"
    assert view.question == "Does creatine help?"
    assert view.status == "running"
    assert view.terminal is False
    assert view.last_completed_stage == "Searching indexed evidence"
    assert view.latest_workflow_node == "retrieval_and_evidence_intelligence"
    assert view.event_count == 1


def test_session_with_no_events_yet_reports_no_completed_stage(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.sqlite3"
    connection = new_connection(str(db_path))
    try:
        SessionRepository(connection).create_session(
            ResearchSession(
                schema_version=1,
                session_id="session-queued",
                created_at="2026-08-30T00:00:00+00:00",
                updated_at="2026-08-30T00:00:00+00:00",
                user_question_original="Any question",
                status=SessionStatus.RUNNING,
            )
        )
    finally:
        connection.close()

    view = read_session_status(str(db_path), "session-queued")

    assert view is not None
    assert view.event_count == 0
    assert view.latest_workflow_node is None
    assert view.last_completed_stage is None


def test_terminal_status_survives_process_restart(tmp_path: Path) -> None:
    """The durable store must survive a fresh connection, not just the same process handle.

    Simulates "close the store and reopen it" (WEB-GQR-4's restart-survival
    requirement) by writing through one connection, closing it fully, then
    reading through an entirely new connection opened later -- the same shape
    a redeployed process reopening a persistent-disk file would see.
    """

    db_path = tmp_path / "sessions.sqlite3"
    connection = new_connection(str(db_path))
    try:
        repository = SessionRepository(connection)
        repository.create_session(
            ResearchSession(
                schema_version=1,
                session_id="session-done",
                created_at="2026-08-30T00:00:00+00:00",
                updated_at="2026-08-30T00:00:05+00:00",
                user_question_original="Does creatine help?",
                status=SessionStatus.RUNNING,
            )
        )
        repository.append_event(
            ResearchEvent(
                event_id="event-1",
                session_id="session-done",
                timestamp="2026-08-30T00:00:01+00:00",
                workflow_node="synthesis",
                executor_type="local_llm",
                validation_status="succeeded",
                source_ids=(),
                source_dois=(),
                parent_event_ids=(),
            )
        )
        repository.update_session_status(
            "session-done", SessionStatus.COMPLETED, updated_at="2026-08-30T00:00:05+00:00"
        )
    finally:
        connection.close()

    # A brand-new connection/process reading the same on-disk file later --
    # not the connection that wrote it.
    view = read_session_status(str(db_path), "session-done")

    assert view is not None
    assert view.status == "completed"
    assert view.terminal is True
    assert view.last_completed_stage == "Preparing and verifying a source-grounded answer"
    assert view.updated_at == "2026-08-30T00:00:05+00:00"


def test_unknown_session_id_in_existing_store_is_none(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.sqlite3"
    _seed_running_session(db_path, session_id="session-1", question="Does creatine help?")

    assert read_session_status(str(db_path), "session-does-not-exist") is None


def test_corrupt_store_file_is_none_not_a_raised_exception(tmp_path: Path) -> None:
    """A file that exists but is not a valid SQLite database must 404, not 500.

    SQLite opens lazily, so a non-database file raises `sqlite3.DatabaseError`
    (e.g. "file is not a database") only once a query actually runs against
    it -- a narrower `except sqlite3.OperationalError` does not catch this,
    since `DatabaseError` is not a subclass of `OperationalError`.
    """

    db_path = tmp_path / "sessions.sqlite3"
    db_path.write_bytes(b"not a sqlite database")

    assert read_session_status(str(db_path), "any-session") is None


def test_completed_session_releases_persisted_synthesis_and_citations(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.sqlite3"
    connection = new_connection(str(db_path))
    try:
        repository = SessionRepository(connection)
        repository.create_session(
            ResearchSession(
                schema_version=1,
                session_id="session-release",
                created_at="2026-08-30T00:00:00+00:00",
                updated_at="2026-08-30T00:00:00+00:00",
                user_question_original="Does creatine help?",
                status=SessionStatus.RUNNING,
            )
        )
        repository.append_event(
            ResearchEvent(
                event_id="synthesis-release",
                session_id="session-release",
                timestamp="2026-08-30T00:00:01+00:00",
                workflow_node="synthesis",
                executor_type="local_llm",
                validation_status="succeeded",
                notes="Creatine improves repeated high-intensity performance [ev-1].",
                duration_ms=125,
                source_ids=("ev-1",),
                source_dois=("10.1000/creatine",),
                parent_event_ids=(),
            )
        )
        repository.update_session_status(
            "session-release",
            SessionStatus.COMPLETED,
            updated_at="2026-08-30T00:00:02+00:00",
        )
    finally:
        connection.close()

    view = read_session_status(str(db_path), "session-release")

    assert view is not None
    assert view.execution_finished is True
    assert view.released_narrative == (
        "Creatine improves repeated high-intensity performance [ev-1]."
    )
    assert view.released_source_ids == ("ev-1",)
    assert view.released_source_dois == ("10.1000/creatine",)
    assert view.recorded_duration_ms == 125


def test_blocked_session_never_exposes_synthesis_draft(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.sqlite3"
    connection = new_connection(str(db_path))
    try:
        repository = SessionRepository(connection)
        repository.create_session(
            ResearchSession(
                schema_version=1,
                session_id="session-blocked",
                created_at="2026-08-30T00:00:00+00:00",
                updated_at="2026-08-30T00:00:00+00:00",
                user_question_original="Question?",
                status=SessionStatus.RUNNING,
            )
        )
        repository.append_event(
            ResearchEvent(
                event_id="synthesis-blocked",
                session_id="session-blocked",
                timestamp="2026-08-30T00:00:01+00:00",
                workflow_node="synthesis",
                executor_type="local_llm",
                validation_status="succeeded",
                notes="Draft that failed the close gate [ev-1].",
                source_ids=("ev-1",),
                source_dois=("10.1000/draft",),
                parent_event_ids=(),
            )
        )
        repository.update_session_status(
            "session-blocked",
            SessionStatus.BLOCKED,
            updated_at="2026-08-30T00:00:02+00:00",
        )
    finally:
        connection.close()

    view = read_session_status(str(db_path), "session-blocked")

    assert view is not None
    assert view.status == "blocked"
    assert view.terminal is False
    assert view.execution_finished is True
    assert view.released_narrative is None
    assert view.released_source_ids == ()
