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
    start_offset: int = 0,
    include_history: bool = False,
    history_days: int = 7,
    include_ebay: bool = False,
) -> tuple[list[dict[str, Any]], int, int]:
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
        start_offset: Pagination offset to start from. Pass the value stored
            in the watermark to resume a previously interrupted run.
        include_history: Whether to request price history. Free tier returns
            3 days; API tier returns up to 180 days. Costs +1 credit per card.
        history_days: Number of history days to request when include_history
            is True. Ignored if include_history is False.
        include_ebay: Whether to request eBay/PSA graded prices. API tier
            only — silently ignored on the free tier. Costs +1 credit per card.

    Returns:
        tuple[list[dict], int, int]: A tuple of
            (card_data_list, credits_remaining, next_offset).
            card_data_list contains all card objects fetched this run.
            credits_remaining is from the last response header (-1 if absent).
            next_offset is 0 when the full set completed (start fresh next run),
            or the offset to resume from when interrupted mid-set.

    Raises:
        requests.HTTPError: If the API returns a non-2xx status after the
            retry attempt, meaning the run should stop.
        requests.RequestException: If a network error prevents the request.
    """
    api_key = _get_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}

    # Use a page size that stays within the free tier daily budget (100 credits).
    # fetchAllInSet=true is avoided because the API pre-calculates the full set
    # cost and rejects the request with 429 if credits are insufficient -- even
    # if we only want a partial set. Plain pagination fetches as many pages as
    # credits allow and stops gracefully when the budget runs out.
    PAGE_SIZE = 50

    # PPT_MAX_CARDS caps the total number of cards fetched per set. Used during
    # development to verify the pipeline without burning through API credits.
    # Remove this env var (or leave it unset) for normal production runs.
    _max_cards_raw = int(os.environ.get("PPT_MAX_CARDS") or 0)
    max_cards = _max_cards_raw if _max_cards_raw > 0 else None
    if max_cards is not None:
        log.warning("PPT_MAX_CARDS=%d is set -- limiting fetch to %d card(s) for testing.", max_cards, max_cards)
        PAGE_SIZE = max_cards

    params: dict[str, Any] = {
        "set": set_name,
        "limit": PAGE_SIZE,
        "sortBy": "cardNumber",
        "sortOrder": "asc",
    }
    if include_history:
        params["includeHistory"] = "true"
        params["days"] = history_days
    if include_ebay:
        params["includeEbay"] = "true"

    all_cards: list[dict[str, Any]] = []
    offset = start_offset
    credits_remaining = -1

    if start_offset > 0:
        log.info("Resuming set=%s from offset=%d", set_name, start_offset)

    while True:
        params["offset"] = offset
        log.debug("GET %s/cards params=%s", BASE_URL, params)

        try:
            response = _request_with_retry(f"{BASE_URL}/cards", headers=headers, params=params)
            response.raise_for_status()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                # Daily credit limit hit mid-pagination. Return the cards
                # collected so far and the offset to resume from next run.
                next_offset = offset  # resume from the page that just failed
                log.warning(
                    "Daily credit limit hit after %d cards (offset=%d). "
                    "Returning partial results -- resuming from offset=%d tomorrow.",
                    len(all_cards), offset, next_offset,
                )
                return all_cards, 0, next_offset
            raise  # Any other HTTP error should propagate normally.

        # Read credit consumption headers from every response.
        consumed = response.headers.get("X-API-Calls-Consumed", "?")
        credits_remaining = int(response.headers.get("X-RateLimit-Daily-Remaining", -1))
        log.info(
            "set=%s offset=%d credits_consumed=%s credits_remaining=%s",
            set_name, offset, consumed, credits_remaining,
        )

        payload = response.json()
        page_cards = payload.get("data", [])
        all_cards.extend(page_cards)
        offset += len(page_cards)

        metadata = payload.get("metadata", {})
        has_more = metadata.get("hasMore", False)

        if not has_more:
            # Full set completed -- reset offset to 0 so the next daily run
            # starts from card 1 for a fresh snapshot pass.
            log.info("Fetched all cards for set=%s (%d total). Offset reset to 0.", set_name, len(all_cards))
            return all_cards, credits_remaining, 0

        # If a test cap is set, simulate credit exhaustion after the first page
        # so the partial-results path is exercised without making more API calls.
        if max_cards is not None:
            log.warning(
                "PPT_MAX_CARDS=%d reached -- simulating credit exhaustion at offset=%d.",
                max_cards, offset,
            )
            return all_cards, 0, offset

        log.debug("Paginating: fetched %d so far, hasMore=True, next offset=%d", len(all_cards), offset)


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
        try:
            body = response.json()
        except Exception:
            body = response.text

        # Distinguish daily credit exhaustion from a per-minute rate limit.
        # Retrying after 60 seconds won't help if the daily budget is gone --
        # credits reset at midnight UTC, not after a backoff period.
        error_str = str(body).lower()
        if "daily credit limit" in error_str or "insufficient api credits" in error_str:
            log.error(
                "Daily credit limit exceeded. Response: %s. "
                "Credits reset at midnight UTC -- re-run this script tomorrow.",
                body,
            )
            response.raise_for_status()  # Raise immediately, no retry.

        log.warning("Minute rate limit hit (429). Response body: %s", body)
        log.warning("Waiting %ds before retrying...", RATE_LIMIT_BACKOFF_SECONDS)
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
