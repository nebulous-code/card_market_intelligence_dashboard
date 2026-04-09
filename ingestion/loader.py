"""
Transforms pokemontcg.io API responses and writes them to the database.

Idempotency rules:
- Sets and cards are upserted (insert or update on conflict).
- Price snapshots are always appended — never updated in place.
"""

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Conditions mapped from the tcgplayer prices object.
PRICE_CONDITIONS = ("normal", "holofoil", "reverseHolofoil")


def _parse_date(value: str | None):
    """Parse a pokemontcg.io date string (YYYY/MM/DD) to a Python date, or None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y/%m/%d").date()
    except ValueError:
        return None


def upsert_set(session: Session, set_data: dict[str, Any]) -> None:
    """Insert or update a set row."""
    images = set_data.get("images", {})
    stmt = pg_insert(text.__class__).values()  # placeholder — see raw SQL below

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
            "series": set_data["series"],
            "printed_total": set_data.get("printedTotal", 0),
            "release_date": _parse_date(set_data.get("releaseDate")),
            "symbol_url": images.get("symbol"),
            "logo_url": images.get("logo"),
        },
    )


def upsert_card(session: Session, card_data: dict[str, Any]) -> None:
    """Insert or update a card row."""
    images = card_data.get("images", {})

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
            "number": card_data["number"],
            "rarity": card_data.get("rarity"),
            "supertype": card_data.get("supertype"),
            "image_url": images.get("small"),
        },
    )


def insert_price_snapshots(session: Session, card_data: dict[str, Any]) -> int:
    """
    Append a price snapshot row for each available condition on this card.

    Returns the number of snapshots inserted.
    """
    tcgplayer = card_data.get("tcgplayer", {})
    prices = tcgplayer.get("prices", {})
    captured_at = datetime.now(timezone.utc)
    inserted = 0

    for condition in PRICE_CONDITIONS:
        price_data = prices.get(condition)
        if price_data is None:
            continue  # This condition is not available for this card — skip silently.

        session.execute(
            text("""
                INSERT INTO price_snapshots
                    (card_id, source, condition, market_price, low_price, high_price, captured_at)
                VALUES
                    (:card_id, :source, :condition, :market_price, :low_price, :high_price, :captured_at)
            """),
            {
                "card_id": card_data["id"],
                "source": "tcgplayer",
                "condition": condition,
                "market_price": price_data.get("market"),
                "low_price": price_data.get("low"),
                "high_price": price_data.get("high"),
                "captured_at": captured_at,
            },
        )
        inserted += 1

    return inserted


def load_set(set_data: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """
    Write a full set (metadata + all cards + price snapshots) to the database.

    The entire operation runs in a single transaction so a partial failure
    leaves the database unchanged.
    """
    with Session(engine) as session:
        with session.begin():
            print(f"  Upserting set: {set_data['id']} ({set_data['name']})")
            upsert_set(session, set_data)

            snapshot_count = 0
            for card in cards:
                upsert_card(session, card)
                snapshot_count += insert_price_snapshots(session, card)

            print(f"  Upserted {len(cards)} cards, inserted {snapshot_count} price snapshots.")
