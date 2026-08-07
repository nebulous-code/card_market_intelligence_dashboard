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


def test_list_sets_excludes_a_set_with_no_prices(client, sample_set, sample_cards):
    """A catalogued but unpriced set must not appear in the set list.

    The catalogue ingest puts every set TCGdex publishes into the database so
    collection uploads can be validated against real sets. Only a fraction of
    those are ones we buy price data for, and a set card that opens onto an
    empty page is worse than no card at all. The upload template dropdown is
    deliberately NOT filtered this way -- see the endpoint docstring.
    """
    response = client.get("/sets")
    assert response.status_code == 200
    assert response.json() == []


def test_list_sets_returns_set_with_total_count(
    client, sample_set, sample_cards, sample_snapshots
):
    response = client.get("/sets")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    row = body[0]
    assert row["id"] == "base1"
    assert row["printed_total"] == 102
    # 2 cards in the fixture, no secrets.
    assert row["total_count"] == 2


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


def test_set_prices_lead_with_the_plainest_printing(client, db_session, sample_set, sample_cards):
    """The card table quotes the first NM row, so ordering decides the price.

    The SQL must lead its ORDER BY with the DISTINCT ON columns, which sorts
    variants alphabetically -- and Postgres puts NULLs last, so "1st_edition"
    led and Standard trailed. Every dual-printing card was quoted at its most
    collectible price: Aerodactyl showed $73.67 (1st Ed. Holo) rather than
    $37.03 (Holofoil).
    """
    from datetime import date, datetime
    from decimal import Decimal

    from models.card import PriceSnapshot

    at = datetime(2026, 8, 7, 12, 0)
    for variant, price in [
        ("1st_edition_holofoil", "73.67"),   # sorts first alphabetically
        ("holofoil", "37.03"),               # the plainer printing we want
    ]:
        db_session.add(
            PriceSnapshot(
                card_id="base1-4", source="tcgplayer", condition="NM",
                variant=variant, market_price=Decimal(price),
                captured_at=at, captured_date=date(2026, 8, 7),
            )
        )
    db_session.flush()

    rows = client.get("/sets/base1/cards/prices").json()["prices"]["base1-4"]
    nm = [r for r in rows if r["condition"] == "NM"]
    assert float(nm[0]["market_price"]) == 37.03
    assert nm[0]["variant_label"] == "Holofoil"


def test_set_prices_prefer_standard_when_it_exists(client, db_session, sample_set, sample_cards):
    """Standard outranks every decorated printing."""
    from datetime import date, datetime
    from decimal import Decimal

    from models.card import PriceSnapshot

    at = datetime(2026, 8, 7, 12, 0)
    for variant, price in [("reverse_holofoil", "0.40"), (None, "0.17")]:
        db_session.add(
            PriceSnapshot(
                card_id="base1-58", source="tcgplayer", condition="NM",
                variant=variant, market_price=Decimal(price),
                captured_at=at, captured_date=date(2026, 8, 7),
            )
        )
    db_session.flush()

    rows = client.get("/sets/base1/cards/prices").json()["prices"]["base1-58"]
    nm = [r for r in rows if r["condition"] == "NM"]
    assert float(nm[0]["market_price"]) == 0.17
    assert nm[0]["variant_label"] == "Standard"
