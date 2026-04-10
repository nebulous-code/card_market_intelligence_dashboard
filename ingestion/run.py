"""
Ingestion entry point.

Usage:
    python run.py --set-id base1

Fetches all cards for the given set from TCGdex and writes them to
the configured Neon PostgreSQL database. Safe to run multiple times —
sets and cards are upserted on repeat runs.
"""

import argparse

from dotenv import load_dotenv

load_dotenv()

from loader import load_set  # noqa: E402
from tcgdex import get_cards, get_set  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Pokémon card data into the database.")
    parser.add_argument(
        "--set-id",
        required=True,
        help="TCGdex set ID to ingest (e.g. base1)",
    )
    args = parser.parse_args()

    set_id: str = args.set_id
    print(f"Starting ingestion for set: {set_id}")

    print("  Fetching set metadata...")
    set_data = get_set(set_id)

    print(f"  Fetching cards for '{set_data['name']}' ({len(set_data.get('cards', []))} cards)...")
    cards = get_cards(set_data["cards"])
    print(f"  Fetched {len(cards)} cards from TCGdex.")

    load_set(set_data, cards)
    print("Ingestion complete.")


if __name__ == "__main__":
    main()
