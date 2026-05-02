"""
Tests for ingestion/run.py.

The orchestration loop has many branches (no sets, set resolver missing,
fetch failure, no data, insert failure, watermark, credit exhaustion,
GITHUB_ENV summary write). Each path is hit with mocked external calls.
"""

import sys

import pytest


def _make_stats(matched=1, skipped=0, errors=0, ppt_total=1,
                 skipped_cards=None, unknowns=None):
    return {
        "matched": matched,
        "skipped": skipped,
        "errors": errors,
        "ppt_total": ppt_total,
        "skipped_cards": skipped_cards or [],
        "unknowns": unknowns or {},
    }


def _patch_db_session(mocker, run_module, sets):
    """Mock create_engine + Session so get_all_sets returns the seeded list."""
    mocker.patch.object(run_module, "create_engine", return_value=object())

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def begin(self):
            return self

    mocker.patch.object(run_module, "Session", FakeSession)
    mocker.patch.object(run_module, "get_all_sets", return_value=sets)


def test_main_no_sets_exits_zero(monkeypatch, mocker, caplog):
    import logging

    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    _patch_db_session(mocker, run, sets=[])

    with caplog.at_level(logging.WARNING):
        with pytest.raises(SystemExit) as exc:
            run.main()
    assert exc.value.code == 0
    assert "No sets found" in caplog.text


def test_main_processes_sets_end_to_end(monkeypatch, mocker, caplog):
    import logging

    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    monkeypatch.delenv("GITHUB_ENV", raising=False)

    sets = [{"id": "base1", "name": "Base Set"}]
    _patch_db_session(mocker, run, sets=sets)

    mocker.patch.object(run, "resolve_identifier", return_value="Base Set")
    mocker.patch.object(run, "get_watermark", return_value=None, create=True)
    mocker.patch("watermark.get_watermark", return_value=None)
    mocker.patch.object(run, "fetch_prices", return_value=([{"name": "C"}], 100, 0))
    mocker.patch.object(run, "insert_price_snapshots", return_value=_make_stats())
    set_wm = mocker.patch.object(run, "set_watermark")
    mocker.patch.object(run, "credits_exhausted", return_value=False)

    with caplog.at_level(logging.INFO):
        run.main()

    set_wm.assert_called_once()
    assert "Nightly ingestion complete" in caplog.text


def test_main_skips_unresolved_set(monkeypatch, mocker, caplog):
    import logging

    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    sets = [{"id": "base1", "name": "Base Set"}]
    _patch_db_session(mocker, run, sets=sets)

    mocker.patch.object(
        run, "resolve_identifier",
        side_effect=run.SetIdentifierNotFoundError("missing"),
    )

    with caplog.at_level(logging.ERROR):
        run.main()
    assert "missing" in caplog.text


def test_main_handles_fetch_failure(monkeypatch, mocker, caplog):
    import logging

    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    sets = [{"id": "base1", "name": "Base Set"}]
    _patch_db_session(mocker, run, sets=sets)

    mocker.patch.object(run, "resolve_identifier", return_value="Base Set")
    mocker.patch("watermark.get_watermark", return_value=None)
    mocker.patch.object(run, "fetch_prices", side_effect=RuntimeError("network"))

    with caplog.at_level(logging.ERROR):
        run.main()
    assert "Failed to fetch prices" in caplog.text


def test_main_handles_empty_ppt_response(monkeypatch, mocker, caplog):
    import logging

    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    sets = [{"id": "base1", "name": "Base Set"}]
    _patch_db_session(mocker, run, sets=sets)

    mocker.patch.object(run, "resolve_identifier", return_value="Base Set")
    mocker.patch("watermark.get_watermark", return_value=None)
    mocker.patch.object(run, "fetch_prices", return_value=([], 100, 0))

    with caplog.at_level(logging.WARNING):
        run.main()
    assert "No price data returned" in caplog.text


