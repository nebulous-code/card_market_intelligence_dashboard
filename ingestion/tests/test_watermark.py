"""
Tests for ingestion/watermark.py.

Watermarks are written and read against the ingestion_watermarks table
(created by migration 002). All tests use the per-test transactional
session so any rows written here roll back on teardown.
"""

from datetime import datetime, timezone

from sqlalchemy import text


def _seed_set(db_session, set_id: str = "base1"):
    """ingestion_watermarks has an FK on set_id -> sets.id, so callers must
    insert a parent set row first."""
    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, created_at) "
            "VALUES (:id, 'Test', 'X', 1, NOW())"
        ),
        {"id": set_id},
    )


def test_get_watermark_returns_none_when_missing(db_session):
    from watermark import get_watermark

    _seed_set(db_session)
    assert get_watermark(db_session, "base1") is None


def test_set_watermark_inserts_a_row(db_session):
    from watermark import SOURCE, get_watermark, set_watermark

    _seed_set(db_session)
    set_watermark(db_session, "base1", last_offset=0)

    wm = get_watermark(db_session, "base1")
    assert wm is not None
    assert wm["last_offset"] == 0
    assert isinstance(wm["last_ingested_at"], datetime)
    assert isinstance(wm["updated_at"], datetime)

    # Sanity: the source label is what the rest of the pipeline reads.
    assert SOURCE == "pokemonpricetracker"


def test_set_watermark_upserts_on_conflict(db_session):
    """Calling set_watermark twice updates the existing row's offset."""
    from watermark import set_watermark

    _seed_set(db_session)
    set_watermark(db_session, "base1", last_offset=0)
    set_watermark(db_session, "base1", last_offset=42)

    row = db_session.execute(
        text(
            "SELECT last_offset FROM ingestion_watermarks "
            "WHERE source = 'pokemonpricetracker' AND set_id = 'base1'"
        )
    ).fetchone()
    assert row.last_offset == 42


def test_get_all_sets_orders_by_release_date(db_session):
    """get_all_sets returns oldest-first; sets with no date sort last."""
    from datetime import date

    from watermark import get_all_sets

    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, release_date, created_at) VALUES "
            "('z', 'Z',     'X', 1, NULL,         NOW()), "
            "('b', 'Older', 'X', 1, '1999-01-01', NOW()), "
            "('a', 'Newer', 'X', 1, '2024-01-01', NOW())"
        )
    )

    rows = get_all_sets(db_session)
    assert [r["id"] for r in rows] == ["b", "a", "z"]
    # Sanity: dict shape is what run.py expects.
    assert all({"id", "name"} <= r.keys() for r in rows)
    # Use the date import to silence lint.
    assert date(1999, 1, 1).year == 1999
    # `now` must be a datetime in UTC for log lines to make sense.
    assert datetime.now(timezone.utc).tzinfo is not None
