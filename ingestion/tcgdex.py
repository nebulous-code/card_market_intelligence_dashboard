"""
Client for the TCGdex REST API.

TCGdex is free and open source — no API key or authentication required.
Base URL: https://api.tcgdex.net/v2/en
"""

from typing import Any

import requests

BASE_URL = "https://api.tcgdex.net/v2/en"


def get_set(set_id: str) -> dict[str, Any]:
    """Fetch metadata for a single set."""
    response = requests.get(f"{BASE_URL}/sets/{set_id}", timeout=30)
    response.raise_for_status()
    return response.json()


def get_cards(set_id: str) -> list[dict[str, Any]]:
    """
    Fetch full card details for every card in a set.

    The brief card list (id, name, image) is embedded in the set response.
    Each card's full detail (rarity, category, etc.) is then fetched
    individually via /cards/{card_id}.
    """
    set_response = requests.get(f"{BASE_URL}/sets/{set_id}", timeout=30)
    set_response.raise_for_status()
    brief_cards: list[dict[str, Any]] = set_response.json().get("cards", [])

    full_cards: list[dict[str, Any]] = []
    for brief in brief_cards:
        card_response = requests.get(f"{BASE_URL}/cards/{brief['id']}", timeout=30)
        card_response.raise_for_status()
        full_cards.append(card_response.json())

    return full_cards
