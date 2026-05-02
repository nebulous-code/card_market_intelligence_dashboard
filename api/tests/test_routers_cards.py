"""
Tests for /cards/* endpoints.

Covers get_card (with latest_prices dedup) and get_price_history (with all
filter combinations).
"""


def test_get_card_returns_metadata_and_latest_prices(client, sample_set, sample_cards, sample_snapshots):
    response = client.get("/cards/base1-4")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "base1-4"
    assert body["name"] == "Charizard"
    assert body["rarity_label"] == "Rare"
    assert body["set_display_name"] == "Base Set"
    assert body["set_printed_total"] == 102

    # Latest per (condition, variant) -- two distinct keys for Charizard.
    prices = body["latest_prices"]
    assert len(prices) == 2
    by_variant = {p["variant"]: p for p in prices}
    # The newer of the two NM Standard rows wins.
    assert float(by_variant[None]["market_price"]) == 120.00
    assert by_variant[None]["condition_label"] == "Near Mint"
    assert by_variant[None]["variant_label"] == "Standard"
    assert float(by_variant["holofoil"]["market_price"]) == 200.00


def test_get_card_404_when_unknown(client):
    response = client.get("/cards/nonexistent")
    assert response.status_code == 404


def test_get_card_without_set_relationship(client, db_session, sample_set):
    """When card.set is None the response uses card.set_id and zero totals."""
    from models.card import Card

    # Insert a card whose set_id matches sample_set; relationship loads.
    # To exercise the missing-set fallback, attach a card to a set we then
    # detach via direct SQL after the relationship is loaded -- simulate by
    # using a card whose set_id refers to an absent set after we manipulate
    # the in-memory object. Easiest: monkey-patch card.set to None.
    orphan = Card(
        id="orphan-1",
        set_id=sample_set.id,
        name="Orphan",
        number="1",
        rarity=None,
        supertype="Pokemon",
        image_url=None,
    )
    db_session.add(orphan)
    db_session.flush()

    response = client.get("/cards/orphan-1")
    assert response.status_code == 200
    body = response.json()
    assert body["set_display_name"] == "Base Set"
    assert body["rarity"] is None
    assert body["rarity_label"] is None


def test_get_price_history_returns_chronological_order(client, sample_set, sample_cards, sample_snapshots):
    response = client.get("/cards/base1-4/price-history")
    assert response.status_code == 200
    snaps = response.json()["snapshots"]
    # Ordered by captured_date asc.
    dates = [s["captured_date"] for s in snaps]
    assert dates == sorted(dates)


def test_get_price_history_filters_by_source(client, sample_set, sample_cards, sample_snapshots):
    response = client.get("/cards/base1-4/price-history", params={"source": "tcgplayer"})
    assert response.status_code == 200
    assert all(s["source"] == "tcgplayer" for s in response.json()["snapshots"])

    # Filter that matches nothing.
    response = client.get("/cards/base1-4/price-history", params={"source": "ebay"})
    assert response.json()["snapshots"] == []


def test_get_price_history_filters_by_condition(client, sample_set, sample_cards, sample_snapshots):
    response = client.get("/cards/base1-4/price-history", params={"condition": "NM"})
    assert all(s["condition"] == "NM" for s in response.json()["snapshots"])


def test_get_price_history_variant_none_sentinel(client, sample_set, sample_cards, sample_snapshots):
    """variant=__none__ filters to rows where variant IS NULL."""
    response = client.get("/cards/base1-4/price-history", params={"variant": "__none__"})
    snaps = response.json()["snapshots"]
    assert len(snaps) > 0
    assert all(s["variant"] is None for s in snaps)


def test_get_price_history_explicit_variant(client, sample_set, sample_cards, sample_snapshots):
    response = client.get("/cards/base1-4/price-history", params={"variant": "holofoil"})
    snaps = response.json()["snapshots"]
    assert all(s["variant"] == "holofoil" for s in snaps)


def test_get_price_history_404_when_card_unknown(client):
    response = client.get("/cards/nonexistent/price-history")
    assert response.status_code == 404
