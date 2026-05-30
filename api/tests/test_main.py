"""
Tests for the FastAPI application entry point.

Covers the root ``/`` endpoint, the background migration runner, and the
lifespan handler. ``run_migrations`` is tested directly as a coroutine with
``asyncio.create_subprocess_exec`` mocked, so we never actually re-run
alembic here -- the ``alembic_upgrade`` fixture in ``conftest`` already
brought the schema up. Lifespan tests patch ``run_migrations`` itself with
controllable coroutines (instant vs. hanging) so both branches of the
shutdown cleanup are exercised.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "docs": "/docs"}


def _fake_proc(returncode, stdout=b"", stderr=b""):
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


def test_run_migrations_success_logs_stdout(capsys):
    """A zero exit prints alembic's stdout and leaves stderr empty."""
    from main import run_migrations

    fake = _fake_proc(returncode=0, stdout=b"upgrade ok\n")

    with patch(
        "main.asyncio.create_subprocess_exec", AsyncMock(return_value=fake)
    ):
        asyncio.run(run_migrations())

    captured = capsys.readouterr()
    assert "upgrade ok" in captured.out
    assert captured.err == ""


def test_run_migrations_failure_logs_stderr(capsys):
    """A non-zero exit logs stderr and a failure marker; no exception escapes."""
    from main import run_migrations

    fake = _fake_proc(returncode=1, stderr=b"boom\n")

    with patch(
        "main.asyncio.create_subprocess_exec", AsyncMock(return_value=fake)
    ):
        asyncio.run(run_migrations())

    captured = capsys.readouterr()
    assert "boom" in captured.err
    assert "Alembic migration failed" in captured.err


def test_lifespan_serves_immediately_and_skips_cancel_when_task_done():
    """/wake is reachable while migrations run in the background.

    When the migration finishes before shutdown the cleanup skips ``cancel``,
    exercising the ``task.done()`` True branch.
    """
    from main import app

    async def _instant_migration():
        return None

    with patch("main.run_migrations", _instant_migration):
        with TestClient(app) as c:
            assert c.get("/wake").status_code == 200
            task = app.state.migration_task
            assert isinstance(task, asyncio.Task)

    assert task.done()
    assert not task.cancelled()


def test_lifespan_cancels_in_flight_migration_on_shutdown():
    """A still-running migration is cancelled when the app shuts down.

    Outlasts the test window so ``task.done()`` is False at shutdown, taking
    the cancel branch of the cleanup.
    """
    from main import app

    async def _hanging_migration():
        await asyncio.sleep(60)

    with patch("main.run_migrations", _hanging_migration):
        with TestClient(app):
            task = app.state.migration_task
            assert not task.done()

    assert task.cancelled()
