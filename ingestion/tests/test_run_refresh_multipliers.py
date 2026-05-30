"""
Tests for ingestion/run_refresh_multipliers.py.

External calls (refresh_all_sets) are mocked so we only exercise the
orchestration -- summary log block, status classification, and the
GITHUB_ENV append.
"""

import logging
import sys


def _empty_stats():
    return {
        "sets_processed": 0,
        "sets_failed": 0,
        "rows_written": 0,
        "ungrouped_warnings": [],
        "failed_sets": [],
    }


def test_format_ungrouped_empty():
    from run_refresh_multipliers import _format_ungrouped

    assert _format_ungrouped([]) == "  (none)"


def test_format_ungrouped_renders_each_card():
    from run_refresh_multipliers import _format_ungrouped

    out = _format_ungrouped([
        {"set_id": "base1", "card_id": "base1-4", "name": "Charizard", "missing_field": "rarity"},
        {"set_id": "base2", "card_id": "base2-1", "name": "Clefable", "missing_field": "supertype"},
    ])
    assert "Charizard" in out
    assert "Clefable" in out
    assert "rarity" in out
    assert "supertype" in out


def test_format_failed_empty():
    from run_refresh_multipliers import _format_failed

    assert _format_failed([]) == "  (none)"


def test_format_failed_renders_each_failure():
    from run_refresh_multipliers import _format_failed

    out = _format_failed([("base1", "boom"), ("base2", "kaboom")])
    assert "base1" in out
    assert "boom" in out
    assert "kaboom" in out


def test_main_success_status(monkeypatch, mocker, caplog):
    """No failures, no warnings -> Success status."""
    import run_refresh_multipliers

    monkeypatch.setattr(sys, "argv", ["run_refresh_multipliers.py"])
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    stats = _empty_stats()
    stats.update(sets_processed=2, rows_written=40)
    mocker.patch.object(run_refresh_multipliers, "refresh_all_sets", return_value=stats)

    with caplog.at_level(logging.INFO):
        run_refresh_multipliers.main()

    assert "Overall status       : Success" in caplog.text


def test_main_warnings_status(monkeypatch, mocker, caplog):
    """Ungrouped cards present but no failed sets -> Warnings status."""
    import run_refresh_multipliers

    monkeypatch.setattr(sys, "argv", ["run_refresh_multipliers.py"])
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    stats = _empty_stats()
    stats.update(
        sets_processed=2,
        rows_written=40,
        ungrouped_warnings=[
            {"set_id": "base1", "card_id": "base1-99", "name": "Mystery",
             "missing_field": "rarity"},
        ],
    )
    mocker.patch.object(run_refresh_multipliers, "refresh_all_sets", return_value=stats)

    with caplog.at_level(logging.INFO):
        run_refresh_multipliers.main()

    assert "Overall status       : Warnings" in caplog.text
    assert "Mystery" in caplog.text


def test_main_failed_status(monkeypatch, mocker, caplog):
    """Any failed set -> Failed status (overrides Warnings)."""
    import run_refresh_multipliers

    monkeypatch.setattr(sys, "argv", ["run_refresh_multipliers.py"])
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    stats = _empty_stats()
    stats.update(
        sets_processed=1,
        sets_failed=1,
        rows_written=20,
        failed_sets=[("base2", "boom")],
    )
    mocker.patch.object(run_refresh_multipliers, "refresh_all_sets", return_value=stats)

    with caplog.at_level(logging.INFO):
        run_refresh_multipliers.main()

    assert "Overall status       : Failed" in caplog.text
    assert "boom" in caplog.text


def test_main_writes_github_env(monkeypatch, mocker, tmp_path):
    """When GITHUB_ENV is set, the summary fields land in that file."""
    import run_refresh_multipliers

    monkeypatch.setattr(sys, "argv", ["run_refresh_multipliers.py"])
    github_env = tmp_path / "github_env"
    monkeypatch.setenv("GITHUB_ENV", str(github_env))

    stats = _empty_stats()
    stats.update(sets_processed=1, rows_written=10)
    mocker.patch.object(run_refresh_multipliers, "refresh_all_sets", return_value=stats)

    run_refresh_multipliers.main()

    contents = github_env.read_text(encoding="utf-8")
    assert "MULTIPLIER_STATUS=Success" in contents
    assert "MULTIPLIER_SUMMARY<<EOF" in contents