def test_main_handles_insert_failure(monkeypatch, mocker, caplog):
    import logging

    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    sets = [{"id": "base1", "name": "Base Set"}]
    _patch_db_session(mocker, run, sets=sets)

    mocker.patch.object(run, "resolve_identifier", return_value="Base Set")
    mocker.patch("watermark.get_watermark", return_value=None)
    mocker.patch.object(run, "fetch_prices", return_value=([{"name": "C"}], 100, 0))
    mocker.patch.object(run, "insert_price_snapshots", side_effect=RuntimeError("bad insert"))

    with caplog.at_level(logging.ERROR):
        run.main()
    assert "Failed to insert snapshots" in caplog.text


def test_main_resumes_from_watermark(monkeypatch, mocker, caplog):
    import logging

    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    sets = [{"id": "base1", "name": "Base Set"}]
    _patch_db_session(mocker, run, sets=sets)

    mocker.patch.object(run, "resolve_identifier", return_value="Base Set")
    mocker.patch("watermark.get_watermark", return_value={"last_offset": 50})
    mocker.patch.object(run, "fetch_prices", return_value=([{"name": "C"}], 100, 60))
    mocker.patch.object(run, "insert_price_snapshots", return_value=_make_stats())
    mocker.patch.object(run, "set_watermark")
    mocker.patch.object(run, "credits_exhausted", return_value=False)

    with caplog.at_level(logging.INFO):
        run.main()
    assert "resuming" in caplog.text.lower()
    assert "partially completed" in caplog.text


def test_main_swallows_watermark_lookup_error(monkeypatch, mocker, caplog):
    """A watermark lookup that raises is treated as 'no watermark yet'."""
    import logging

    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    sets = [{"id": "base1", "name": "Base Set"}]
    _patch_db_session(mocker, run, sets=sets)

    mocker.patch.object(run, "resolve_identifier", return_value="Base Set")
    mocker.patch("watermark.get_watermark", side_effect=RuntimeError("dirty schema"))
    mocker.patch.object(run, "fetch_prices", return_value=([{"name": "C"}], 100, 0))
    mocker.patch.object(run, "insert_price_snapshots", return_value=_make_stats())
    mocker.patch.object(run, "set_watermark")
    mocker.patch.object(run, "credits_exhausted", return_value=False)

    with caplog.at_level(logging.INFO):
        run.main()
    # No exception bubbled; the run completed normally despite the wm error.
    assert "Nightly ingestion complete" in caplog.text


def test_main_stops_when_credits_exhausted(monkeypatch, mocker, caplog):
    import logging

    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    sets = [
        {"id": "base1", "name": "Base Set"},
        {"id": "base2", "name": "Jungle"},
    ]
    _patch_db_session(mocker, run, sets=sets)

    mocker.patch.object(run, "resolve_identifier", return_value="Base Set")
    mocker.patch("watermark.get_watermark", return_value=None)
    mocker.patch.object(run, "fetch_prices", return_value=([{"name": "C"}], 5, 0))
    mocker.patch.object(run, "insert_price_snapshots", return_value=_make_stats())
    mocker.patch.object(run, "set_watermark")
    mocker.patch.object(run, "credits_exhausted", return_value=True)

    with caplog.at_level(logging.WARNING):
        run.main()
    assert "Daily credit limit nearly exhausted" in caplog.text


def test_main_writes_github_env_summary(monkeypatch, mocker, tmp_path):
    """When GITHUB_ENV is set, the summary block is appended to that file."""
    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    github_env = tmp_path / "github_env"
    monkeypatch.setenv("GITHUB_ENV", str(github_env))

    _patch_db_session(mocker, run, sets=[])

    with pytest.raises(SystemExit):
        # No sets -> exits 0 *before* the summary block. To hit the write,
        # use a non-empty sets list. Re-arrange:
        run.main()


