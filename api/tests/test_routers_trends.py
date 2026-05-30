"""
Tests for the /trends/* endpoints.

Covers list_sets_with_multipliers (which sets show up vs. don't) and
get_condition_multipliers (response shape, ordering, label join, error
paths). Fixtures live in the API conftest -- `sample_multipliers` seeds
a representative slice of the condition_multipliers table for sample_set.
"""


def test_sets_with_multipliers_excludes_sets_with_no_data(client, sample_set):
    """A set without any multiplier rows is not returned."""
    response = client.get("/trends/sets-with-multipliers")
    assert response.status_code == 200
    assert response.json() == {"sets": []}


def test_sets_with_multipliers_returns_seeded_sets(client, sample_multipliers, sample_set):
    response = client.get("/trends/sets-with-multipliers")
    assert response.status_code == 200
    body = response.json()
    assert body["sets"] == [
        {"set_id": sample_set.id, "set_display_name": sample_set.name},
    ]


def test_sets_with_multipliers_orders_newest_first(client, db_session, sample_multipliers, sample_set):
    """Two sets with multiplier rows: newer release_date sorts first."""
    from datetime import date, datetime
    from decimal import Decimal

    from models.condition_multiplier import ConditionMultiplier
    from models.set import Set

    # Add a second, newer set + one multiplier row so it qualifies.
    # The flush between Set and ConditionMultiplier matters: SQLAlchemy
    # doesn't always order pending inserts by FK dependency when both
    # are added in the same uow, so the multiplier's set_id FK can fail
    # without an explicit flush.
    newer = Set(
        id="modern1",
        name="Modern Set",
        series="Modern",
        printed_total=100,
        release_date=date(2024, 1, 1),
    )
    db_session.add(newer)
    db_session.flush()

    db_session.add(
        ConditionMultiplier(
            set_id="modern1",
            grouping_type="rarity",
            grouping_value="rare",
            from_condition="NM",
            to_condition="LP",
            multiplier=Decimal("0.6000"),
            data_points=10,
            last_refreshed=datetime(2026, 5, 1, 12, 0),
        )
    )
    db_session.flush()

    response = client.get("/trends/sets-with-multipliers")
    body = response.json()
    assert [s["set_id"] for s in body["sets"]] == ["modern1", sample_set.id]


def test_get_condition_multipliers_full_response(client, sample_multipliers, sample_set):
    response = client.get(
        "/trends/condition-multipliers",
        params={"set_id": sample_set.id, "grouping_type": "rarity"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["set_id"] == sample_set.id
    assert body["set_display_name"] == sample_set.name
    assert body["grouping_type"] == "rarity"
    assert body["last_refreshed"] is not None

    # Two rarities seeded -- 'rare' has display_order=500, 'common' has 900,
    # so rare sorts first (rarest at top).
    grouping_values = [g["grouping_value"] for g in body["groupings"]]
    assert grouping_values == ["rare", "common"]

    # Display labels come from canonical_rarities.
    grouping_labels = [g["grouping_label"] for g in body["groupings"]]
    assert grouping_labels == ["Rare", "Common"]


def test_get_condition_multipliers_transitions_present_only_when_seeded(client, sample_multipliers, sample_set):
    """Common rarity has only 3 transitions seeded; the rest are absent."""
    response = client.get(
        "/trends/condition-multipliers",
        params={"set_id": sample_set.id, "grouping_type": "rarity"},
    )
    common = next(g for g in response.json()["groupings"] if g["grouping_value"] == "common")
    pairs = {(t["from_condition"], t["to_condition"]) for t in common["transitions"]}
    assert pairs == {("NM", "LP"), ("NM", "MP"), ("LP", "MP")}


def test_get_condition_multipliers_supertype_grouping(client, sample_multipliers, sample_set):
    response = client.get(
        "/trends/condition-multipliers",
        params={"set_id": sample_set.id, "grouping_type": "supertype"},
    )
    assert response.status_code == 200
    body = response.json()
    # Supertype values are alphabetical (Pokemon < Trainer).
    grouping_values = [g["grouping_value"] for g in body["groupings"]]
    assert grouping_values == ["Pokemon", "Trainer"]
    # Supertype labels are the raw value -- no canonical join.
    assert all(g["grouping_label"] == g["grouping_value"] for g in body["groupings"])


def test_get_condition_multipliers_invalid_grouping_type_returns_422(client, sample_multipliers, sample_set):
    response = client.get(
        "/trends/condition-multipliers",
        params={"set_id": sample_set.id, "grouping_type": "bogus"},
    )
    assert response.status_code == 422
    assert "grouping_type" in response.json()["detail"]


def test_get_condition_multipliers_unknown_set_returns_404(client):
    response = client.get(
        "/trends/condition-multipliers",
        params={"set_id": "nonexistent", "grouping_type": "rarity"},
    )
    assert response.status_code == 404


def test_get_condition_multipliers_empty_groupings_when_no_rows(client, sample_set):
    """Set exists but has no multiplier rows -> 200 with empty groupings list."""
    response = client.get(
        "/trends/condition-multipliers",
        params={"set_id": sample_set.id, "grouping_type": "rarity"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["groupings"] == []
    assert body["last_refreshed"] is None


def test_get_condition_multipliers_unknown_rarity_falls_back_to_raw_value(
    client, db_session, sample_set
):
    """A grouping_value that's not in canonical_rarities still appears,
    using the raw value as both value and label and sorting after the
    canonical rarities."""
    from datetime import datetime
    from decimal import Decimal

    from models.condition_multiplier import ConditionMultiplier

    db_session.add(
        # 'rare' is canonical -- sorts at display_order=500.
        ConditionMultiplier(
            set_id=sample_set.id,
            grouping_type="rarity",
            grouping_value="rare",
            from_condition="NM",
            to_condition="LP",
            multiplier=Decimal("0.6000"),
            data_points=10,
            last_refreshed=datetime(2026, 5, 1, 12, 0),
        )
    )
    db_session.add(
        # An off-list rarity that shouldn't normally appear post-FK on
        # cards.rarity, but the response code defends against it anyway.
        ConditionMultiplier(
            set_id=sample_set.id,
            grouping_type="rarity",
            grouping_value="weirdrarity",
            from_condition="NM",
            to_condition="LP",
            multiplier=Decimal("0.5000"),
            data_points=5,
            last_refreshed=datetime(2026, 5, 1, 12, 0),
        )
    )
    db_session.flush()

    response = client.get(
        "/trends/condition-multipliers",
        params={"set_id": sample_set.id, "grouping_type": "rarity"},
    )
    body = response.json()
    grouping_values = [g["grouping_value"] for g in body["groupings"]]
    # Canonical 'rare' first, off-list after.
    assert grouping_values == ["rare", "weirdrarity"]
    weird = next(g for g in body["groupings"] if g["grouping_value"] == "weirdrarity")
    assert weird["grouping_label"] == "weirdrarity"
