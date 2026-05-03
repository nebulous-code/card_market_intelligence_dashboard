"""
Tests for services.collection_session.

Hits the database directly through the per-test transactional session.
The helpers commit internally; that's intentional in production but in
tests it pushes rows past the outer SAVEPOINT-based isolation. We work
around that by re-reading via the same session, then explicitly cleaning
up at the end of each test where the helper auto-committed.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from schemas.collection import ParsedCollectionRow
from services.collection_session import (
    COOKIE_MAX_AGE_SECONDS,
    SESSION_TTL,
    create_session,
    delete_session,
    get_session,
)


def _row(**overrides):
    base = dict(
        card_id="base1-4",
        condition="NM",
        variant=["Reverse Holo"],
        is_first_edition=True,
        quantity=2,
        purchase_price=Decimal("250.00"),
    )
    base.update(overrides)
    return ParsedCollectionRow(**base)


@pytest.fixture
def session_cleanup(engine):
    """Track session ids the test created and DELETE them at teardown.

    The CRUD helpers commit internally, so the per-test SAVEPOINT
    rollback in db_session does not reach them.
    """
    created: list[str] = []
    yield created
    if created:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM collection_sessions WHERE id = ANY(:ids)"),
                {"ids": created},
            )


def test_cookie_constants_match_ttl():
    assert SESSION_TTL == timedelta(hours=24)
    assert COOKIE_MAX_AGE_SECONDS == 24 * 60 * 60


def test_create_and_read_round_trip(db_session, session_cleanup):
    session_id = create_session(db_session, [_row(), _row(card_id="base1-58", quantity=1)])
    session_cleanup.append(session_id)

    stored = get_session(db_session, session_id)
    assert stored is not None
    assert stored.session_id == session_id
    assert len(stored.rows) == 2
    assert stored.rows[0].card_id == "base1-4"
    assert stored.rows[0].variant == ["Reverse Holo"]
    assert stored.rows[0].is_first_edition is True
    assert stored.rows[0].purchase_price == Decimal("250.00")
    # Expiry should be roughly TTL away from creation.
    assert (stored.expires_at - stored.created_at) >= timedelta(hours=23, minutes=55)


def test_create_session_stores_no_purchase_price(db_session, session_cleanup):
    session_id = create_session(db_session, [_row(purchase_price=None)])
    session_cleanup.append(session_id)
    stored = get_session(db_session, session_id)
    assert stored.rows[0].purchase_price is None


def test_create_session_stores_empty_variant(db_session, session_cleanup):
    session_id = create_session(db_session, [_row(variant=[])])
    session_cleanup.append(session_id)
    stored = get_session(db_session, session_id)
    assert stored.rows[0].variant == []


def test_get_session_missing_returns_none(db_session):
    assert get_session(db_session, "00000000-0000-0000-0000-000000000000") is None


def test_get_session_expired_returns_none(db_session, session_cleanup, engine):
    from sqlalchemy.orm import Session

    session_id = create_session(db_session, [_row()])
    session_cleanup.append(session_id)
    # Push expires_at into the past via a fresh connection so the change
    # is committed before the read.
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE collection_sessions SET expires_at = :past WHERE id = :id"),
            {"past": datetime.utcnow() - timedelta(minutes=1), "id": session_id},
        )
    # Read with a brand-new session so we don't hit any stale snapshot
    # from the per-test session's earlier transaction.
    with Session(engine) as fresh:
        assert get_session(fresh, session_id) is None


def test_delete_session_removes_row(db_session, session_cleanup):
    session_id = create_session(db_session, [_row()])
    session_cleanup.append(session_id)
    delete_session(db_session, session_id)
    assert get_session(db_session, session_id) is None


def test_delete_session_missing_id_is_noop(db_session):
    delete_session(db_session, "no-such-id")  # must not raise
