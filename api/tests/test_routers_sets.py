"""
Tests for /sets/* endpoints.

Covers list_sets, get_set, list_cards_for_set, and get_prices_for_set --
including the recent additions for total_count, rarity_label, and the
DISTINCT ON optimization that returns only the latest snapshot per card.
"""


def test_list_sets_empty_when_no_data(client):
    response = client.get("/sets")
    assert response.status_code == 200
    assert response.json() == []


def test_list_sets_returns_set_with_total_count(client, sample_set, sample_cards):
    response = client.get("/sets")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    row = body[0]
    assert row["id"] == "base1"
    assert row["printed_total"] == 102
    # 2 cards in the fixture, no secrets.
    assert row["total_count"] == 2
    # No prices ingested -> stats are null.
    assert row["min_price"] is None
    assert row["avg_price"] is None
    assert row["max_price"] is None


def test_list_sets_aggregates_price_stats(client, sample_set, sample_cards, sample_snapshots):
    response = client.get("/sets")
    assert response.status_code == 200
    row = response.json()[0]
    # Snapshots include 0.50, 100.00, 120.00, 200.00 -- min/max/avg straightforward.
    assert float(row["min_price"]) == 0.50
    assert float(row["max_price"]) == 200.00


def test_get_set_returns_total_count(client, sample_set, sample_cards):
    response = client.get("/sets/base1")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "base1"
    assert body["total_count"] == 2


def test_get_set_404_when_unknown(client):
    response = client.get("/sets/nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_cards_for_set_populates_rarity_label(client, sample_set, sample_cards):
    response = client.get("/sets/base1/cards")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    # Cards are returned sorted by number.
    by_id = {r["id"]: r for r in rows}
    assert by_id["base1-4"]["rarity"] == "rare"
    assert by_id["base1-4"]["rarity_label"] == "Rare"
    assert by_id["base1-58"]["rarity_label"] == "Common"


def test_list_cards_for_set_404_when_unknown(client):
    response = client.get("/sets/missing/cards")
    assert response.status_code == 404


def test_get_prices_returns_only_latest_per_card_condition(client, sample_set, sample_cards, sample_snapshots):
    """The DISTINCT ON query must collapse the older Charizard NM row."""
    response = client.get("/sets/base1/cards/prices")
    assert response.status_code == 200
    prices = response.json()["prices"]

    # Charizard has two latest entries: NM Standard (latest of two) and NM Holofoil.
    charizard = prices["base1-4"]
    assert len(charizard) == 2
    nm_standard = next(p for p in charizard if p["variant"] is None)
    assert float(nm_standard["market_price"]) == 120.00
    nm_holo = next(p for p in charizard if p["variant"] == "holofoil")
    assert float(nm_holo["market_price"]) == 200.00

    # Pidgey has only one snapshot.
    assert len(prices["base1-58"]) == 1
    assert float(prices["base1-58"][0]["market_price"]) == 0.50


def test_get_prices_404_when_set_unknown(client):
    response = client.get("/sets/missing/cards/prices")
    assert response.status_code == 404


def test_get_prices_empty_when_set_has_no_prices(client, sample_set, sample_cards):
    response = client.get("/sets/base1/cards/prices")
    assert response.status_code == 200
    assert response.json()["prices"] == {}
