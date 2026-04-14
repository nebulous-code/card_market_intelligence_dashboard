"""
Entry point for the TCGdex card data ingestion pipeline.

This script fetches set and card metadata from the TCGdex API and writes
it to the sets and cards tables in PostgreSQL. It must be run before the
price ingestion script (run.py) because price snapshots reference cards
by foreign key.

Usage (manual):
    uv run python run_ingest.py --set-id base1

Usage via shell scripts:
    ./run_ingest.sh base1      (Linux / macOS / WSL)
    .\\run_ingest.ps1 base1    (Windows PowerShell)

The script is idempotent: sets and cards are upserted, so re-running it
for the same set will update any changed fields without creating duplicates.
"""

import argparse
import logging
import sys

from dotenv import find_dotenv, load_dotenv
from logging_setup import configure_logging

configure_logging()
load_dotenv(find_dotenv())

from loader import load_set    # noqa: E402
from set_resolver import SOURCE_TCGDEX, SetIdentifierNotFoundError, resolve_identifier  # noqa: E402
from tcgdex import get_cards, get_set  # noqa: E402

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a Pokemon TCG set from TCGdex.")
    parser.add_argument(
        "--set-id",
        required=True,
        help="Any recognizable set identifier (e.g. base1, 'Base Set').",
    )
    args = parser.parse_args()
    search_term: str = args.set_id

    # Resolve the canonical TCGdex ID through the set_identifiers table.
    # This ensures we always use the exact ID TCGdex expects, and fails loudly
    # if the mapping is missing rather than silently calling the API with a
    # wrong identifier.
    try:
        tcgdex_id = resolve_identifier(search_term, SOURCE_TCGDEX)
    except SetIdentifierNotFoundError as e:
        log.error("%s", e)
        sys.exit(1)

    log.info("Resolved '%s' → TCGdex ID '%s'", search_term, tcgdex_id)
    log.info("Fetching set metadata for: %s", tcgdex_id)
    try:
        set_data = get_set(tcgdex_id)
    except Exception as e:
        log.error("Failed to fetch set '%s' from TCGdex: %s", tcgdex_id, e)
        sys.exit(1)

    brief_cards = set_data.get("cards", [])
    log.info("Set '%s' has %d cards. Fetching full card detail...", set_data.get("name"), len(brief_cards))

    cards = get_cards(brief_cards)
    log.info("Fetched %d cards successfully.", len(cards))

    load_set(set_data, cards)
    log.info("Ingestion complete for set: %s (%s)", set_id, set_data.get("name"))


if __name__ == "__main__":
    main()
