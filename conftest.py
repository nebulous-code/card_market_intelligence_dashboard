"""
Top-level pytest configuration shared by api/tests and ingestion/tests.

Sets the environment variables every test module expects to be in place
before any production code is imported, and runs alembic migrations once
per session so the schema is in place regardless of which subset of tests
is selected (api-only, ingestion-only, or all).
"""

import os
import subprocess
from pathlib import Path

import pytest

# Point production code at the local test Postgres. tools/test.sh starts a
# container on port 5433; CI provides one via a service container on the
# same connection string. The default URL keeps local invocation
# (`uv run pytest`) working without manually exporting anything.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://test:test@localhost:5433/card_market_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# Every API-key / secret env var production code reads at import time gets
# a harmless placeholder so module-level code paths can run during tests
# without each test having to monkeypatch them. Real HTTP calls are mocked.
os.environ.setdefault("POKEMON_PRICE_TRACKER_API_KEY", "test-key")
os.environ.setdefault("PPT_INCLUDE_HISTORY", "false")
os.environ.setdefault("PPT_HISTORY_DAYS", "7")
os.environ.setdefault("PPT_INCLUDE_EBAY", "false")

API_DIR = Path(__file__).resolve().parent / "api"


@pytest.fixture(scope="session", autouse=True)
def _alembic_upgrade():
    """Bring the test schema up to head once per session.

    Lives at the root so it fires regardless of whether the run targets
    api/tests/, ingestion/tests/, or both. Runs alembic with cwd=api/ so
    it picks up the alembic.ini in that package; DATABASE_URL is read by
    api/alembic/env.py just like in production.
    """
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=API_DIR,
        check=True,
        capture_output=True,
    )
    yield
