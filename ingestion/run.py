"""
Entry point for the Milestone 2 price ingestion pipeline.

This script fetches current card prices (and optionally price history and
eBay/graded data) from the PokemonPriceTracker API and writes them to the
price_snapshots table in PostgreSQL.

The script is designed to be run nightly via GitHub Actions. It automatically
discovers all sets currently in the database and prices each one in turn,
stopping gracefully if the daily credit limit is approached.

Usage (manual):
    uv run python run.py

Usage (GitHub Actions):
    See .github/workflows/ingest.yml

Environment variables (see .env.example):
    POKEMON_PRICE_TRACKER_API_KEY  -- required: API key for PokemonPriceTracker
    PPT_INCLUDE_HISTORY            -- "true" to fetch price history (API tier)
    PPT_HISTORY_DAYS               -- number of history days to request (default 7)
    PPT_INCLUDE_EBAY               -- "true" to fetch eBay graded prices (API tier)

The TCGdex ingestion (run.py --set-id) is separate and unchanged. Run that
first to populate the sets and cards tables before running this script.
"""

import logging
import os
import sys

from dotenv import find_dotenv, load_dotenv
from logging_setup import configure_logging

# Configure logging before loading any local modules so that log lines
# from pokemonpricetracker.py, watermark.py, and loader.py all go to
# both the console and ingestion.log.
configure_logging()

# Load .env before importing any local modules that read env vars at import time.
load_dotenv(find_dotenv())

from loader import insert_price_snapshots                                    # noqa: E402
from pokemonpricetracker import credits_exhausted, fetch_prices              # noqa: E402
from set_resolver import SOURCE_PPT, SetIdentifierNotFoundError, resolve_identifier  # noqa: E402
from watermark import get_all_sets, set_watermark                            # noqa: E402
from sqlalchemy import create_engine                                         # noqa: E402
from sqlalchemy.orm import Session                                           # noqa: E402

log = logging.getLogger(__name__)


def _bool_env(key: str, default: bool = False) -> bool:
    """Read a boolean environment variable. Accepts 'true'/'false' (case-insensitive)."""
    return os.environ.get(key, str(default)).strip().lower() == "true"


