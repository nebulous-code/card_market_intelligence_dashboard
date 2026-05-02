"""
Tests for the database session-factory module.

The route tests cover database queries through the dependency override, so
this file's job is only to exercise get_db itself -- specifically that it
yields a working session and closes it on teardown.
"""


def test_get_db_yields_session_and_closes(mocker):
    """The generator yields a session, then calls close() on teardown.

    Patching SessionLocal in the database module lets us swap in a
    mock session whose .close() we can assert on. The real session
    is exercised throughout the rest of the suite via the fixture --
    here we just want to lock in the cleanup contract.
    """
    import database

    fake_session = mocker.MagicMock()
    mocker.patch.object(database, "SessionLocal", return_value=fake_session)

    gen = database.get_db()
    session = next(gen)
    assert session is fake_session
    fake_session.close.assert_not_called()

    # Exhausting the generator runs the `finally: db.close()` block.
    with __import__("pytest").raises(StopIteration):
        next(gen)
    fake_session.close.assert_called_once()
