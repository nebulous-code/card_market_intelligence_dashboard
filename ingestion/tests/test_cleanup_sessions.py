"""
Tests for ingestion/cleanup_sessions.py.

The script is a thin wrapper around a single DELETE -- we exercise the
real DB round-trip rather than mocking it, since that's the whole code
path. Uses the same TEST_DATABASE_URL the api test suite does (set in
the root conftest), so the alembic-migrated test schema is available.
"""

from datetime import datetime, timedelta

from sqlalchemy import create_engine, text


def _engine():
    import os

    return create_engine(os.environ["DATABASE_URL"])


def _insert_session(engine, session_id: str, expires_at: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO collection_sessions (id, collection, expires_at)
                VALUES (:id, CAST('[]' AS JSONB), :expires_at)
                """
            ),
            {"id": session_id, "expires_at": expires_at},
        )


def _row_exists(engine, session_id: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM collection_sessions WHERE id = :id"),
            {"id": session_id},
        ).fetchone()
    return row is not None


def test_main_deletes_only_expired_rows():
    import cleanup_sessions

    engine = _engine()
    fresh_id = "test-cleanup-fresh"
    expired_id = "test-cleanup-expired"
    _insert_session(engine, fresh_id, datetime.utcnow() + timedelta(hours=1))
    _insert_session(engine, expired_id, datetime.utcnow() - timedelta(hours=1))

    try:
        cleanup_sessions.main()
        assert _row_exists(engine, fresh_id) is True
        assert _row_exists(engine, expired_id) is False
    finally:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM collection_sessions WHERE id IN (:fresh, :expired)"
                ),
                {"fresh": fresh_id, "expired": expired_id},
            )


def test_main_with_no_expired_rows_is_noop(caplog):
    import cleanup_sessions

    engine = _engine()
    fresh_id = "test-cleanup-noop"
    _insert_session(engine, fresh_id, datetime.utcnow() + timedelta(hours=1))
    try:
        with caplog.at_level("INFO", logger="cleanup_sessions"):
            cleanup_sessions.main()
        assert "Deleted 0 expired" in caplog.text
        assert _row_exists(engine, fresh_id) is True
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM collection_sessions WHERE id = :id"),
                {"id": fresh_id},
            )
