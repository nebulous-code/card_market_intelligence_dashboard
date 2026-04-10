"""
Client for the TCGdex REST API.

TCGdex is free and open source — no API key or authentication required.
Base URL: https://api.tcgdex.net/v2/en
"""

from typing import Any

import requests

BASE_URL = "https://api.tcgdex.net/v2/en"


def get_set(set_id: str) -> dict[str, Any]:
    """
    Fetch metadata for a single set.

    The response includes a `cards` array of CardBrief objects which can be
    passed directly to get_cards() to avoid a redundant network request.
    """
    response = requests.get(f"{BASE_URL}/sets/{set_id}", timeout=30)
    response.raise_for_status()
    return response.json()


def get_cards(brief_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Fetch full card detail for each card in the provided brief list.

    Accepts the `cards` array embedded in a set response so the caller
    does not need to re-fetch the set. Each full card is fetched individually
    via GET /cards/{cardId} — TCGdex has no bulk detail endpoint.

    Cards that return a non-200 response are skipped with a warning rather
    than aborting the entire ingestion run.
    """
    full_cards: list[dict[str, Any]] = []

    for i, brief in enumerate(brief_cards, start=1):
        card_id = brief["id"]
        print(f"  [{i}/{len(brief_cards)}] Fetching card: {card_id} ({brief.get('name', '?')})")

        try:
            response = requests.get(f"{BASE_URL}/cards/{card_id}", timeout=30)
            response.raise_for_status()
            full_cards.append(response.json())
        except requests.HTTPError as e:
            print(f"  WARNING: Skipping {card_id} — HTTP {e.response.status_code}")
        except requests.RequestException as e:
            print(f"  WARNING: Skipping {card_id} — {e}")

    return full_cards
