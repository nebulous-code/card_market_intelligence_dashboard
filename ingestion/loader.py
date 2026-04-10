"""
Transforms TCGdex API responses and writes them to the database.

Idempotency rules:
- Sets and cards are upserted (insert or update on conflict).

Price ingestion is not included in Milestone 1. It will be added in
Milestone 2 via the eBay completed sales API.
"""

import logging
import os
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# ANSI color codes for console output.
_COLORS = {
    "DEBUG": "\033[36m",    # cyan
    "INFO": "\033[32m",     # green
    "WARNING": "\033[33m",  # yellow
    "ERROR": "\033[31m",    # red
    "CRITICAL": "\033[35m", # magenta
    "RESET": "\033[0m",
}


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, _COLORS["RESET"])
        reset = _COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


_file_handler = logging.FileHandler("ingestion.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_ColorFormatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(level=logging.DEBUG, handlers=[_file_handler, _console_handler])
log = logging.getLogger(__name__)


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
    params = {
        "id": set_data["id"],
        "name": set_data["name"],
        "series": set_data["serie"]["name"],
        "printed_total": set_data["cardCount"]["official"],
        "release_date": _parse_date(set_data.get("releaseDate")),
        "symbol_url": _asset_url(set_data.get("symbol")),
        "logo_url": _asset_url(set_data.get("logo")),
    }
    log.debug("upsert_set params: %s", params)
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
        params,
    )
    log.debug("upsert_set executed OK for set_id=%s", params["id"])


def upsert_card(session: Session, card_data: dict[str, Any]) -> None:
    """Insert or update a card row."""
    image_base = card_data.get("image")
    image_url = f"{image_base}/low.png" if image_base else None

    params = {
        "id": card_data["id"],
        "set_id": card_data["set"]["id"],
        "name": card_data["name"],
        "number": card_data["localId"],
        "rarity": card_data.get("rarity"),
        "supertype": card_data.get("category"),
        "image_url": image_url,
    }
    log.debug("upsert_card params: %s", params)
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
        params,
    )
    log.debug("upsert_card executed OK for card_id=%s", params["id"])


def load_set(set_data: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """
    Write a full set (metadata + all cards) to the database.

    The entire operation runs in a single transaction so a partial failure
    leaves the database unchanged.
    """
    log.info("Beginning database transaction for set %s (%s)", set_data["id"], set_data["name"])
    try:
        with Session(engine) as session:
            with session.begin():
                log.info("Upserting set: %s (%s)", set_data["id"], set_data["name"])
                upsert_set(session, set_data)
                log.info("Set upsert complete")

                for card in cards:
                    upsert_card(session, card)

                log.info("Transaction committing — %d cards upserted", len(cards))
        log.info("Transaction committed successfully")
    except Exception as e:
        log.exception("Transaction failed and was rolled back: %s", e)
        raise
