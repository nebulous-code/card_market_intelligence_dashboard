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


log = logging.getLogger(__name__)


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


def insert_price_snapshots(ppt_cards: list[dict[str, Any]], set_id: str) -> dict[str, Any]:
    """
    Insert price snapshots for a batch of cards from PokemonPriceTracker.

    Price snapshots use ON CONFLICT DO UPDATE so re-running on the same day
    updates the existing row rather than inserting a duplicate.

    PokemonPriceTracker uses numeric TCGPlayer IDs which do not match the
    TCGdex IDs stored in our cards table. Cards are matched by card number
    within the set -- PPT's cardNumber field corresponds to our cards.number
    column after stripping zero-padding and the "/total" suffix.

    Args:
        ppt_cards: The list of card objects from the PokemonPriceTracker API.
        set_id: The TCGdex set ID (e.g. "base1") used to scope card lookups.

    Returns:
        dict with keys:
            ppt_total  -- number of PPT cards processed
            matched    -- cards successfully matched and inserted
            skipped    -- cards skipped (no match or no price data)
            errors     -- cards that raised an unexpected exception
            skipped_cards -- list of (card_id_or_number, name, reason) tuples

    Raises:
        Exception: Re-raises any exception from the database transaction.
    """
    stats: dict[str, Any] = {
        "ppt_total": len(ppt_cards),
        "matched": 0,
        "skipped": 0,
        "errors": 0,
        "skipped_cards": [],  # list of (card_id_or_number, name, reason)
    }

    try:
        with Session(engine) as session:
            with session.begin():
                # Build a mapping of card number -> (card_id, card_name).
                # Also keep a sorted list of all known numbers for nearby-number hints.
                rows_db = session.execute(
                    text("SELECT id, number, name FROM cards WHERE set_id = :set_id"),
                    {"set_id": set_id},
                ).fetchall()
                number_to_info: dict[str, tuple[str, str]] = {
                    row.number: (row.id, row.name) for row in rows_db
                }
                # Pre-sort numeric keys for nearby-number lookup on misses.
                all_numbers_sorted = sorted(
                    (n for n in number_to_info if n.isdigit()),
                    key=int,
                )
                log.debug("Loaded %d card number mappings for set %s", len(number_to_info), set_id)

                for card in ppt_cards:
                    card_name = card.get("name", "?")
                    raw = str(card.get("cardNumber", "")).strip().split("/")[0]
                    card_number = raw.lstrip("0") or "0"

                    if not card_number:
                        log.warning("[%s] SKIPPED (no number): '%s' has no cardNumber", set_id, card_name)
                        stats["skipped"] += 1
                        stats["skipped_cards"].append((raw or "?", card_name, "no cardNumber"))
                        continue

                    info = number_to_info.get(card_number)
                    if not info:
                        nearby = _nearby_numbers(card_number, all_numbers_sorted, number_to_info)
                        nearby_str = ", ".join(f"{n} ({number_to_info[n][1]})" for n in nearby)
                        log.warning(
                            "[%s] SKIPPED (no match): '%s' PPT#%s — searched for '%s', "
                            "not found in cards table.\n  Cards with nearby numbers: %s",
                            set_id, card_name, raw, card_number,
                            nearby_str or "none",
                        )
                        stats["skipped"] += 1
                        stats["skipped_cards"].append((card_number, card_name, "no match"))
                        continue

                    card_id, db_name = info

                    try:
                        snapshot_rows = _build_snapshot_rows(card_id, card)
                    except Exception as exc:
                        log.error("[%s] ERROR matching '%s' PPT#%s: %s", set_id, card_name, raw, exc)
                        stats["errors"] += 1
                        continue

                    if not snapshot_rows:
                        log.warning(
                            "[%s] SKIPPED (no price): '%s' PPT#%s matched %s but PPT returned no price data",
                            set_id, card_name, raw, card_id,
                        )
                        stats["skipped"] += 1
                        stats["skipped_cards"].append((card_id, card_name, "no price data"))
                        continue

                    for row in snapshot_rows:
                        session.execute(
                            text("""
                                INSERT INTO price_snapshots
                                    (card_id, source, condition, variant, market_price, low_price, high_price,
                                     captured_at, captured_date)
                                VALUES
                                    (:card_id, :source, :condition, :variant, :market_price, :low_price, :high_price,
                                     NOW(), COALESCE(CAST(:captured_date AS date), CURRENT_DATE))
                                ON CONFLICT (card_id, source, condition, variant, captured_date) DO UPDATE SET
                                    market_price = EXCLUDED.market_price,
                                    low_price    = EXCLUDED.low_price,
                                    high_price   = EXCLUDED.high_price,
                                    captured_at  = EXCLUDED.captured_at
                            """),
                            row,
                        )

                    # Log a DEBUG summary for this card.
                    variants_in_rows = len({r.get("variant") for r in snapshot_rows})
                    conds_in_rows = len({r.get("condition") for r in snapshot_rows})
                    history_rows = sum(1 for r in snapshot_rows if r.get("captured_date") is not None)
                    log.debug(
                        "[%s] MATCHED: '%s' PPT#%s → %s | %d variant(s), %d condition(s), %d history points",
                        set_id, card_name, raw, card_id,
                        variants_in_rows, conds_in_rows, history_rows,
                    )
                    stats["matched"] += 1

        return stats

    except Exception as e:
        log.exception("Price snapshot insert failed and was rolled back: %s", e)
        raise


