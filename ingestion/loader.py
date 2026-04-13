"""
Database writer for the ingestion pipeline.

This module takes data fetched from the TCGdex API and writes it to
the PostgreSQL database. It handles the translation between the API's
response format and the database column names, and enforces the
idempotency rules that make the ingestion script safe to run repeatedly.

Idempotency rules:
  - Sets and cards are upserted. If a row already exists it is updated
    with the latest values from TCGdex. If it does not exist it is inserted.
  - Price snapshots are always appended as new rows and are never updated.
    This preserves the full price history. Price ingestion is not included
    in Milestone 1 -- it will be added in Milestone 2 via the eBay API.
"""

import logging
import os
from datetime import datetime
from typing import Any

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Load environment variables by walking up the directory tree to find .env.
# find_dotenv() searches from this file's location upward, so the script
# works regardless of which directory it is run from or invoked via Docker.
load_dotenv(find_dotenv())

# Read the database connection string and create the engine.
DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


# ---- Logging setup -------------------------------------------------------
# Log messages go to both the terminal and a file called ingestion.log in
# the ingestion/ directory. The file is useful for reviewing what happened
# after the fact, especially if the script was run unattended.

# ANSI color codes used to make log levels visually distinct in the terminal.
_COLORS = {
    "DEBUG": "\033[36m",     # cyan
    "INFO": "\033[32m",      # green
    "WARNING": "\033[33m",   # yellow
    "ERROR": "\033[31m",     # red
    "CRITICAL": "\033[35m",  # magenta
    "RESET": "\033[0m",
}


class _ColorFormatter(logging.Formatter):
    """Custom log formatter that adds color codes to the level name in console output."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record with color applied to the level name.

        Args:
            record: The log record to format.

        Returns:
            str: The formatted log message with ANSI color codes applied.
        """
        color = _COLORS.get(record.levelname, _COLORS["RESET"])
        reset = _COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


# File handler writes plain text without color codes (color codes in a file
# would appear as garbage characters when reading the file).
_file_handler = logging.FileHandler("ingestion.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

# Console handler uses the color formatter for readability in the terminal.
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_ColorFormatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(level=logging.DEBUG, handlers=[_file_handler, _console_handler])
log = logging.getLogger(__name__)

# ---- End logging setup ---------------------------------------------------


def _parse_date(value: str | None):
    """
    Parse a TCGdex date string into a Python date object.

    TCGdex provides release dates in YYYY-MM-DD format. This function
    converts that string to a Python date object that SQLAlchemy can
    store in a DATE column. Returns None if the value is missing or
    cannot be parsed, since not all sets have a known release date.

    Args:
        value: A date string in YYYY-MM-DD format, or None.

    Returns:
        datetime.date: The parsed date, or None if parsing failed.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _asset_url(base: str | None) -> str | None:
    """
    Resolve a TCGdex asset base URL to a usable image URL.

    TCGdex returns bare base URLs for set logos and symbols -- they do not
    include a file extension. For example:
        https://assets.tcgdex.net/en/base/base1/logo

    This function appends ".png" so the URL can be used directly in an
    <img> tag without the frontend or any other consumer needing to know
    about TCGdex's URL format.

    If the URL already ends with a file extension it is returned unchanged,
    which makes this function safe to call more than once on the same value.

    Args:
        base: The asset base URL from TCGdex, or None.

    Returns:
        str: The resolved image URL with .png appended if needed, or None
            if the input was None.
    """
    if not base:
        return None

    # Check whether the last path segment already contains a dot, which
    # would indicate a file extension is already present.
    if "." in base.rsplit("/", 1)[-1]:
        return base

    # No extension found -- append .png.
    return f"{base}.png"


def upsert_set(session: Session, set_data: dict[str, Any]) -> None:
    """
    Insert a new set row or update it if one already exists.

    Uses PostgreSQL's ON CONFLICT DO UPDATE syntax (also known as an
    upsert) so the script can be run multiple times without creating
    duplicate rows. If the set already exists, all fields are refreshed
    with the latest values from TCGdex.

    Args:
        session: The active database session to execute the query on.
        set_data: The set object returned by the TCGdex API.

    Returns:
        None
    """
    # Build the parameter dictionary that maps database columns to values
    # from the TCGdex response. Log it at DEBUG level for diagnostics.
    params = {
        "id": set_data["id"],
        "name": set_data["name"],
        "series": set_data["serie"]["name"],        # nested under "serie"
        "printed_total": set_data["cardCount"]["official"],  # nested under "cardCount"
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
                -- created_at is intentionally omitted: we never overwrite the
                -- original insertion timestamp when re-ingesting the same set.
        """),
        params,
    )
    log.debug("upsert_set executed OK for set_id=%s", params["id"])


