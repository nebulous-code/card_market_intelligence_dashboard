"""
Tests for ingestion/pokemonpricetracker.py.

The HTTP layer is mocked with `responses` so tests are deterministic.
time.sleep in the rate-limit retry path is patched to keep the suite fast.
"""

import pytest
import requests
import responses


@responses.activate
def test_fetch_prices_single_page(monkeypatch):
    """A single page with hasMore=False returns all cards and offset=0."""
    from pokemonpricetracker import BASE_URL, fetch_prices

    monkeypatch.setenv("POKEMON_PRICE_TRACKER_API_KEY", "secret")

    cards = [{"cardNumber": "1"}, {"cardNumber": "2"}]
    responses.add(
        responses.GET,
        f"{BASE_URL}/cards",
        json={"data": cards, "metadata": {"hasMore": False}},
        status=200,
        headers={"X-RateLimit-Daily-Remaining": "97", "X-API-Calls-Consumed": "3"},
    )

    result, credits, next_offset = fetch_prices("Base Set")
    assert [c["cardNumber"] for c in result] == ["1", "2"]
    assert credits == 97
    assert next_offset == 0


@responses.activate
def test_fetch_prices_paginates(monkeypatch):
    """When hasMore=True the loop fires another GET; final page resets offset."""
    from pokemonpricetracker import BASE_URL, fetch_prices

    monkeypatch.setenv("POKEMON_PRICE_TRACKER_API_KEY", "secret")
    monkeypatch.delenv("PPT_MAX_CARDS", raising=False)

    page1 = [{"cardNumber": str(i)} for i in range(50)]
    page2 = [{"cardNumber": str(i)} for i in range(50, 75)]

    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"data": page1, "metadata": {"hasMore": True}},
        status=200,
        headers={"X-RateLimit-Daily-Remaining": "100"},
    )
    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"data": page2, "metadata": {"hasMore": False}},
        status=200,
        headers={"X-RateLimit-Daily-Remaining": "98"},
    )

    cards, credits, next_offset = fetch_prices("Base Set")
    assert len(cards) == 75
    assert credits == 98
    assert next_offset == 0


@responses.activate
def test_fetch_prices_429_returns_partial(monkeypatch):
    """A 429 mid-pagination returns whatever was fetched plus a resume offset."""
    from pokemonpricetracker import BASE_URL, fetch_prices

    monkeypatch.setenv("POKEMON_PRICE_TRACKER_API_KEY", "secret")
    monkeypatch.delenv("PPT_MAX_CARDS", raising=False)
    # Skip the 60s backoff inside _request_with_retry.
    import pokemonpricetracker
    monkeypatch.setattr(pokemonpricetracker.time, "sleep", lambda *_: None)

    page1 = [{"cardNumber": "1"}, {"cardNumber": "2"}]
    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"data": page1, "metadata": {"hasMore": True}},
        status=200,
        headers={"X-RateLimit-Daily-Remaining": "5"},
    )
    # Two 429s in a row -- _request_with_retry will retry once and the second
    # 429 propagates as an HTTPError that fetch_prices catches and converts
    # to the partial-result return.
    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"error": "Too many requests"}, status=429,
    )
    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"error": "Too many requests"}, status=429,
    )

    cards, credits, next_offset = fetch_prices("Base Set", start_offset=0)
    assert len(cards) == 2
    assert credits == 0
    assert next_offset == 2  # resume from the page that failed


@responses.activate
def test_fetch_prices_resume_logs_offset(monkeypatch):
    """start_offset > 0 hits the resume log line."""
    from pokemonpricetracker import BASE_URL, fetch_prices

    monkeypatch.setenv("POKEMON_PRICE_TRACKER_API_KEY", "secret")

    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"data": [], "metadata": {"hasMore": False}}, status=200,
        headers={"X-RateLimit-Daily-Remaining": "100"},
    )
    cards, credits, next_offset = fetch_prices("Base Set", start_offset=20)
    assert cards == []
    assert next_offset == 0


