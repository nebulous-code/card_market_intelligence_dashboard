"""
Entry point for the priced-sets sync.

Reads priced_sets.yml and reconciles it into set_identifiers, which is what
decides the sets the nightly price run will fetch. Runs after the catalogue
ingest (a set must be in the sets table before a mapping can reference it)
and before the price run (which reads the rows this writes).

Costs nothing and touches no external API -- it is a small table write.

Usage (manual):
    uv run python run_sync_priced_sets.py

Usage (GitHub Actions):
    See .github/workflows/ingest.yml

Environment variables:
    DATABASE_URL  -- required: PostgreSQL connection string
"""

import logging
import os
import sys

from dotenv import find_dotenv, load_dotenv
from logging_setup import configure_logging

configure_logging()
load_dotenv(find_dotenv())

from priced_sets import PricedSetsError, load_priced_sets, sync_priced_sets  # noqa: E402

log = logging.getLogger(__name__)


def main() -> None:
    """Load the YAML, sync it, and report what changed."""
    try:
        entries = load_priced_sets()
    except PricedSetsError as e:
        log.error("%s", e)
        _write_summary("Failed", f"priced_sets.yml could not be loaded:\n  {e}")
        sys.exit(1)

    log.info("priced_sets.yml lists %d sets.", len(entries))

    try:
        result = sync_priced_sets(entries)
    except Exception as e:
        log.error("Failed to sync priced sets: %s", e)
        _write_summary("Failed", f"The sync failed against the database:\n  {e}")
        sys.exit(1)

    _report(len(entries), result)


def _report(total: int, result: dict) -> None:
    """Log the summary and hand it to GitHub Actions."""
    missing = result["missing_sets"]
    changed = result["inserted"] or result["updated"]

    if missing:
        status = "Warnings"
    elif changed:
        status = "Changed"
    else:
        status = "Success"

    lines = []
    for set_id, kind, value in result["inserted"]:
        lines.append(f"  + {set_id:10} {kind:12} {value}")
    for set_id, kind, value in result["updated"]:
        lines.append(f"  ~ {set_id:10} {kind:12} -> {value}")
    changes_section = "\n".join(lines) if lines else "  (no changes)"

    if missing:
        missing_section = "\n".join(
            f"  {set_id} -- not in the sets table. Either the catalogue ingest\n"
            f"     has not picked it up yet (it will retry tomorrow), or the\n"
            f"     set_id is a typo. Check https://tcgdex.dev for the exact id."
            for set_id in missing
        )
    else:
        missing_section = "  (none)"

    sep = "=" * 45
    summary = (
        f"\n{sep}\n"
        f"Priced-set sync complete\n"
        f"  Sets in YAML   : {total}\n"
        f"  Rows inserted  : {len(result['inserted'])}\n"
        f"  Rows updated   : {len(result['updated'])}\n"
        f"  Rows unchanged : {result['unchanged']}\n"
        f"  Overall status : {status}\n"
        f"\nChanges:\n{changes_section}\n"
        f"\nSets not yet in the catalogue:\n{missing_section}\n"
        f"{sep}"
    )
    log.info("%s", summary)
    _write_summary(status, summary)


def _write_summary(status: str, summary: str) -> None:
    """Write the sync status to the GitHub Actions environment file."""
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"PRICED_SETS_STATUS={status}\n")
            f.write(f"PRICED_SETS_SUMMARY<<EOF\n{summary}\nEOF\n")


if __name__ == "__main__":
    main()
