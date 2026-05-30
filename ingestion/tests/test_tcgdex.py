"""
Tests for ingestion/tcgdex.py -- HTTP client for the TCGdex API.

Uses the `responses` library to mock HTTP calls so tests never hit the
real API.
"""

import pytest
import requests
import responses


@responses.activate
def test_get_set_returns_json():
    from tcgdex import BASE_URL, get_set

    payload = {"id": "base1", "name": "Base Set", "cards": []}
    responses.add(
        responses.GET, f"{BASE_URL}/sets/base1", json=payload, status=200
    )

    assert get_set("base1") == payload


@responses.activate
def test_get_set_raises_on_404():
    from tcgdex import BASE_URL, get_set

    responses.add(responses.GET, f"{BASE_URL}/sets/nope", status=404)

    with pytest.raises(requests.HTTPError):
        get_set("nope")


@responses.activate
def test_get_cards_fetches_each_card():
    from tcgdex import BASE_URL, get_cards

    brief = [
        {"id": "base1-1", "name": "Alakazam"},
        {"id": "base1-2", "name": "Blastoise"},
    ]
    responses.add(responses.GET, f"{BASE_URL}/cards/base1-1", json={"id": "base1-1", "rarity": "Rare"}, status=200)
    responses.add(responses.GET, f"{BASE_URL}/cards/base1-2", json={"id": "base1-2", "rarity": "Rare"}, status=200)

    full = get_cards(brief)
    assert [c["id"] for c in full] == ["base1-1", "base1-2"]


@responses.activate
def test_get_cards_skips_404s():
    """A 404 on one card doesn't abort -- the rest still come back."""
    from tcgdex import BASE_URL, get_cards

    brief = [
        {"id": "base1-1", "name": "Alakazam"},
        {"id": "base1-bad", "name": "Missing"},
        {"id": "base1-3", "name": "Zapdos"},
    ]
    responses.add(responses.GET, f"{BASE_URL}/cards/base1-1", json={"id": "base1-1"}, status=200)
    responses.add(responses.GET, f"{BASE_URL}/cards/base1-bad", status=404)
    responses.add(responses.GET, f"{BASE_URL}/cards/base1-3", json={"id": "base1-3"}, status=200)

    full = get_cards(brief)
    assert [c["id"] for c in full] == ["base1-1", "base1-3"]


@responses.activate
def test_get_cards_skips_network_errors():
    """A connection error on one card doesn't abort the rest."""
    from tcgdex import BASE_URL, get_cards

    brief = [
        {"id": "base1-1", "name": "Alakazam"},
        {"id": "base1-2", "name": "Will fail"},
    ]
    responses.add(responses.GET, f"{BASE_URL}/cards/base1-1", json={"id": "base1-1"}, status=200)
    responses.add(
        responses.GET,
        f"{BASE_URL}/cards/base1-2",
        body=requests.ConnectionError("simulated network failure"),
    )

    full = get_cards(brief)
    assert [c["id"] for c in full] == ["base1-1"]


@responses.activate
def test_get_cards_handles_missing_name_gracefully():
    """Brief cards without a name still get fetched -- no key error."""
    from tcgdex import BASE_URL, get_cards

    brief = [{"id": "base1-1"}]  # no "name" field
    responses.add(responses.GET, f"{BASE_URL}/cards/base1-1", json={"id": "base1-1"}, status=200)

    assert get_cards(brief) == [{"id": "base1-1"}]
