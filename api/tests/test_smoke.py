"""
Smoke tests proving the test harness boots end-to-end.

These tests deliberately exercise the full chain -- engine connect, schema
applied, FastAPI app importable, TestClient routes resolvable -- so that
anything subtler that breaks the harness fails here loudly rather than as
mysterious failures elsewhere in the suite.
"""


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_db_session_can_query(db_session):
    """Schema is up and the per-test session is wired correctly."""
    from sqlalchemy import text

    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_canonical_tables_seeded(db_session):
    """Migration 008/009 seeded canonical_conditions/variants/rarities."""
    from sqlalchemy import text

    counts = {
        table: db_session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        for table in ("canonical_conditions", "canonical_variants", "canonical_rarities")
    }
    assert counts["canonical_conditions"] >= 14
    assert counts["canonical_variants"] >= 6
    assert counts["canonical_rarities"] == 8
