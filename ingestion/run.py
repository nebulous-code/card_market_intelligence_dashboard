"""
Entry point for the Pokemon card data ingestion script.

This script fetches card and set data from the TCGdex API and saves it
to the PostgreSQL database. It is designed to be run manually from the
command line and is safe to run multiple times -- existing data is updated
rather than duplicated.

Usage:
    python run.py --set-id base1

The --set-id argument is required and must be a valid TCGdex set identifier.
A full list of set IDs is available at https://tcgdex.dev.
"""

import argparse

from dotenv import load_dotenv

# Load the .env file before importing loader or tcgdex, because those
# modules read environment variables at import time. If the .env file is
# not loaded first, DATABASE_URL will not be available and the import
# will fail with a KeyError.
load_dotenv()

from loader import load_set       # noqa: E402
from tcgdex import get_cards, get_set  # noqa: E402


def main() -> None:
    """
    Parse command line arguments and run the ingestion pipeline.

    The pipeline has three steps:
      1. Fetch set metadata from TCGdex.
      2. Fetch full card details for every card in the set.
      3. Write the set and all cards to the database.

    Returns:
        None
    """
    # Set up the command line argument parser.
    # argparse handles --help automatically and produces a clean error
    # message if required arguments are missing.
    parser = argparse.ArgumentParser(description="Ingest Pokemon card data into the database.")
    parser.add_argument(
        "--set-id",
        required=True,
        help="TCGdex set ID to ingest (e.g. base1)",
    )
    args = parser.parse_args()

    set_id: str = args.set_id
    print(f"Starting ingestion for set: {set_id}")

    # Step 1: Fetch the set metadata.
    # The response also contains the brief card list we need for step 2.
    print("  Fetching set metadata...")
    set_data = get_set(set_id)

    # Step 2: Fetch full card details.
    # The number of cards in the set is shown upfront so the operator knows
    # how many requests to expect before they start appearing in the log.
    print(f"  Fetching cards for '{set_data['name']}' ({len(set_data.get('cards', []))} cards)...")
    cards = get_cards(set_data["cards"])
    print(f"  Fetched {len(cards)} cards from TCGdex.")

    # Step 3: Write everything to the database in a single transaction.
    load_set(set_data, cards)

    print("Ingestion complete.")


if __name__ == "__main__":
    main()
