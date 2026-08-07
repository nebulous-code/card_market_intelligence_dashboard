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


def test_get_priced_sets_orders_by_release_date(db_session):
    """get_priced_sets returns oldest-first; sets with no date sort last."""
    from datetime import date

    from watermark import get_priced_sets

    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, release_date, created_at) VALUES "
            "('z', 'Z',     'X', 1, NULL,         NOW()), "
            "('b', 'Older', 'X', 1, '1999-01-01', NOW()), "
            "('a', 'Newer', 'X', 1, '2024-01-01', NOW())"
        )
    )
    # Only a set with a ('ppt', 'name') mapping counts as priced.
    db_session.execute(
        text(
            "INSERT INTO set_identifiers (set_id, source, identifier, identifier_type) VALUES "
            "('z', 'ppt', 'Z',     'name'), "
            "('b', 'ppt', 'Older', 'name'), "
            "('a', 'ppt', 'Newer', 'name')"
        )
    )

    rows = get_priced_sets(db_session)
    assert [r["id"] for r in rows] == ["b", "a", "z"]
    # Sanity: dict shape is what run.py expects.
    assert all({"id", "name"} <= r.keys() for r in rows)
    # Use the date import to silence lint.
    assert date(1999, 1, 1).year == 1999
    # `now` must be a datetime in UTC for log lines to make sense.
    assert datetime.now(timezone.utc).tzinfo is not None


def test_get_priced_sets_excludes_sets_without_a_ppt_mapping(db_session):
    """A catalogued set we do not pay for must not reach the price run.

    This is the whole point of the function: since the catalogue ingest
    landed, the sets table holds every set TCGdex publishes, and iterating
    all of them would produce a wall of resolver errors every night.
    """
    from watermark import get_priced_sets

    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, release_date, created_at) VALUES "
            "('priced',   'Priced',   'X', 1, '2000-01-01', NOW()), "
            "('unpriced', 'Unpriced', 'X', 1, '2000-01-02', NOW())"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO set_identifiers (set_id, source, identifier, identifier_type) VALUES "
            "('priced', 'ppt', 'Priced', 'name'), "
            # A tcgdex mapping is not a PPT mapping -- this set is catalogued
            # but not paid for, and must still be excluded.
            "('unpriced', 'tcgdex', 'unpriced', 'id')"
        )
    )

    rows = get_priced_sets(db_session)
    assert [r["id"] for r in rows] == ["priced"]