def main() -> None:
    """
    Orchestrate the nightly price ingestion run.

    Steps:
      1. Read tier configuration from environment variables.
      2. Query the database for all known set IDs.
      3. For each set, call PokemonPriceTracker and insert price snapshots.
      4. Update the watermark for the set on success.
      5. Stop gracefully if the daily credit limit is running low.

    Sets that have already been backfilled are fetched with current prices
    only on subsequent runs. Sets that have not yet been backfilled are
    fetched with full history on the first run (API tier only).

    Returns:
        None
    """
    # Read tier flags from environment. These control what is requested from
    # PokemonPriceTracker. No code changes are needed to switch tiers --
    # only these env vars and the API key need to change.
    include_history = _bool_env("PPT_INCLUDE_HISTORY", default=False)
    history_days = int(os.environ.get("PPT_HISTORY_DAYS", "7"))
    include_ebay = _bool_env("PPT_INCLUDE_EBAY", default=False)

    log.info(
        "Starting price ingestion run. include_history=%s history_days=%s include_ebay=%s",
        include_history, history_days, include_ebay,
    )
    log.debug(
        "Raw env values: PPT_INCLUDE_HISTORY=%r PPT_HISTORY_DAYS=%r PPT_INCLUDE_EBAY=%r",
        os.environ.get("PPT_INCLUDE_HISTORY"),
        os.environ.get("PPT_HISTORY_DAYS"),
        os.environ.get("PPT_INCLUDE_EBAY"),
    )

    # Open a single session for watermark reads/writes throughout the run.
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

    with Session(engine) as session:
        sets = get_all_sets(session)

    if not sets:
        log.warning("No sets found in the database. Run the TCGdex ingestion first.")
        sys.exit(0)

    log.info("Found %d sets to process: %s", len(sets), [s["id"] for s in sets])

    sets_completed = 0
    sets_skipped = 0

    # Accumulators for the run-level summary logged at the end.
    run_total_matched = 0
    run_total_skipped = 0
    run_total_errors = 0
    run_set_lines: list[str] = []      # per-set breakdown lines for the summary
    run_warning_lines: list[str] = []  # skipped-card detail lines for the summary

    for set_info in sets:
        set_id = set_info["id"]
        set_name = set_info["name"]
        log.info("--- Processing set: %s (%s) ---", set_id, set_name)

        # Resolve the PPT display name through the set_identifiers table.
        # This fails loudly if the mapping is missing rather than silently
        # calling the API with a wrong name and getting 0 results.
        try:
            ppt_name = resolve_identifier(set_id, SOURCE_PPT)
        except SetIdentifierNotFoundError as e:
            log.error("%s", e)
            sets_skipped += 1
            continue

        # Check whether this set needs a backfill or just a current-price run.
        with Session(engine) as session:
            watermark = None
            try:
                from watermark import get_watermark
                watermark = get_watermark(session, set_id)
            except Exception:
                pass  # First run -- no watermark exists yet.

        already_backfilled = watermark.get("backfilled", False) if watermark else False
        start_offset = watermark.get("last_offset", 0) if watermark else 0
        if start_offset > 0:
            log.info("Watermark found for set %s at offset=%d -- resuming.", set_id, start_offset)

        # Determine whether to include history on this run.
        # On the API tier (include_history=True), pull history on the first run
        # per set. On subsequent runs, history accumulates from daily snapshots.
        run_with_history = include_history and not already_backfilled
        run_with_ebay = include_ebay

        try:
            ppt_cards, credits_remaining, next_offset = fetch_prices(
                set_name=ppt_name,
                start_offset=start_offset,
                include_history=run_with_history,
                history_days=history_days,
                include_ebay=run_with_ebay,
            )
        except Exception as e:
            log.error("Failed to fetch prices for set %s: %s. Skipping.", set_id, e)
            sets_skipped += 1
            continue

        if not ppt_cards:
            log.warning("No price data returned for set %s. Skipping.", set_id)
            sets_skipped += 1
            continue

        # Write price snapshots for this set.
        try:
            stats = insert_price_snapshots(ppt_cards, set_id)
        except Exception as e:
            log.error("Failed to insert snapshots for set %s: %s. Skipping watermark.", set_id, e)
            sets_skipped += 1
            continue

        # Log the per-set summary block.
        skipped_detail = ", ".join(
            f"{cid} ({name})" for cid, name, _ in stats["skipped_cards"]
        ) or "none"
        sep = "─" * 45
        log.info(
            "\n%s\n%s ingestion complete\n"
            "  PPT cards returned : %d\n"
            "  Matched            : %d\n"
            "  Skipped            : %d\n"
            "  Errors             : %d\n"
            "  Skipped cards      : %s\n%s",
            sep, set_name,
            stats["ppt_total"], stats["matched"], stats["skipped"], stats["errors"],
            skipped_detail, sep,
        )

        # Accumulate into run-level totals.
        run_total_matched += stats["matched"]
        run_total_skipped += stats["skipped"]
        run_total_errors  += stats["errors"]
        run_set_lines.append(
            f"  {set_name:<12} {stats['matched']}/{stats['ppt_total']} matched, {stats['skipped']} skipped"
        )
        for cid, name, reason in stats["skipped_cards"]:
            run_warning_lines.append(f"  [{set_id}] {cid} ({name}) — {reason}")

        # Update the watermark with the next offset.
        # next_offset=0 means the full set completed; any other value means
        # the run was interrupted and the next run should resume from there.
        # Only mark backfilled=True when the set fully completed this run
        # (next_offset=0 means no more pages). If the run was interrupted
        # mid-set, keep backfilled=False so the next resume still requests
        # history for the remaining cards.
        set_completed = next_offset == 0
        with Session(engine) as session:
            with session.begin():
                set_watermark(
                    session,
                    set_id,
                    backfilled=run_with_history and set_completed,
                    last_offset=next_offset,
                )
        if next_offset == 0:
            log.info("Set %s fully completed this run.", set_id)
        else:
            log.info("Set %s partially completed. Next run resumes at offset=%d.", set_id, next_offset)
        sets_completed += 1

        # Check if the daily credit limit is running low. If so, stop now
        # rather than starting a set that may only partially complete.
        if credits_exhausted(credits_remaining):
            log.warning(
                "Daily credit limit nearly exhausted (%d remaining). "
                "Stopping after %d sets. Remaining sets will be processed tomorrow.",
                credits_remaining, sets_completed,
            )
            break

    # --- Run-level summary ---
    from datetime import date as _date
    run_date = _date.today().isoformat()

    if run_total_errors > 0:
        overall_status = "❌ Failed"
    elif run_total_skipped > 0:
        overall_status = "⚠️ Warnings"
    else:
        overall_status = "✅ Success"

    warnings_section = "\n".join(run_warning_lines) if run_warning_lines else "  (none)"
    per_set_section = "\n".join(run_set_lines) if run_set_lines else "  (no sets processed)"

    sep = "═" * 45
    summary = (
        f"\n{sep}\n"
        f"Nightly ingestion complete — {run_date}\n"
        f"  Sets processed : {sets_completed}\n"
        f"  Total matched  : {run_total_matched}\n"
        f"  Total skipped  : {run_total_skipped}\n"
        f"  Total errors   : {run_total_errors}\n"
        f"  Overall status : {overall_status}\n"
        f"\nPer-set breakdown:\n{per_set_section}\n"
        f"\nWarnings:\n{warnings_section}\n"
        f"{sep}"
    )
    log.info("%s", summary)

    # Write summary variables to GitHub Actions environment file when running
    # in CI. This is a no-op locally because GITHUB_ENV is not set there.
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"RUN_DATE={run_date}\n")
            f.write(f"RUN_STATUS={overall_status}\n")
            f.write(f"EMAIL_BODY<<EOF\n{summary}\nEOF\n")


if __name__ == "__main__":
    main()
