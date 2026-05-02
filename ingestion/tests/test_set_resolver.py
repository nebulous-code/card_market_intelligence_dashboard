"""
Tests for ingestion/set_resolver.py.

set_resolver opens its own Session via a module-level engine, so we don't
use the conftest db_session fixture. Instead, we insert seed rows through
a separate session, commit them so the resolver's session sees them, and
clean up at the end of each test.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@pytest.fixture
def seed_session():
    """Standalone session that commits its work so resolver sees the rows."""
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def cleanup_set_identifiers():
    """Reset set_resolver's module-level engine cache and clear seed data."""
    import set_resolver

    # Force a fresh engine reference per test so we always read DATABASE_URL
    # from the test environment.
    set_resolver._engine = None

    yield

    # Wipe any rows tests inserted so order-of-tests doesn't matter.
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        with session.begin():
            session.execute(text("DELETE FROM set_identifiers WHERE set_id LIKE 'res_%'"))
            session.execute(text("DELETE FROM sets WHERE id LIKE 'res_%'"))


def _seed_set(seed_session, set_id: str = "res_base1"):
    """Helper: insert a set + tcgdex/ppt identifier rows and commit."""
    with seed_session.begin():
        seed_session.execute(
            text(
                "INSERT INTO sets (id, name, series, printed_total, created_at) "
                "VALUES (:id, 'Test Set', 'Series', 1, NOW())"
            ),
            {"id": set_id},
        )
        seed_session.execute(
            text(
                "INSERT INTO set_identifiers (set_id, source, identifier, identifier_type) VALUES "
                "(:id, 'tcgdex', :id,         'id'), "
                "(:id, 'tcgdex', 'Test Set',   'name'), "
                "(:id, 'ppt',    'Test Set Pretty Name', 'name')"
            ),
            {"id": set_id},
        )


def test_resolve_returns_tcgdex_id(seed_session):
    from set_resolver import SOURCE_TCGDEX, resolve_identifier

    _seed_set(seed_session)
    assert resolve_identifier("Test Set", SOURCE_TCGDEX) == "res_base1"


def test_resolve_returns_ppt_name(seed_session):
    from set_resolver import SOURCE_PPT, resolve_identifier

    _seed_set(seed_session)
    assert resolve_identifier("res_base1", SOURCE_PPT) == "Test Set Pretty Name"


def test_resolve_case_insensitive(seed_session):
    from set_resolver import SOURCE_TCGDEX, resolve_identifier

    _seed_set(seed_session)
    assert resolve_identifier("test set", SOURCE_TCGDEX) == "res_base1"


def test_resolve_unknown_source_defaults_to_name(seed_session):
    """Unknown source falls back to identifier_type='name'."""
    from set_resolver import resolve_identifier

    _seed_set(seed_session)
    # 'tcgplayer' is in the constants table -- use a truly unknown source
    # by inserting one and asking for it.
    with seed_session.begin():
        seed_session.execute(
            text(
                "INSERT INTO set_identifiers (set_id, source, identifier, identifier_type) "
                "VALUES ('res_base1', 'mystery', 'Mystery Display Name', 'name')"
            )
        )
    assert resolve_identifier("res_base1", "mystery") == "Mystery Display Name"


def test_resolve_raises_with_helpful_message(seed_session):
    """Missing mapping yields a SetIdentifierNotFoundError with INSERT SQL."""
    from set_resolver import (
        SOURCE_PPT,
        SetIdentifierNotFoundError,
        resolve_identifier,
    )

    _seed_set(seed_session, set_id="res_only_tcgdex")
    # Drop the ppt row so a ppt lookup fails.
    with seed_session.begin():
        seed_session.execute(
            text(
                "DELETE FROM set_identifiers "
                "WHERE set_id = 'res_only_tcgdex' AND source = 'ppt'"
            )
        )

    with pytest.raises(SetIdentifierNotFoundError) as excinfo:
        resolve_identifier("res_only_tcgdex", SOURCE_PPT)

    msg = str(excinfo.value)
    assert "ppt" in msg
    assert "INSERT INTO set_identifiers" in msg
    # The hint should include the actual set_id so the operator can paste-fix.
    assert "res_only_tcgdex" in msg


def test_resolve_unknown_set_uses_placeholder_hint(seed_session):
    """When even the set_id can't be found, error message uses <set_id>."""
    from set_resolver import SOURCE_PPT, SetIdentifierNotFoundError, resolve_identifier

    with pytest.raises(SetIdentifierNotFoundError) as excinfo:
        resolve_identifier("absolutely-not-a-real-set", SOURCE_PPT)
    assert "<set_id>" in str(excinfo.value)


def test_register_identifier_inserts_row(seed_session):
    from set_resolver import SOURCE_TCGPLAYER, register_identifier, resolve_identifier

    _seed_set(seed_session, set_id="res_register")
    register_identifier("res_register", SOURCE_TCGPLAYER, "TCGPlayer Name", "name")

    assert resolve_identifier("res_register", SOURCE_TCGPLAYER) == "TCGPlayer Name"


def test_register_identifier_rejects_missing_set(seed_session):
    from set_resolver import register_identifier

    with pytest.raises(ValueError, match="does not exist in the sets table"):
        register_identifier("res_nope", "ppt", "Name", "name")


def test_register_identifier_rejects_duplicate(seed_session):
    from set_resolver import register_identifier

    _seed_set(seed_session, set_id="res_dup")
    with pytest.raises(ValueError, match="already exists"):
        # The seed already inserted (set, ppt, name).
        register_identifier("res_dup", "ppt", "Some Other Name", "name")


def test_engine_is_cached(seed_session):
    """_get_engine returns the same instance on subsequent calls."""
    import set_resolver

    set_resolver._engine = None
    e1 = set_resolver._get_engine()
    e2 = set_resolver._get_engine()
    assert e1 is e2
