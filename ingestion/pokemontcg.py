"""
Client for the pokemontcg.io v2 API.

If POKEMONTCG_API_KEY is present in the environment it is sent as the
X-Api-Key header for higher rate limits. Unauthenticated requests work
without any API key — the key is never required.
"""

import os
from typing import Any

import requests

BASE_URL = "https://api.pokemontcg.io/v2"


def _headers() -> dict[str, str]:
    api_key = os.environ.get("POKEMONTCG_API_KEY")
    if api_key:
        return {"X-Api-Key": api_key}
    return {}


def get_set(set_id: str) -> dict[str, Any]:
    """Fetch metadata for a single set."""
    response = requests.get(f"{BASE_URL}/sets/{set_id}", headers=_headers(), timeout=30)
    response.raise_for_status()
    return response.json()["data"]


def get_cards(set_id: str) -> list[dict[str, Any]]:
    """
    Fetch all cards belonging to a set.

    pokemontcg.io paginates at 250 cards per page. For most sets a single
    request is sufficient; this function handles multi-page responses
    automatically.
    """
    cards: list[dict[str, Any]] = []
    page = 1
    page_size = 250

    while True:
        response = requests.get(
            f"{BASE_URL}/cards",
            headers=_headers(),
            params={"q": f"set.id:{set_id}", "pageSize": page_size, "page": page},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        cards.extend(payload["data"])

        # Stop when we have collected all cards.
        if len(cards) >= payload["totalCount"]:
            break
        page += 1

    return cards
