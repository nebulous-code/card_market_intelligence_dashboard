"""
Tests for ingestion/run_sync_priced_sets.py.

The entry point's job is turning a sync result into a status the nightly
email can carry. The interesting cases are the status branches: a set named
in the YAML that is not in the catalogue must warn without failing, and a
malformed YAML must fail loudly rather than silently pricing nothing.
"""

import logging

import pytest


def _result(inserted=(), updated=(), unchanged=0, missing=()):
    return {
        "inserted": list(inserted),
        "updated": list(updated),
        "unchanged": unchanged,
        "missing_sets": list(missing),
    }


def _patch(mocker, monkeypatch, *, entries=None, result=None, load_exc=None, sync_exc=None):
    import run_sync_priced_sets as mod

    monkeypatch.delenv("GITHUB_ENV", raising=False)
    if load_exc is not None:
        mocker.patch.object(mod, "load_priced_sets", side_effect=load_exc)
    else:
        mocker.patch.object(mod, "load_priced_sets", return_value=entries or [])
    if sync_exc is not None:
        mocker.patch.object(mod, "sync_priced_sets", side_effect=sync_exc)
    else:
        mocker.patch.object(mod, "sync_priced_sets", return_value=result or _result())
    return mod


def test_a_clean_no_op_reports_success(mocker, monkeypatch, caplog):
    """The nightly case: the YAML has not changed since last night."""
    mod = _patch(
        mocker, monkeypatch,
        entries=[{"set_id": "a", "ppt_name": "A", "tcgdex_id": "a"}],
        result=_result(unchanged=2),
    )
    with caplog.at_level(logging.INFO):
        mod.main()

    assert "Rows unchanged : 2" in caplog.text
    assert "Overall status : Success" in caplog.text
    assert "(no changes)" in caplog.text


def test_reports_inserts_and_updates(mocker, monkeypatch, caplog):
    mod = _patch(
        mocker, monkeypatch,
        entries=[{"set_id": "a", "ppt_name": "A", "tcgdex_id": "a"}],
        result=_result(
            inserted=[("a", "ppt/name", "A")],
            updated=[("b", "ppt/name", "B New")],
        ),
    )
    with caplog.at_level(logging.INFO):
        mod.main()

    assert "+ a" in caplog.text
    assert "~ b" in caplog.text
    assert "-> B New" in caplog.text
    assert "Overall status : Changed" in caplog.text


def test_a_set_missing_from_the_catalogue_warns_without_failing(mocker, monkeypatch, caplog):
    """Transient the night TCGdex is down; a typo if it persists. The
    message has to name both possibilities."""
    mod = _patch(
        mocker, monkeypatch,
        entries=[{"set_id": "ghost", "ppt_name": "G", "tcgdex_id": "ghost"}],
        result=_result(missing=["ghost"]),
    )
    with caplog.at_level(logging.INFO):
        mod.main()   # must NOT raise SystemExit

    assert "Overall status : Warnings" in caplog.text
    assert "ghost -- not in the sets table" in caplog.text
    assert "typo" in caplog.text


def test_a_malformed_yaml_exits_one(mocker, monkeypatch, caplog):
    from priced_sets import PricedSetsError

    mod = _patch(mocker, monkeypatch, load_exc=PricedSetsError("bad file"))

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as exc:
            mod.main()
    assert exc.value.code == 1
    assert "bad file" in caplog.text


def test_a_database_failure_exits_one(mocker, monkeypatch, caplog):
    mod = _patch(
        mocker, monkeypatch,
        entries=[{"set_id": "a", "ppt_name": "A", "tcgdex_id": "a"}],
        sync_exc=RuntimeError("connection refused"),
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as exc:
            mod.main()
    assert exc.value.code == 1
    assert "connection refused" in caplog.text


def test_writes_github_env_when_present(mocker, monkeypatch, tmp_path):
    import run_sync_priced_sets as mod

    env_file = tmp_path / "gh.env"
    mocker.patch.object(mod, "load_priced_sets", return_value=[])
    mocker.patch.object(mod, "sync_priced_sets", return_value=_result(unchanged=1))
    monkeypatch.setenv("GITHUB_ENV", str(env_file))

    mod.main()

    body = env_file.read_text()
    assert "PRICED_SETS_STATUS=Success" in body
    assert "PRICED_SETS_SUMMARY<<EOF" in body


def test_failure_summary_also_reaches_github_env(mocker, monkeypatch, tmp_path):
    from priced_sets import PricedSetsError
    import run_sync_priced_sets as mod

    env_file = tmp_path / "gh.env"
    mocker.patch.object(mod, "load_priced_sets", side_effect=PricedSetsError("nope"))
    monkeypatch.setenv("GITHUB_ENV", str(env_file))

    with pytest.raises(SystemExit):
        mod.main()

    assert "PRICED_SETS_STATUS=Failed" in env_file.read_text()
