"""
Tests for ingestion/logging_setup.py.

Logging configuration is global, so tests reset the root logger's handlers
on each run to avoid bleeding state between tests.
"""

import logging
import os


def _reset_root_logger():
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()


def test_configure_logging_adds_two_handlers(tmp_path, monkeypatch):
    _reset_root_logger()
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    from logging_setup import configure_logging

    log_file = tmp_path / "test.log"
    configure_logging(log_file=str(log_file))

    root = logging.getLogger()
    assert len(root.handlers) == 2
    assert root.level == logging.INFO

    # File handler must have written the file when something logs.
    logging.getLogger("smoke").info("hello")
    for h in root.handlers:
        h.flush()
    assert log_file.exists()
    assert log_file.read_text(encoding="utf-8")


def test_configure_logging_is_idempotent(tmp_path):
    _reset_root_logger()
    from logging_setup import configure_logging

    configure_logging(log_file=str(tmp_path / "a.log"))
    handler_count_before = len(logging.getLogger().handlers)
    configure_logging(log_file=str(tmp_path / "b.log"))
    assert len(logging.getLogger().handlers) == handler_count_before


def test_configure_logging_honors_log_level_env(tmp_path, monkeypatch):
    _reset_root_logger()
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    from logging_setup import configure_logging

    configure_logging(log_file=str(tmp_path / "debug.log"))
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_unknown_level_falls_back_to_info(tmp_path, monkeypatch):
    _reset_root_logger()
    monkeypatch.setenv("LOG_LEVEL", "NOPE")

    from logging_setup import configure_logging

    configure_logging(log_file=str(tmp_path / "fallback.log"))
    assert logging.getLogger().level == logging.INFO


def test_color_formatter_wraps_levelname_with_ansi():
    from logging_setup import _COLORS, _ColorFormatter

    fmt = _ColorFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="x",
        level=logging.WARNING,
        pathname=__file__,
        lineno=10,
        msg="hi",
        args=(),
        exc_info=None,
    )
    out = fmt.format(record)
    assert _COLORS["WARNING"] in out
    assert _COLORS["RESET"] in out


def test_color_formatter_falls_back_to_reset_for_unknown_level():
    from logging_setup import _COLORS, _ColorFormatter

    fmt = _ColorFormatter("%(levelname)s")
    record = logging.LogRecord(
        name="x",
        level=99,
        pathname=__file__,
        lineno=1,
        msg="hi",
        args=(),
        exc_info=None,
    )
    record.levelname = "MYSTERY"
    out = fmt.format(record)
    # Falls back to the RESET color (since "MYSTERY" isn't in _COLORS).
    assert out.startswith(_COLORS["RESET"])


def teardown_module():
    """Restore a clean root logger so other tests aren't affected."""
    _reset_root_logger()
    # Touch os to silence import lint -- needed for monkeypatch usage above.
    assert os.environ is not None
