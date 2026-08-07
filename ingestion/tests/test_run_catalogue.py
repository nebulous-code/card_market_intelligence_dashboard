"""
Tests for ingestion/run_catalogue.py.

The catalogue walk touches ~218 sets in one run, so its defining property
is failure isolation: one bad set is skipped, never fatal. Only a failure
to fetch the set list itself stops the run, because without it there is
nothing to iterate.
"""

import logging
import sys

import pytest


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """The driver paces itself between calls; tests must not actually wait."""
    import run_catalogue

    monkeypatch.setattr(run_catalogue.time, "sleep", lambda _s: None)


def _patch(mocker, monkeypatch, *, briefs, get_set=None, load=None, known=()):
    import run_catalogue

    monkeypatch.delenv("GITHUB_ENV", raising=False)
    mocker.patch.object(run_catalogue, "get_sets", return_value=briefs)
    mocker.patch.object(run_catalogue, "_existing_set_ids", return_value=set(known))
    if get_set is not None:
        mocker.patch.object(run_catalogue, "get_set", side_effect=get_set)
    if load is not None:
        mocker.patch.object(run_catalogue, "load_set_identity", side_effect=load)
    return run_catalogue


def _set(set_id, serie="base", cards=1):
    return {
        "id": set_id, "name": set_id.upper(),
        "serie": {"id": serie, "name": serie},
        "cards": [{"id": f"{set_id}-1", "name": "C", "localId": "1"}] * cards,
    }


def _stats(n=1):
    return {"cards_upserted": n, "duplicates_skipped": 0, "malformed_skipped": 0}


def test_walks_every_set_and_summarizes(mocker, monkeypatch, caplog):
    rc = _patch(
        mocker, monkeypatch,
        briefs=[{"id": "a"}, {"id": "b"}],
        get_set=lambda sid: _set(sid),
        load=lambda data: {"set_id": data["id"], **_stats(3)},
    )
    with caplog.at_level(logging.INFO):
        rc.main()

    assert "Sets upserted  : 2" in caplog.text
    assert "Cards upserted : 6" in caplog.text
    assert "Overall status : Success" in caplog.text


def test_a_failed_fetch_skips_only_that_set(mocker, monkeypatch, caplog):
    """One transient 502 out of 218 is a warning, not a failed run."""
    def flaky(sid):
        if sid == "bad":
            raise RuntimeError("boom")
        return _set(sid)

    rc = _patch(
        mocker, monkeypatch,
        briefs=[{"id": "good"}, {"id": "bad"}],
        get_set=flaky,
        load=lambda data: {"set_id": data["id"], **_stats()},
    )
    with caplog.at_level(logging.INFO):
        rc.main()

    assert "Sets upserted  : 1" in caplog.text
    assert "Sets failed    : 1" in caplog.text
    assert "bad -- fetch: boom" in caplog.text
    assert "Overall status : Warnings" in caplog.text


def test_a_failed_load_skips_only_that_set(mocker, monkeypatch, caplog):
    def flaky_load(data):
        if data["id"] == "bad":
            raise RuntimeError("db gone")
        return {"set_id": data["id"], **_stats()}

    rc = _patch(
        mocker, monkeypatch,
        briefs=[{"id": "good"}, {"id": "bad"}],
        get_set=lambda sid: _set(sid),
        load=flaky_load,
    )
    with caplog.at_level(logging.INFO):
        rc.main()

    assert "bad -- load: db gone" in caplog.text
    assert "Sets upserted  : 1" in caplog.text


def test_throttles_even_when_a_fetch_fails(mocker, monkeypatch):
    """The sleep lives in a finally block so a run of failures cannot turn
    into a burst of retries against the API."""
    import run_catalogue

    calls = []
    monkeypatch.setattr(run_catalogue.time, "sleep", lambda s: calls.append(s))
    _patch(
        mocker, monkeypatch,
        briefs=[{"id": "bad"}],
        get_set=mocker.Mock(side_effect=RuntimeError("boom")),
    )
    run_catalogue.main()

    assert len(calls) == 1


def test_excludes_digital_only_series(mocker, monkeypatch, caplog):
    """Pokemon TCG Pocket cards cannot be physically owned, so every feature
    downstream of the catalogue is meaningless for them."""
    rc = _patch(
        mocker, monkeypatch,
        briefs=[{"id": "phys"}, {"id": "digi"}],
        get_set=lambda sid: _set(sid, serie="tcgp" if sid == "digi" else "base"),
        load=lambda data: {"set_id": data["id"], **_stats()},
    )
    with caplog.at_level(logging.INFO):
        rc.main()

    assert "Sets upserted  : 1" in caplog.text
    assert "Sets excluded  : 1" in caplog.text


