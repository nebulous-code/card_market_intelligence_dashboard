"""
Tests for routers.palette.

The palette is seeded by migration 012 itself, so the API returns the
same eight colors on every fresh test database. Tests verify the order
matches ``display_order`` and that adding a row via SQL flows through
to the response.
"""

from sqlalchemy import text


def test_palette_returns_seeded_colors_in_order(client):
    response = client.get("/palette")
    assert response.status_code == 200
    body = response.json()
    # Migration 012 seeds 8 colors; the first three are the canonical
    # Magikarp red / gold / muted grey-blue.
    assert body["colors"][:3] == ["#E8412A", "#F5C842", "#A0A0B8"]
    assert len(body["colors"]) == 8


def test_palette_includes_added_row(client, db_session):
    """Inserting a row at a higher display_order appends to the response."""
    db_session.execute(
        text(
            "INSERT INTO palette_colors (color_hex, display_order) "
            "VALUES (:hex, :ord)"
        ),
        {"hex": "#123456", "ord": 99},
    )
    db_session.flush()
    response = client.get("/palette")
    assert response.json()["colors"][-1] == "#123456"
