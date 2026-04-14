"""
Shared logging configuration for the ingestion pipeline.

Call configure_logging() once at the start of any ingestion entry point
(run.py, run_ingest.py) to set up consistent console + file logging across
all modules in the pipeline.

Log file location: ingestion/ingestion.log (relative to the working directory,
which is always the ingestion/ folder when scripts are invoked via uv run).
"""

import logging


# ANSI color codes used to make log levels visually distinct in the terminal.
_COLORS = {
    "DEBUG": "\033[36m",     # cyan
    "INFO": "\033[32m",      # green
    "WARNING": "\033[33m",   # yellow
    "ERROR": "\033[31m",     # red
    "CRITICAL": "\033[35m",  # magenta
    "RESET": "\033[0m",
}


class _ColorFormatter(logging.Formatter):
    """Custom log formatter that adds ANSI color codes to the level name."""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, _COLORS["RESET"])
        reset = _COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


def configure_logging(log_file: str = "ingestion.log") -> None:
    """
    Configure the root logger with a console handler and a file handler.

    Safe to call more than once -- duplicate handlers are not added if the
    root logger already has handlers (e.g. if a module was imported before
    this function was called).

    Args:
        log_file: Path to the log file. Defaults to "ingestion.log" in the
            current working directory (the ingestion/ folder).
    """
    root = logging.getLogger()

    if root.handlers:
        # Already configured -- don't add duplicate handlers.
        return

    root.setLevel(logging.DEBUG)

    # File handler: plain text, no color codes (they appear as garbage in files).
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    # Console handler: colorized for readability in the terminal.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(_ColorFormatter("%(asctime)s [%(levelname)s] %(message)s"))

    root.addHandler(file_handler)
    root.addHandler(console_handler)
