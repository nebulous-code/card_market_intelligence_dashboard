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

# Load .env before importing any local modules that read env vars at import time.
load_dotenv(find_dotenv())

from loader import insert_price_snapshots          # noqa: E402
from pokemonpricetracker import credits_exhausted, fetch_prices  # noqa: E402
from watermark import get_all_sets, set_watermark  # noqa: E402
from sqlalchemy import create_engine                # noqa: E402
from sqlalchemy.orm import Session                  # noqa: E402

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

    for set_info in sets:
        set_id = set_info["id"]
        set_name = set_info["name"]
        log.info("--- Processing set: %s (%s) ---", set_id, set_name)

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
            # Pass the display name to PokemonPriceTracker -- it does not
            # recognise TCGdex IDs. The set_id is kept for watermark tracking.
            ppt_cards, credits_remaining, next_offset = fetch_prices(
                set_name=set_name,
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
            inserted = insert_price_snapshots(ppt_cards, set_id)
            log.info("Inserted %d snapshots for set %s.", inserted, set_id)
        except Exception as e:
            log.error("Failed to insert snapshots for set %s: %s. Skipping watermark.", set_id, e)
            sets_skipped += 1
            continue

        # Update the watermark with the next offset.
        # next_offset=0 means the full set completed; any other value means
        # the run was interrupted and the next run should resume from there.
        with Session(engine) as session:
            with session.begin():
                set_watermark(
                    session,
                    set_id,
                    backfilled=run_with_history,
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

    log.info(
        "Price ingestion run complete. sets_completed=%d sets_skipped=%d",
        sets_completed, sets_skipped,
    )


if __name__ == "__main__":
    main()
