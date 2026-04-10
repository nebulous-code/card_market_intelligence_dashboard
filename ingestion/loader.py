"""
Transforms TCGdex API responses and writes them to the database.

Idempotency rules:
- Sets and cards are upserted (insert or update on conflict).

Price ingestion is not included in Milestone 1. It will be added in
Milestone 2 via the eBay completed sales API.
"""

import os
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def _parse_date(value: str | None):
    """Parse a TCGdex date string (YYYY-MM-DD) to a Python date, or None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _asset_url(base: str | None) -> str | None:
    """
    Resolve a TCGdex asset base URL to a usable image URL.

    TCGdex returns bare base URLs for logos and symbols (no file extension).
    Append .png so any consumer can use the URL directly without extra logic.
    """
    if not base:
        return None
    # Already has an extension — return as-is.
    if "." in base.rsplit("/", 1)[-1]:
        return base
    return f"{base}.png"


def upsert_set(session: Session, set_data: dict[str, Any]) -> None:
    """Insert or update a set row."""
    session.execute(
        text("""
            INSERT INTO sets (id, name, series, printed_total, release_date, symbol_url, logo_url, created_at)
            VALUES (:id, :name, :series, :printed_total, :release_date, :symbol_url, :logo_url, NOW())
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                series = EXCLUDED.series,
                printed_total = EXCLUDED.printed_total,
                release_date = EXCLUDED.release_date,
                symbol_url = EXCLUDED.symbol_url,
                logo_url = EXCLUDED.logo_url
        """),
        {
            "id": set_data["id"],
            "name": set_data["name"],
            "series": set_data["serie"]["name"],
            "printed_total": set_data["cardCount"]["official"],
            "release_date": _parse_date(set_data.get("releaseDate")),
            "symbol_url": _asset_url(set_data.get("symbol")),
            "logo_url": _asset_url(set_data.get("logo")),
        },
    )


def upsert_card(session: Session, card_data: dict[str, Any]) -> None:
    """Insert or update a card row."""
    image_base = card_data.get("image")
    image_url = f"{image_base}/low.png" if image_base else None

    session.execute(
        text("""
            INSERT INTO cards (id, set_id, name, number, rarity, supertype, image_url, created_at)
            VALUES (:id, :set_id, :name, :number, :rarity, :supertype, :image_url, NOW())
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                number = EXCLUDED.number,
                rarity = EXCLUDED.rarity,
                supertype = EXCLUDED.supertype,
                image_url = EXCLUDED.image_url
        """),
        {
            "id": card_data["id"],
            "set_id": card_data["set"]["id"],
            "name": card_data["name"],
            "number": card_data["localId"],
            "rarity": card_data.get("rarity"),
            "supertype": card_data.get("category"),
            "image_url": image_url,
        },
    )


def load_set(set_data: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """
    Write a full set (metadata + all cards) to the database.

    The entire operation runs in a single transaction so a partial failure
    leaves the database unchanged.
    """
    with Session(engine) as session:
        with session.begin():
            print(f"  Upserting set: {set_data['id']} ({set_data['name']})")
            upsert_set(session, set_data)

            for card in cards:
                upsert_card(session, card)

            print(f"  Upserted {len(cards)} cards.")
