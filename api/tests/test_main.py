"""
Tests for the FastAPI application entry point.

Covers the lifespan handler (success + failure paths) and the root /
endpoint. Lifespan tests mock subprocess.run so we don't actually re-run
alembic during the test -- the alembic_upgrade fixture in conftest already
brought the schema up.
"""

import subprocess
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "docs": "/docs"}


def test_lifespan_runs_alembic_on_startup():
    """A successful alembic exit (returncode 0) lets the app start normally."""
    from main import app

    fake_result = subprocess.CompletedProcess(
        args=["alembic", "upgrade", "head"],
        returncode=0,
        stdout="upgrade ok\n",
        stderr="",
    )

    with patch("main.subprocess.run", return_value=fake_result) as mock_run:
        # Using TestClient as a context manager triggers lifespan startup.
        with TestClient(app) as c:
            assert c.get("/health").status_code == 200
        mock_run.assert_called_once()
        assert mock_run.call_args.args[0] == ["alembic", "upgrade", "head"]


def test_lifespan_raises_when_alembic_fails():
    """Non-zero alembic exit must raise RuntimeError so the server stops."""
    from main import app

    fake_result = subprocess.CompletedProcess(
        args=["alembic", "upgrade", "head"],
        returncode=1,
        stdout="",
        stderr="boom\n",
    )

    with patch("main.subprocess.run", return_value=fake_result):
        with pytest.raises(RuntimeError, match="Alembic migration failed"):
            with TestClient(app):
                pass  # not reached -- lifespan startup must error first