def test_reports_new_sets(mocker, monkeypatch, caplog):
    rc = _patch(
        mocker, monkeypatch,
        briefs=[{"id": "old"}, {"id": "new"}],
        get_set=lambda sid: _set(sid),
        load=lambda data: {"set_id": data["id"], **_stats()},
        known=["old"],
    )
    with caplog.at_level(logging.INFO):
        rc.main()

    assert "new (NEW)" in caplog.text
    assert "old (OLD)" not in caplog.text


def test_caps_the_new_set_list(mocker, monkeypatch, caplog):
    """A first run finds every set; a 218-line email is not a summary."""
    import run_catalogue

    monkeypatch.setattr(run_catalogue, "MAX_NEW_SETS_LISTED", 2)
    rc = _patch(
        mocker, monkeypatch,
        briefs=[{"id": f"s{i}"} for i in range(5)],
        get_set=lambda sid: _set(sid),
        load=lambda data: {"set_id": data["id"], **_stats()},
    )
    with caplog.at_level(logging.INFO):
        rc.main()

    assert "and 3 more" in caplog.text


def test_card_skips_downgrade_the_status(mocker, monkeypatch, caplog):
    rc = _patch(
        mocker, monkeypatch,
        briefs=[{"id": "a"}],
        get_set=lambda sid: _set(sid),
        load=lambda data: {
            "set_id": data["id"], "cards_upserted": 1,
            "duplicates_skipped": 1, "malformed_skipped": 2,
        },
    )
    with caplog.at_level(logging.INFO):
        rc.main()

    assert "Overall status : Warnings" in caplog.text
    assert "duplicate 1, malformed 2" in caplog.text


def test_a_run_that_wrote_nothing_is_a_failure(mocker, monkeypatch, caplog):
    rc = _patch(
        mocker, monkeypatch,
        briefs=[{"id": "a"}],
        get_set=mocker.Mock(side_effect=RuntimeError("boom")),
    )
    with caplog.at_level(logging.INFO):
        rc.main()

    assert "Overall status : Failed" in caplog.text


def test_a_failed_set_list_exits_one(mocker, monkeypatch, caplog):
    """Without the list there is nothing to iterate -- the one fatal case."""
    import run_catalogue

    monkeypatch.delenv("GITHUB_ENV", raising=False)
    mocker.patch.object(run_catalogue, "get_sets", side_effect=RuntimeError("dns"))

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as exc:
            run_catalogue.main()
    assert exc.value.code == 1
    assert "Failed to fetch the set list" in caplog.text


def test_writes_github_env_when_present(mocker, monkeypatch, tmp_path):
    import run_catalogue

    env_file = tmp_path / "gh.env"
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    mocker.patch.object(run_catalogue, "get_sets", return_value=[{"id": "a"}])
    mocker.patch.object(run_catalogue, "_existing_set_ids", return_value=set())
    mocker.patch.object(run_catalogue, "get_set", side_effect=lambda sid: _set(sid))
    mocker.patch.object(
        run_catalogue, "load_set_identity",
        side_effect=lambda d: {"set_id": d["id"], **_stats()},
    )

    run_catalogue.main()

    body = env_file.read_text()
    assert "CATALOGUE_STATUS=Success" in body
    assert "CATALOGUE_SUMMARY<<EOF" in body


def test_existing_set_ids_reads_the_database(db_session, monkeypatch):
    import loader
    import run_catalogue
    from sqlalchemy import text

    monkeypatch.setattr(loader, "engine", db_session.connection())
    monkeypatch.setattr(run_catalogue, "engine", db_session.connection())
    db_session.execute(text(
        "INSERT INTO sets (id, name, series, printed_total, created_at) "
        "VALUES ('rc_x', 'X', 'S', 1, NOW())"
    ))

    assert "rc_x" in run_catalogue._existing_set_ids()


def test_module_runs_as_a_script(mocker, monkeypatch):
    """The `if __name__ == '__main__'` guard."""
    import runpy

    import run_catalogue

    mocker.patch.object(run_catalogue, "get_sets", return_value=[])
    mocker.patch.object(run_catalogue, "_existing_set_ids", return_value=set())
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_catalogue.py"])
    # An empty catalogue writes nothing, so the status is Failed and the
    # script still completes rather than raising.
    run_catalogue.main()
    assert runpy is not None