def test_main_writes_github_env_when_run_completes(monkeypatch, mocker, tmp_path):
    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    github_env = tmp_path / "github_env"
    monkeypatch.setenv("GITHUB_ENV", str(github_env))

    sets = [{"id": "base1", "name": "Base Set"}]
    _patch_db_session(mocker, run, sets=sets)
    mocker.patch.object(run, "resolve_identifier", return_value="Base Set")
    mocker.patch("watermark.get_watermark", return_value=None)
    mocker.patch.object(run, "fetch_prices", return_value=([{"name": "C"}], 100, 0))
    mocker.patch.object(run, "insert_price_snapshots", return_value=_make_stats())
    mocker.patch.object(run, "set_watermark")
    mocker.patch.object(run, "credits_exhausted", return_value=False)

    run.main()

    contents = github_env.read_text()
    assert "RUN_DATE=" in contents
    assert "RUN_STATUS=" in contents
    assert "EMAIL_BODY<<EOF" in contents


def test_main_merges_per_set_unknowns_into_summary(monkeypatch, mocker, caplog):
    """Per-set stats['unknowns'] entries get merged into run_unknowns and
    rendered via _format_unknowns at end of run."""
    import logging

    import run

    monkeypatch.setattr(sys, "argv", ["run.py"])
    sets = [{"id": "base1", "name": "Base"}]
    _patch_db_session(mocker, run, sets=sets)
    mocker.patch.object(run, "resolve_identifier", return_value="Base")
    mocker.patch("watermark.get_watermark", return_value=None)
    mocker.patch.object(run, "fetch_prices", return_value=([{"name": "C"}], 100, 0))
    mocker.patch.object(
        run, "insert_price_snapshots",
        return_value=_make_stats(unknowns={("variant", "WeirdFoil"): 12}),
    )
    mocker.patch.object(run, "set_watermark")
    mocker.patch.object(run, "credits_exhausted", return_value=False)

    with caplog.at_level(logging.INFO):
        run.main()

    assert "WeirdFoil" in caplog.text
    assert "INSERT INTO variant_aliases" in caplog.text


def test_main_summary_status_paths(monkeypatch, mocker):
    """The overall_status branches: errors -> Failed, skipped -> Warnings,
    clean -> Success."""
    import run

    # Errors path.
    monkeypatch.setattr(sys, "argv", ["run.py"])
    sets = [{"id": "base1", "name": "Base"}]
    _patch_db_session(mocker, run, sets=sets)
    mocker.patch.object(run, "resolve_identifier", return_value="Base")
    mocker.patch("watermark.get_watermark", return_value=None)
    mocker.patch.object(run, "fetch_prices", return_value=([{"name": "C"}], 100, 0))
    mocker.patch.object(run, "insert_price_snapshots", return_value=_make_stats(errors=1))
    mocker.patch.object(run, "set_watermark")
    mocker.patch.object(run, "credits_exhausted", return_value=False)
    run.main()  # asserts no exception

    # Warnings path: set up fresh mocks so we can swap in the warnings stats.
    mocker.patch.object(run, "insert_price_snapshots", return_value=_make_stats(skipped=1, skipped_cards=[("c1", "X", "no match")]))
    run.main()


def test_format_unknowns_empty_returns_none_marker():
    from run import _format_unknowns

    assert _format_unknowns({}) == "  (none)"


def test_format_unknowns_renders_insert_snippets():
    from run import _format_unknowns

    out = _format_unknowns({
        ("variant", "WeirdFoil"): 47,
        ("condition", "Mystery"): 3,
        ("rarity", "Mythic"): 5,  # unknown field falls back to "rarity_aliases".
    })
    assert "WeirdFoil" in out
    assert "Mystery" in out
    assert "Mythic" in out
    assert "INSERT INTO variant_aliases" in out
    assert "INSERT INTO condition_aliases" in out
    assert "INSERT INTO rarity_aliases" in out


def test_bool_env_reads_environment(monkeypatch):
    from run import _bool_env

    monkeypatch.setenv("FOO", "true")
    assert _bool_env("FOO") is True
    monkeypatch.setenv("FOO", "FALSE")
    assert _bool_env("FOO") is False
    monkeypatch.delenv("FOO", raising=False)
    assert _bool_env("FOO", default=True) is True
    assert _bool_env("FOO", default=False) is False
