"""
HTTP client for the PokemonPriceTracker REST API.

PokemonPriceTracker aggregates TCGPlayer market prices and eBay graded sale
data and exposes it via a single REST endpoint. This module wraps that
endpoint and handles authentication, pagination, credit-limit checking, and
rate-limit back-off so the rest of the ingestion pipeline never needs to
think about HTTP details.

API base URL: https://www.pokemonpricetracker.com/api/v2
Full reference: docs/POKEMON_PRICE_TRACKER_API.md
"""

import logging
import os
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

# Base URL for all PokemonPriceTracker API requests.
BASE_URL = "https://www.pokemonpricetracker.com/api/v2"

# Stop ingesting when the remaining daily credit balance drops to or below
# this threshold. Leaving a small buffer avoids accidentally burning the
# last credits on a set that may only partially complete.
CREDIT_SAFETY_THRESHOLD = 10

# How long to wait (in seconds) after receiving a 429 Too Many Requests
# response before retrying the same call once.
RATE_LIMIT_BACKOFF_SECONDS = 60


def _get_api_key() -> str:
    """
    Read the PokemonPriceTracker API key from the environment.

    Raises:
        KeyError: If POKEMON_PRICE_TRACKER_API_KEY is not set.

    Returns:
        str: The API key string.
    """
    return os.environ["POKEMON_PRICE_TRACKER_API_KEY"]


def fetch_prices(
    set_name: str,
    include_history: bool = False,
    history_days: int = 7,
    include_ebay: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """
    Fetch card price data for an entire set from PokemonPriceTracker.

    Sends a single request using fetchAllInSet=true to retrieve all cards in
    the set at once. Handles pagination automatically if the set has more
    cards than the API's default page size. Retries once on a 429 response
    with a 60-second back-off before giving up.

    Args:
        set_name: The set display name as stored in the database (e.g. "Base Set").
            PokemonPriceTracker does not use TCGdex IDs -- it matches on the
            display name from its own catalogue.
        include_history: Whether to request price history. Free tier returns
            3 days; API tier returns up to 180 days. Costs +1 credit per card.
        history_days: Number of history days to request when include_history
            is True. Ignored if include_history is False.
        include_ebay: Whether to request eBay/PSA graded prices. API tier
            only — silently ignored on the free tier. Costs +1 credit per card.

    Returns:
        tuple[list[dict], int]: A tuple of (card_data_list, credits_remaining).
            card_data_list contains all card objects from the API response.
            credits_remaining is the value of X-RateLimit-Daily-Remaining from
            the last response header, or -1 if the header was absent.

    Raises:
        requests.HTTPError: If the API returns a non-2xx status after the
            retry attempt, meaning the run should stop.
        requests.RequestException: If a network error prevents the request.
    """
    api_key = _get_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}

    params: dict[str, Any] = {
        "set": set_name,
        "fetchAllInSet": "true",
        "limit": 200,  # request the maximum page size to minimise round-trips
    }
    if include_history:
        params["includeHistory"] = "true"
        params["days"] = history_days
    if include_ebay:
        params["includeEbay"] = "true"

    all_cards: list[dict[str, Any]] = []
    offset = 0
    credits_remaining = -1

    while True:
        params["offset"] = offset
        log.debug("GET %s/cards params=%s", BASE_URL, params)

        response = _request_with_retry(f"{BASE_URL}/cards", headers=headers, params=params)
        response.raise_for_status()

        # Read credit consumption headers from every response.
        consumed = response.headers.get("X-API-Calls-Consumed", "?")
        credits_remaining = int(response.headers.get("X-RateLimit-Daily-Remaining", -1))
        log.info(
            "set=%s credits_consumed=%s credits_remaining=%s",
            set_name, consumed, credits_remaining,
        )

        payload = response.json()
        page_cards = payload.get("data", [])
        all_cards.extend(page_cards)

        metadata = payload.get("metadata", {})
        has_more = metadata.get("hasMore", False)

        if not has_more:
            break

        # Advance the offset by the number of cards returned this page.
        offset += len(page_cards)
        log.debug("Paginating: fetched %d so far, hasMore=True", len(all_cards))

    log.info("Fetched %d cards for set=%s", len(all_cards), set_name)
    return all_cards, credits_remaining


def _request_with_retry(url: str, **kwargs: Any) -> requests.Response:
    """
    Make an HTTP GET request, retrying once on a 429 rate-limit response.

    If the server responds with 429, the function waits RATE_LIMIT_BACKOFF_SECONDS
    seconds and tries once more. Any other error is raised immediately.

    Args:
        url: The URL to request.
        **kwargs: Additional keyword arguments forwarded to requests.get()
            (e.g. headers, params, timeout).

    Returns:
        requests.Response: The successful response object.

    Raises:
        requests.HTTPError: If the retry also returns a non-2xx status.
        requests.RequestException: On network-level errors.
    """
    kwargs.setdefault("timeout", 30)
    response = requests.get(url, **kwargs)

    if response.status_code == 429:
        log.warning(
            "Rate limited (429). Waiting %ds before retrying...",
            RATE_LIMIT_BACKOFF_SECONDS,
        )
        time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
        response = requests.get(url, **kwargs)

    return response


def credits_exhausted(credits_remaining: int) -> bool:
    """
    Return True if the remaining daily credit balance is too low to continue.

    The ingestion loop calls this after each set to decide whether to stop
    before attempting the next one, rather than making a call that might
    partially succeed or return a 402 Payment Required error.

    Args:
        credits_remaining: The value of X-RateLimit-Daily-Remaining from
            the most recent API response. Pass -1 if the header was absent
            (treated as not exhausted so the run doesn't halt unnecessarily).

    Returns:
        bool: True if the run should stop due to insufficient credits.
    """
    if credits_remaining == -1:
        return False  # Header absent — assume we are OK to continue.
    return credits_remaining <= CREDIT_SAFETY_THRESHOLD
