"""
Entry point for the nightly condition_multipliers refresh.

Called by the GitHub Actions ingest workflow after price snapshots have
finished writing. Mirrors the run-summary structure used by run.py so the
nightly email gets a consistent layout.

Usage (manual):
    cd ingestion && uv run python run_refresh_multipliers.py
"""

import logging
import os

from dotenv import find_dotenv, load_dotenv
from logging_setup import configure_logging

configure_logging()
load_dotenv(find_dotenv())

from refresh_multipliers import refresh_all_sets  # noqa: E402

log = logging.getLogger(__name__)


def _format_ungrouped(warnings: list[dict]) -> str:
    """Render the ungrouped-card warnings as a copy-pasteable list.

    Each line names the set, card, and which field was missing so the
    operator can fix it in TCGdex (or accept that the card is intentionally
    unclassified). Returns "  (none)" when the list is empty.
    """
    if not warnings:
        return "  (none)"
    return "\n".join(
        f"  [{w['set_id']}] {w['card_id']} ({w['name']}) -- missing {w['missing_field']}"
        for w in warnings
    )


def _format_failed(failed: list[tuple[str, str]]) -> str:
    if not failed:
        return "  (none)"
    return "\n".join(f"  [{set_id}] {err}" for set_id, err in failed)


def main() -> None:
    log.info("Starting condition multiplier refresh")

    stats = refresh_all_sets()

    if stats["sets_failed"] > 0:
        overall_status = "Failed"
    elif stats["ungrouped_warnings"]:
        overall_status = "Warnings"
    else:
        overall_status = "Success"

    sep = "=" * 45
    summary = (
        f"\n{sep}\n"
        f"Condition multiplier refresh complete\n"
        f"  Sets processed       : {stats['sets_processed']}\n"
        f"  Sets failed          : {stats['sets_failed']}\n"
        f"  Multiplier rows written : {stats['rows_written']}\n"
        f"  Ungrouped cards      : {len(stats['ungrouped_warnings'])}\n"
        f"  Overall status       : {overall_status}\n"
        f"\nFailed sets:\n{_format_failed(stats['failed_sets'])}\n"
        f"\nUngrouped cards (excluded from grouping -- fix in TCGdex):\n"
        f"{_format_ungrouped(stats['ungrouped_warnings'])}\n"
        f"{sep}"
    )
    log.info("%s", summary)

    # Append summary fields to GITHUB_ENV when running in CI so the email
    # workflow can pick them up. No-op locally because GITHUB_ENV is unset.
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"MULTIPLIER_STATUS={overall_status}\n")
            f.write(f"MULTIPLIER_SUMMARY<<EOF\n{summary}\nEOF\n")


if __name__ == "__main__":
    main()