def _nearby_numbers(
    target: str,
    sorted_numbers: list[str],
    number_to_info: dict[str, tuple[str, str]],
    n: int = 3,
) -> list[str]:
    """
    Return up to n card numbers from sorted_numbers closest to target.

    Used to provide helpful context in skip warnings when a PPT card number
    does not match any card in our database.

    Args:
        target: The card number that was not found (e.g. "58").
        sorted_numbers: All known card numbers for the set, sorted numerically.
        number_to_info: Mapping of number -> (card_id, card_name).
        n: Maximum number of nearby numbers to return.

    Returns:
        list[str]: Up to n card numbers closest in value to target.
    """
    if not target.isdigit() or not sorted_numbers:
        return []
    target_int = int(target)
    # Sort all known numeric numbers by absolute distance from target.
    by_distance = sorted(sorted_numbers, key=lambda x: abs(int(x) - target_int))
    # Exclude the target itself (it wasn't found), return the n closest.
    return [x for x in by_distance if x != target][:n]


def _build_snapshot_rows(card_id: str, card: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Convert a single PokemonPriceTracker card object into snapshot row dicts.

    Produces one row for each available price data point:
      - Historical rows from priceHistory.variants (per-variant, per-condition)
      - Current-price rows from prices.variants for today's date
      - Falls back to prices.market scalar when neither structure is present
      - eBay/graded prices from ebay.* when present (API tier)

    The PPT API returns history under priceHistory.variants when
    includeHistory=true is sent. Structure (verified April 2026):

        priceHistory.variants = {
          "Holofoil": {
            "Near Mint": {
              "history": [{"date": "2025-10-17T...", "market": 62.32, "volume": 4}, ...],
              "dataPoints": 26,
              "latestPrice": 62.32
            },
            "Lightly Played": { ... },
            ...
          },
          "1st Edition Holofoil": { ... }
        }

    Args:
        card_id: The internal card ID in our database (matched by card number).
        card: The card object from the PokemonPriceTracker API response.

    Returns:
        list[dict]: One dict per row, ready to pass as SQL parameters.
    """
    rows: list[dict[str, Any]] = []

    # --- Condition and variant normalization maps ---

    CONDITION_MAP = {
        "Near Mint":         "NM",
        "Lightly Played":    "LP",
        "Moderately Played": "MP",
        "Heavily Played":    "HP",
        "Damaged":           "DMG",
    }

    # PPT variant strings → normalized DB values.
    # None means no variant distinction (standard/unlimited printing) — stored as NULL.
    VARIANT_MAP = {
        "Holofoil":             "holofoil",
        "1st Edition Holofoil": "1st_edition_holofoil",
        "Reverse Holofoil":     "reverse_holofoil",
        "Normal":               None,
        "1st Edition Normal":   "1st_edition_normal",
        # Older sets (Base Set, Jungle, Fossil, Base Set 2) use bare printing labels.
        "1st Edition":          "1st_edition",
        "Unlimited":            "unlimited",
    }

    # Suffixes PPT sometimes appends to the condition key when variant info
    # bleeds into the condition string (e.g. "Near Mint 1st Edition").
    # Listed longest-first so more-specific matches are tried before shorter ones.
    _CONDITION_SUFFIXES = [
        " 1st Edition Holofoil",
        " Reverse Holofoil",
        " 1st Edition Normal",
        " 1st Edition",
        " Holofoil",
        " Unlimited",
        " Normal",
    ]

    def _normalize_condition(raw: str) -> str:
        if raw in CONDITION_MAP:
            return CONDITION_MAP[raw]
        # PPT sometimes appends the variant name to the condition string
        # (e.g. "Near Mint 1st Edition"). Strip the suffix and retry.
        for suffix in _CONDITION_SUFFIXES:
            if raw.endswith(suffix):
                base = raw[: -len(suffix)]
                if base in CONDITION_MAP:
                    return CONDITION_MAP[base]
        log.warning("Unknown condition '%s' for card %s — storing as-is", raw, card_id)
        return raw

    def _normalize_variant(raw: str) -> str | None:
        if raw in VARIANT_MAP:
            return VARIANT_MAP[raw]
        normalized = raw.lower().replace(" ", "_")
        log.warning(
            "Unknown variant '%s' for card %s — storing as '%s'", raw, card_id, normalized
        )
        return normalized

    # --- Historical + current prices from priceHistory.variants ---
    #
    # priceHistory is only present when includeHistory=true was sent.
    # Each variant/condition bucket has a history array (one point per date)
    # and a latestPrice for today's value.

    price_history = card.get("priceHistory") or {}
    ph_variants = price_history.get("variants") or {}

    history_point_count = 0

    for variant_raw, conditions in ph_variants.items():
        if not isinstance(conditions, dict):
            continue
        variant = _normalize_variant(variant_raw)

        for condition_raw, cond_data in conditions.items():
            if not isinstance(cond_data, dict):
                continue
            condition = _normalize_condition(condition_raw)

            # Historical rows — one per date point in the history array.
            for point in cond_data.get("history") or []:
                if not isinstance(point, dict):
                    continue
                market = point.get("market")
                date_str = point.get("date", "")
                date_str = date_str[:10] if date_str else None
                if market is None or not date_str:
                    continue
                rows.append({
                    "card_id":       card_id,
                    "source":        "tcgplayer",
                    "condition":     condition,
                    "variant":       variant,
                    "market_price":  market,
                    "low_price":     None,
                    "high_price":    None,
                    "captured_date": date_str,
                })
                history_point_count += 1

            # Current price row from latestPrice — ensures today's price is
            # written even if the history array doesn't include today's date.
            latest = cond_data.get("latestPrice")
            if latest is not None:
                rows.append({
                    "card_id":       card_id,
                    "source":        "tcgplayer",
                    "condition":     condition,
                    "variant":       variant,
                    "market_price":  latest,
                    "low_price":     None,
                    "high_price":    None,
                    "captured_date": None,  # None → CURRENT_DATE in INSERT
                })

    if ph_variants:
        variant_count = len(ph_variants)
        cond_count = sum(
            len(v) for v in ph_variants.values() if isinstance(v, dict)
        )
        log.debug(
            "[%s] priceHistory: %d variant(s), %d condition(s), %d history points",
            card_id, variant_count, cond_count, history_point_count,
        )
    else:
        # priceHistory absent — fall back to current prices from prices.variants.
        if price_history:
            # priceHistory key exists but variants is empty/missing.
            log.warning(
                "Card %s: priceHistory present but variants is empty — current price only",
                card_id,
            )

        prices = card.get("prices") or {}
        pv = prices.get("variants")

        if isinstance(pv, dict) and pv:
            # per-printing / per-condition current prices.
            for variant_raw, conditions in pv.items():
                if not isinstance(conditions, dict):
                    continue
                variant = _normalize_variant(variant_raw)
                for condition_raw, cond_data in conditions.items():
                    if not isinstance(cond_data, dict):
                        continue
                    price = cond_data.get("price")
                    if price is None:
                        continue
                    condition = _normalize_condition(condition_raw)
                    rows.append({
                        "card_id":       card_id,
                        "source":        "tcgplayer",
                        "condition":     condition,
                        "variant":       variant,
                        "market_price":  price,
                        "low_price":     None,
                        "high_price":    None,
                        "captured_date": None,
                    })

        elif prices.get("market") is not None:
            # Bare scalar fallback — free-tier or stripped response.
            rows.append({
                "card_id":       card_id,
                "source":        "tcgplayer",
                "condition":     "NM",
                "variant":       None,
                "market_price":  prices["market"],
                "low_price":     prices.get("low"),
                "high_price":    prices.get("high"),
                "captured_date": None,
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
            "captured_date": None,  # None → use CURRENT_DATE in the INSERT
        })

    return rows