@responses.activate
def test_fetch_prices_includes_history_and_ebay_params(monkeypatch):
    from pokemonpricetracker import BASE_URL, fetch_prices

    monkeypatch.setenv("POKEMON_PRICE_TRACKER_API_KEY", "secret")
    monkeypatch.delenv("PPT_MAX_CARDS", raising=False)

    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"data": [], "metadata": {"hasMore": False}}, status=200,
        headers={"X-RateLimit-Daily-Remaining": "100"},
    )

    fetch_prices("Base Set", include_history=True, history_days=180, include_ebay=True)
    sent = responses.calls[-1].request
    assert "includeHistory=true" in sent.url
    assert "days=180" in sent.url
    assert "includeEbay=true" in sent.url


@responses.activate
def test_fetch_prices_max_cards_simulates_exhaustion(monkeypatch):
    """PPT_MAX_CARDS forces the loop to stop after the first page."""
    from pokemonpricetracker import BASE_URL, fetch_prices

    monkeypatch.setenv("POKEMON_PRICE_TRACKER_API_KEY", "secret")
    monkeypatch.setenv("PPT_MAX_CARDS", "3")

    cards = [{"cardNumber": str(i)} for i in range(3)]
    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"data": cards, "metadata": {"hasMore": True}},
        status=200,
        headers={"X-RateLimit-Daily-Remaining": "100"},
    )

    result, credits, next_offset = fetch_prices("Base Set")
    assert len(result) == 3
    assert credits == 0
    assert next_offset == 3


@responses.activate
def test_request_with_retry_minute_limit_retries(monkeypatch):
    """Per-minute 429 -- retry succeeds the second time."""
    from pokemonpricetracker import BASE_URL, _request_with_retry

    import pokemonpricetracker
    monkeypatch.setattr(pokemonpricetracker.time, "sleep", lambda *_: None)

    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"error": "rate limit"}, status=429,
    )
    responses.add(
        responses.GET, f"{BASE_URL}/cards", json={"data": []}, status=200,
    )

    response = _request_with_retry(f"{BASE_URL}/cards")
    assert response.status_code == 200


@responses.activate
def test_request_with_retry_daily_limit_raises_immediately(monkeypatch):
    """Daily-credit 429 raises without sleeping, no retry."""
    from pokemonpricetracker import BASE_URL, _request_with_retry

    import pokemonpricetracker
    sleep_calls = []
    monkeypatch.setattr(pokemonpricetracker.time, "sleep", lambda s: sleep_calls.append(s))

    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"error": "Daily credit limit reached"}, status=429,
    )

    with pytest.raises(requests.HTTPError):
        _request_with_retry(f"{BASE_URL}/cards")

    assert sleep_calls == []


@responses.activate
def test_request_with_retry_unparseable_429_body(monkeypatch):
    """A 429 body that isn't JSON falls back to text() and triggers a retry."""
    from pokemonpricetracker import BASE_URL, _request_with_retry

    import pokemonpricetracker
    monkeypatch.setattr(pokemonpricetracker.time, "sleep", lambda *_: None)

    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        body="<html>Server error</html>", status=429,
    )
    responses.add(
        responses.GET, f"{BASE_URL}/cards", json={}, status=200,
    )

    response = _request_with_retry(f"{BASE_URL}/cards")
    assert response.status_code == 200


def test_credits_exhausted_threshold():
    from pokemonpricetracker import CREDIT_SAFETY_THRESHOLD, credits_exhausted

    assert credits_exhausted(0) is True
    assert credits_exhausted(CREDIT_SAFETY_THRESHOLD) is True
    assert credits_exhausted(CREDIT_SAFETY_THRESHOLD + 1) is False
    # -1 means "header missing", treated as not exhausted.
    assert credits_exhausted(-1) is False


def test_get_api_key_reads_environment(monkeypatch):
    from pokemonpricetracker import _get_api_key

    monkeypatch.setenv("POKEMON_PRICE_TRACKER_API_KEY", "abc123")
    assert _get_api_key() == "abc123"


@responses.activate
def test_fetch_prices_propagates_unexpected_http_error(monkeypatch):
    """A 500 response is not caught -- it should bubble up to the caller."""
    from pokemonpricetracker import BASE_URL, fetch_prices

    monkeypatch.setenv("POKEMON_PRICE_TRACKER_API_KEY", "secret")
    responses.add(
        responses.GET, f"{BASE_URL}/cards",
        json={"error": "boom"}, status=500,
    )

    with pytest.raises(requests.HTTPError):
        fetch_prices("Base Set")
