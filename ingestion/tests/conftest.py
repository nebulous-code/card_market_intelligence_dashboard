"""
Test fixtures for the ingestion package.

Mirrors api/tests/conftest.py: adds ingestion/ to sys.path and provides a
transactional db_session fixture. The schema is set up by api/tests/
conftest.py's session-scoped alembic_upgrade fixture; we don't need to
re-run migrations here because pytest discovers the root conftest first
and shares the alembic_upgrade fixture across both test trees.

We do NOT add the api/ alembic-running fixture here. If someone runs only
ingestion tests (`pytest ingestion/tests`), they're expected to either run
the full suite first or have an already-migrated test DB. The CI workflow
runs the whole suite at once, so this is fine in practice.
"""

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

INGESTION_DIR = Path(__file__).resolve().parent.parent
if str(INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(INGESTION_DIR))


@pytest.fixture
def db_session():
    """Per-test transactional session for ingestion tests."""
    engine = create_engine(os.environ["DATABASE_URL"])
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
