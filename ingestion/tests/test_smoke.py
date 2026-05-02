"""
Smoke tests for the ingestion package's test harness.
"""


def test_loader_module_imports():
    """The loader module imports cleanly with the test env vars set."""
    import loader

    assert hasattr(loader, "load_set")
    assert hasattr(loader, "insert_price_snapshots")


def test_db_session_can_query(db_session):
    from sqlalchemy import text

    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1