def upsert_card(session: Session, card_data: dict[str, Any]) -> None:
    """
    Insert a new card row or update it if one already exists.

    Uses the same upsert pattern as upsert_set. The card image URL is
    constructed by appending "/low.png" to the base image URL from TCGdex.
    The "low" quality is used to keep image file sizes reasonable for a
    dashboard view. High quality images can be fetched if needed later.

    Args:
        session: The active database session to execute the query on.
        card_data: The full card object returned by the TCGdex API.

    Returns:
        None
    """
    # Build the image URL by appending "/low.png" to the base image path.
    # TCGdex provides the base URL without an extension or quality suffix.
    image_base = card_data.get("image")
    image_url = f"{image_base}/low.png" if image_base else None

    params = {
        "id": card_data["id"],
        "set_id": card_data["set"]["id"],   # the card's parent set ID
        "name": card_data["name"],
        "number": card_data["localId"],     # TCGdex uses "localId" for card number
        "rarity": card_data.get("rarity"),
        "supertype": card_data.get("category"),  # TCGdex uses "category" for supertype
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
                -- created_at is intentionally omitted: we never overwrite the
                -- original insertion timestamp when re-ingesting the same card.
        """),
        params,
    )
    log.debug("upsert_card executed OK for card_id=%s", params["id"])


def load_set(set_data: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """
    Write a complete set and all its cards to the database in one transaction.

    The set upsert and all card upserts are wrapped in a single database
    transaction. This means either everything is saved together or nothing
    is -- if an error occurs partway through, the database is left exactly
    as it was before the function was called. There will never be a partial
    import with some cards missing.

    Args:
        set_data: The set object returned by tcgdex.get_set().
        cards: The list of full card objects returned by tcgdex.get_cards().

    Returns:
        None

    Raises:
        Exception: Re-raises any exception that occurs during the transaction
            after logging it and rolling back all changes.
    """
    log.info("Beginning database transaction for set %s (%s)", set_data["id"], set_data["name"])

    try:
        with Session(engine) as session:
            with session.begin():
                # Write the set row first because cards reference it via
                # foreign key -- the set must exist before cards can be inserted.
                log.info("Upserting set: %s (%s)", set_data["id"], set_data["name"])
                upsert_set(session, set_data)
                log.info("Set upsert complete")

                # Write each card row. All cards are in the same transaction
                # as the set, so they will all be committed or rolled back together.
                for card in cards:
                    upsert_card(session, card)

                log.info("Transaction committing -- %d cards upserted", len(cards))

        # This line only runs if the transaction committed without errors.
        log.info("Transaction committed successfully")

    except Exception as e:
        # Log the full exception including the stack trace, then re-raise
        # so the calling script knows the ingestion failed.
        log.exception("Transaction failed and was rolled back: %s", e)
        raise


def insert_price_snapshots(ppt_cards: list[dict[str, Any]], set_id: str) -> int:
    """
    Insert price snapshots for a batch of cards from PokemonPriceTracker.

    Price snapshots are always appended as new rows -- existing rows are
    never updated. This preserves the full price history so that trends can
    be charted over time.

    PokemonPriceTracker uses numeric TCGPlayer IDs (e.g. 42350) which do not
    match the TCGdex IDs stored in our cards table (e.g. "base1-4"). Cards are
    matched to our database by card number within the set -- PPT's cardNumber
    field (e.g. "4") corresponds to our cards.number column.

    Cards whose card number cannot be found in our database are skipped with
    a warning. This can happen if the PPT set contains promo or variant cards
    that were not ingested via TCGdex.

    Args:
        ppt_cards: The list of card objects from the PokemonPriceTracker
            API response (the "data" array).
        set_id: The TCGdex set ID (e.g. "base1") used to scope the card
            number lookup to the correct set.

    Returns:
        int: The total number of snapshot rows inserted.

    Raises:
        Exception: Re-raises any exception after logging and rolling back.
    """
    total_inserted = 0

    try:
        with Session(engine) as session:
            with session.begin():
                # Build a mapping of card number -> our card ID for this set.
                # PPT uses its own numeric IDs; we resolve to our TCGdex IDs
                # by matching on card number within the set.
                rows_db = session.execute(
                    text("SELECT id, number FROM cards WHERE set_id = :set_id"),
                    {"set_id": set_id},
                ).fetchall()
                number_to_id = {row.number: row.id for row in rows_db}
                log.debug("Loaded %d card number mappings for set %s", len(number_to_id), set_id)

                for card in ppt_cards:
                    # PPT returns card numbers as "001/102" (zero-padded, with total).
                    # Our database stores only the plain number (e.g. "1").
                    raw = str(card.get("cardNumber", "")).strip().split("/")[0]
                    card_number = raw.lstrip("0") or "0"
                    if not card_number:
                        log.warning("Skipping PPT card with no cardNumber: %s", card.get("name"))
                        continue

                    card_id = number_to_id.get(card_number)
                    if not card_id:
                        log.warning(
                            "Skipping PPT card '%s' (number=%s) -- not found in cards table for set %s",
                            card.get("name"), card_number, set_id,
                        )
                        continue

                    snapshot_rows = _build_snapshot_rows(card_id, card)
                    for row in snapshot_rows:
                        session.execute(
                            text("""
                                INSERT INTO price_snapshots
                                    (card_id, source, condition, market_price, low_price, high_price, captured_at)
                                VALUES
                                    (:card_id, :source, :condition, :market_price, :low_price, :high_price, NOW())
                            """),
                            row,
                        )
                    total_inserted += len(snapshot_rows)

        log.info("Inserted %d price snapshot rows", total_inserted)
        return total_inserted

    except Exception as e:
        log.exception("Price snapshot insert failed and was rolled back: %s", e)
        raise


def _build_snapshot_rows(card_id: str, card: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Convert a single PokemonPriceTracker card object into snapshot row dicts.

    Produces one row for each available price data point:
      - Current TCGPlayer prices (prices.market / low / high) keyed by condition
      - Historical TCGPlayer prices from priceHistory (market only, no low/high)
      - eBay/graded prices from ebay.* when present (API tier)

    Args:
        card_id: The tcgPlayerId value for this card.
        card: The card object from the PokemonPriceTracker API response.

    Returns:
        list[dict]: One dict per row, ready to pass as SQL parameters.
    """
    rows: list[dict[str, Any]] = []

    # --- Current TCGPlayer prices ---
    # The API returns a flat prices dict with keys like "market", "low", "mid",
    # "high". We store the current snapshot as condition="NM" (the standard
    # ungraded near-mint condition) using source="tcgplayer".
    prices = card.get("prices")
    if prices:
        rows.append({
            "card_id": card_id,
            "source": "tcgplayer",
            "condition": "NM",
            "market_price": prices.get("market"),
            "low_price": prices.get("low"),
            "high_price": prices.get("high"),
        })

    # --- Historical TCGPlayer prices ---
    # priceHistory is a list of {"date": "YYYY-MM-DD", "market": float} objects.
    # Each historical point is stored as a separate row with market_price only
    # (low/high are not available in history). We keep them under source="tcgplayer"
    # so they appear in the same chart series as current prices.
    for point in card.get("priceHistory", []):
        market = point.get("market")
        if market is None:
            continue
        rows.append({
            "card_id": card_id,
            "source": "tcgplayer",
            "condition": "NM",
            "market_price": market,
            "low_price": None,
            "high_price": None,
        })

    # --- eBay / graded prices (API tier only) ---
    # ebay is a dict with keys like "psa10", "psa9", "bgs95" etc. Each value
    # is {"avg": float}. We store each grade as a separate row with the grade
    # as the condition and the grading company as the source.
    ebay = card.get("ebay", {})
    grade_map = {
        # key in API response -> (source, condition label)
        "psa10": ("psa", "PSA-10"),
        "psa9": ("psa", "PSA-9"),
        "psa8": ("psa", "PSA-8"),
        "bgs10": ("bgs", "BGS-10"),
        "bgs95": ("bgs", "BGS-9.5"),
        "bgs9": ("bgs", "BGS-9"),
        "cgc10": ("cgc", "CGC-10"),
        "cgc95": ("cgc", "CGC-9.5"),
        "cgc9": ("cgc", "CGC-9"),
    }
    for api_key, (source, condition_label) in grade_map.items():
        grade_data = ebay.get(api_key)
        if not grade_data:
            continue
        avg = grade_data.get("avg")
        if avg is None:
            continue
        rows.append({
            "card_id": card_id,
            "source": source,
            "condition": condition_label,
            "market_price": avg,
            "low_price": None,
            "high_price": None,
        })

    return rows
