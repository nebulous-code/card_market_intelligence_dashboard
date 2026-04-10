"""
HTTP client for the TCGdex REST API.

TCGdex is a free, open-source Pokemon TCG data API. It requires no API key
or account -- all requests are unauthenticated. This module provides two
functions that the ingestion script uses to fetch set and card data.

API base URL: https://api.tcgdex.net/v2/en
Full API reference: docs/tcgdex_api_specs.md
"""

from typing import Any

import requests

# The base URL for all API requests. The "en" segment specifies English
# as the language for card names and descriptions.
BASE_URL = "https://api.tcgdex.net/v2/en"


def get_set(set_id: str) -> dict[str, Any]:
    """
    Fetch metadata for a single Pokemon card set from TCGdex.

    The response includes the set name, series, release date, card count,
    logo and symbol URLs, and a brief list of every card in the set. The
    card list (set_data["cards"]) can be passed directly to get_cards()
    to avoid making this same request twice.

    Args:
        set_id: The TCGdex set identifier (e.g. "base1" for Base Set).
            A full list of valid IDs is available at tcgdex.dev.

    Returns:
        dict: The full set object from the TCGdex API response.

    Raises:
        requests.HTTPError: If the API returns a non-2xx status code,
            for example a 404 if the set ID does not exist.
        requests.RequestException: If the request fails due to a network
            error or timeout.
    """
    response = requests.get(f"{BASE_URL}/sets/{set_id}", timeout=30)

    # Raise an exception for any HTTP error status (4xx, 5xx).
    # This stops the ingestion run immediately with a clear error rather
    # than continuing with incomplete data.
    response.raise_for_status()

    return response.json()


def get_cards(brief_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Fetch full card detail for each card in the provided brief card list.

    TCGdex does not offer a bulk detail endpoint. The set response includes
    a brief list of cards (with only id, name, and image) but does not
    include rarity, category, or other fields needed by the database. This
    function fetches the full detail for each card individually.

    Accepts the brief card list from the set response rather than a set ID
    to avoid fetching the set a second time -- the caller already has it.

    Cards that return a non-200 response are skipped with a warning log
    rather than aborting the entire run. This means a single broken card
    in TCGdex's data will not prevent the rest of the set from being saved.

    Args:
        brief_cards: The list of brief card objects from the "cards" field
            of a set response. Each object must have an "id" field.

    Returns:
        list[dict]: Full card objects for all cards that were successfully
            fetched. May be shorter than brief_cards if any cards failed.
    """
    full_cards: list[dict[str, Any]] = []

    for i, brief in enumerate(brief_cards, start=1):
        card_id = brief["id"]

        # Log each card fetch with a progress counter so the operator can
        # see that the script is running and how far along it is.
        print(f"  [{i}/{len(brief_cards)}] Fetching card: {card_id} ({brief.get('name', '?')})")

        try:
            response = requests.get(f"{BASE_URL}/cards/{card_id}", timeout=30)
            response.raise_for_status()
            full_cards.append(response.json())

        except requests.HTTPError as e:
            # A 404 means TCGdex does not have detail data for this card.
            # Skip it and continue rather than aborting the entire run.
            print(f"  WARNING: Skipping {card_id} -- HTTP {e.response.status_code}")

        except requests.RequestException as e:
            # A network error (timeout, connection refused, etc.).
            # Skip this card and continue.
            print(f"  WARNING: Skipping {card_id} -- {e}")

    return full_cards
