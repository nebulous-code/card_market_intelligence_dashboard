"""
Tests for /reference/* endpoints.

The canonical tables are seeded by migrations 008/009, so these tests rely
on that data without having to insert anything.
"""


def test_list_conditions_returns_seeded_canon(client):
    response = client.get("/reference/conditions")
    assert response.status_code == 200
    data = response.json()
    values = {row["value"] for row in data}
    assert {"NM", "LP", "PSA-10", "BGS-9.5"} <= values
    # Sorted ascending by display_order.
    orders = [row["display_order"] for row in data]
    assert orders == sorted(orders)


def test_list_variants_includes_standard_null(client):
    response = client.get("/reference/variants")
    assert response.status_code == 200
    data = response.json()
    # The "Standard" canonical row stores value = NULL.
    standard = [row for row in data if row["value"] is None]
    assert len(standard) == 1
    assert standard[0]["label"] == "Standard"


def test_list_rarities_ordered_rarest_first(client):
    response = client.get("/reference/rarities")
    assert response.status_code == 200
    data = response.json()
    # Migration 009 seeds 8 canonical rarities, rarest first.
    assert len(data) == 8
    assert data[0]["value"] == "hyper_rare"
    assert data[-1]["value"] == "common"
