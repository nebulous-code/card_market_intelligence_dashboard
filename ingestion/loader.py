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


def _load_rarity_aliases(session: Session) -> dict[str, str]:
    """Load rarity_aliases as a {raw_value: canonical_value} dict."""
    rows = session.execute(
        text("SELECT raw_value, canonical_value FROM rarity_aliases")
    ).fetchall()
    return {r.raw_value: r.canonical_value for r in rows}


def upsert_card(
    session: Session,
    card_data: dict[str, Any],
    rarity_aliases: dict[str, str] | None = None,
    unknowns: dict[tuple[str, str], int] | None = None,
) -> None:
    """
    Insert a new card row or update it if one already exists.

    Uses the same upsert pattern as upsert_set. The card image URL is
    constructed by appending "/low.png" to the base image URL from TCGdex.
    The "low" quality is used to keep image file sizes reasonable for a
    dashboard view. High quality images can be fetched if needed later.

    Args:
        session: The active database session to execute the query on.
        card_data: The full card object returned by the TCGdex API.
        rarity_aliases: Mapping of raw TCGdex rarity strings to canonical
            values from rarity_aliases. Required since migration 009 added
            an FK on cards.rarity. Pass {} to skip alias normalization
            (only valid when there is genuinely no alias table yet).
        unknowns: Optional accumulator for unrecognized rarity strings.
            Maps (field, raw_value) -> count. Surfaced in the run summary.

    Returns:
        None
    """
    # Build the image URL by appending "/low.png" to the base image path.
    # TCGdex provides the base URL without an extension or quality suffix.
    image_base = card_data.get("image")
    image_url = f"{image_base}/low.png" if image_base else None

    raw_rarity = card_data.get("rarity")
    if raw_rarity is None:
        canonical_rarity = None
    elif rarity_aliases is None or raw_rarity in (rarity_aliases or {}):
        canonical_rarity = (rarity_aliases or {}).get(raw_rarity, raw_rarity)
    else:
        # Unknown raw rarity. Insert NULL rather than blow up the FK; the
        # run summary surfaces the unknown so an alias row can be added.
        log.warning(
            "Unknown rarity '%s' on card %s — inserting NULL. Add a "
            "rarity_aliases row to capture it.",
            raw_rarity, card_data.get("id"),
        )
        if unknowns is not None:
            key = ("rarity", raw_rarity)
            unknowns[key] = unknowns.get(key, 0) + 1
        canonical_rarity = None

    params = {
        "id": card_data["id"],
        "set_id": card_data["set"]["id"],   # the card's parent set ID
        "name": card_data["name"],
        "number": card_data["localId"],     # TCGdex uses "localId" for card number
        "rarity": canonical_rarity,
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


def load_set(set_data: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
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
        dict with keys:
            cards_upserted -- number of cards written
            unknowns       -- {(field, raw_value): count} for rarity strings
                              not in rarity_aliases. Empty on a clean run.

    Raises:
        Exception: Re-raises any exception that occurs during the transaction
            after logging it and rolling back all changes.
    """
    log.info("Beginning database transaction for set %s (%s)", set_data["id"], set_data["name"])

    unknowns: dict[tuple[str, str], int] = {}

    try:
        with Session(engine) as session:
            with session.begin():
                # Load the rarity alias map once per set ingest. Backs the
                # canonical-rewrite logic in upsert_card.
                rarity_aliases = _load_rarity_aliases(session)

                # Write the set row first because cards reference it via
                # foreign key -- the set must exist before cards can be inserted.
                log.info("Upserting set: %s (%s)", set_data["id"], set_data["name"])
                upsert_set(session, set_data)
                log.info("Set upsert complete")

                # Write each card row. All cards are in the same transaction
                # as the set, so they will all be committed or rolled back together.
                for card in cards:
                    upsert_card(session, card, rarity_aliases, unknowns)

                log.info("Transaction committing -- %d cards upserted", len(cards))

        # This line only runs if the transaction committed without errors.
        log.info("Transaction committed successfully")

    except Exception as e:
        # Log the full exception including the stack trace, then re-raise
        # so the calling script knows the ingestion failed.
        log.exception("Transaction failed and was rolled back: %s", e)
        raise

    return {"cards_upserted": len(cards), "unknowns": unknowns}


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
    # Tracks raw variant/condition strings PPT sent that aren't in the canonical
    # maps. Rows containing them are skipped by _build_snapshot_rows. Surfaced
    # in the run-level summary so new mappings can be added when needed.
    unknowns: dict[tuple[str, str], int] = {}

    stats: dict[str, Any] = {
        "ppt_total": len(ppt_cards),
        "matched": 0,
        "skipped": 0,
        "errors": 0,
        "skipped_cards": [],  # list of (card_id_or_number, name, reason)
        "unknowns": unknowns,  # {(field, raw_value): count}
    }

    try:
        with Session(engine) as session:
            with session.begin():
                # Load the canonical alias maps once per set ingest. These
                # back the strict-mode normalize helpers in _build_snapshot_rows
                # -- raw PPT strings missing from the alias tables produce a
                # skipped row and an entry in `unknowns`.
                aliases = _load_aliases(session)

                # Build a mapping of card number -> (card_id, card_name).
                # Also keep a sorted list of all known numbers for nearby-number hints.
                #
                # The lookup key is the unpadded card number (leading zeros
                # stripped). TCGdex stores localId as zero-padded for some
                # modern sets (e.g. sv03.5 "001") and unpadded for older ones
                # ("1"), while PPT always returns zero-padded. Normalizing both
                # sides to the same form keeps the loader agnostic to whatever
                # convention TCGdex used for a given set.
                rows_db = session.execute(
                    text("SELECT id, number, name FROM cards WHERE set_id = :set_id"),
                    {"set_id": set_id},
                ).fetchall()
                number_to_info: dict[str, tuple[str, str]] = {
                    (row.number.lstrip("0") or "0"): (row.id, row.name)
                    for row in rows_db
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

                    if not card_number:  # pragma: no cover -- unreachable: lstrip("0") or "0" never returns falsy
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
                        snapshot_rows = _build_snapshot_rows(card_id, card, aliases, unknowns)
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

                    _bulk_insert_snapshots(session, snapshot_rows)

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


def _bulk_insert_snapshots(session: Session, rows: list[dict[str, Any]]) -> None:
    """
    Insert all snapshot rows for one card with a single multi-row INSERT.

    Each `session.execute()` is a round-trip to the database, and the cards
    in PPT's API tier produce ~900 rows per card (178 history points × several
    variants and conditions). Sending those one row at a time over a WAN link
    to a cloud Postgres makes the transaction take long enough to time out
    before any data is committed. Batching collapses each card to a single
    network call.

    Postgres caps bind parameters at 65535 per statement. With 7 params per
    row, that's ~9300 rows per statement -- comfortably above realistic
    per-card row counts -- but we chunk anyway as a safety net.
    """
    if not rows:
        return

    PARAMS_PER_ROW = 7
    MAX_ROWS_PER_STMT = 60000 // PARAMS_PER_ROW  # ~8500

    for chunk_start in range(0, len(rows), MAX_ROWS_PER_STMT):
        chunk = rows[chunk_start:chunk_start + MAX_ROWS_PER_STMT]
        placeholders = []
        params: dict[str, Any] = {}
        for i, r in enumerate(chunk):
            placeholders.append(
                f"(:card_id_{i}, :source_{i}, :condition_{i}, :variant_{i}, "
                f":market_price_{i}, :low_price_{i}, :high_price_{i}, "
                f"NOW(), COALESCE(CAST(:captured_date_{i} AS date), CURRENT_DATE))"
            )
            params[f"card_id_{i}"]       = r["card_id"]
            params[f"source_{i}"]        = r["source"]
            params[f"condition_{i}"]     = r["condition"]
            params[f"variant_{i}"]       = r.get("variant")
            params[f"market_price_{i}"]  = r["market_price"]
            params[f"low_price_{i}"]     = r.get("low_price")
            params[f"high_price_{i}"]    = r.get("high_price")
            params[f"captured_date_{i}"] = r.get("captured_date")

        session.execute(
            text(f"""
                INSERT INTO price_snapshots
                    (card_id, source, condition, variant, market_price, low_price, high_price,
                     captured_at, captured_date)
                VALUES {", ".join(placeholders)}
                ON CONFLICT (card_id, source, condition, variant, captured_date) DO UPDATE SET
                    market_price = EXCLUDED.market_price,
                    low_price    = EXCLUDED.low_price,
                    high_price   = EXCLUDED.high_price,
                    captured_at  = EXCLUDED.captured_at
            """),
            params,
        )


# Sentinel returned by the normalizers when the raw PPT value isn't in the
# alias tables. The row builder uses identity comparison (`is _UNKNOWN`) to
# decide whether to skip the row, so this works even though variants can
# legitimately be None.
_UNKNOWN = object()


def _load_aliases(session: Session) -> dict[str, dict[str, str | None]]:
    """
    Load condition_aliases and variant_aliases into in-memory dicts.

    Called once per ingestion run before processing any cards. The two
    nested dicts power the normalize helpers in `_build_snapshot_rows`.

    Returns:
        {
            "condition": {"Near Mint": "NM", "psa10": "PSA-10", ...},
            "variant":   {"Holofoil": "holofoil", "Normal": None, ...},
        }
    """
    cond_rows = session.execute(
        text("SELECT raw_value, canonical_value FROM condition_aliases")
    ).fetchall()
    variant_rows = session.execute(
        text("SELECT raw_value, canonical_value FROM variant_aliases")
    ).fetchall()
    return {
        "condition": {r.raw_value: r.canonical_value for r in cond_rows},
        "variant":   {r.raw_value: r.canonical_value for r in variant_rows},
    }


def _build_snapshot_rows(
    card_id: str,
    card: dict[str, Any],
    aliases: dict[str, dict[str, str | None]],
    unknowns: dict[tuple[str, str], int] | None = None,
) -> list[dict[str, Any]]:
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
        unknowns: Optional accumulator for non-canonical (variant/condition)
            strings encountered. Maps (field, raw_value) -> count. Surfaced in
            the run summary so new mappings can be added when needed.

    Returns:
        list[dict]: One dict per row, ready to pass as SQL parameters.
    """
    rows: list[dict[str, Any]] = []
    if unknowns is None:
        unknowns = {}

    cond_aliases = aliases["condition"]
    variant_aliases = aliases["variant"]

    def _normalize_condition(raw: str):
        # Variant strings (e.g. " 1st Edition Holofoil") that PPT bleeds into
        # the condition string are pre-seeded as condition_aliases rows by
        # migration 008 -- so a single dict lookup covers both plain and
        # suffixed forms. New spellings show up as unknowns to be added later.
        if raw in cond_aliases:
            return cond_aliases[raw]
        unknowns[("condition", raw)] = unknowns.get(("condition", raw), 0) + 1
        return _UNKNOWN

    def _normalize_variant(raw: str):
        if raw in variant_aliases:
            return variant_aliases[raw]
        unknowns[("variant", raw)] = unknowns.get(("variant", raw), 0) + 1
        return _UNKNOWN

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
        if variant is _UNKNOWN:
            continue  # Skip every row in this variant bucket.

        for condition_raw, cond_data in conditions.items():
            if not isinstance(cond_data, dict):
                continue
            condition = _normalize_condition(condition_raw)
            if condition is _UNKNOWN:
                continue  # Skip history + latestPrice rows for this condition.

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
                if variant is _UNKNOWN:
                    continue
                for condition_raw, cond_data in conditions.items():
                    if not isinstance(cond_data, dict):
                        continue
                    price = cond_data.get("price")
                    if price is None:
                        continue
                    condition = _normalize_condition(condition_raw)
                    if condition is _UNKNOWN:
                        continue
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
    # is {"avg": float}. The raw API key is normalized through the same
    # condition_aliases lookup the rest of the loader uses, keeping the
    # canonical/display pipeline uniform across all condition sources.
    # The grading company is encoded in the key prefix and stored as `source`.
    ebay = card.get("ebay", {})
    for api_key, grade_data in ebay.items():
        if not isinstance(grade_data, dict):
            continue
        avg = grade_data.get("avg")
        if avg is None:
            continue
        condition = _normalize_condition(api_key)
        if condition is _UNKNOWN:
            continue
        # Source = "psa" / "bgs" / "cgc" derived from the api_key prefix.
        # Falls back to "ebay" when the prefix isn't a known grader so a
        # surprise key still produces a usable row once an alias is added.
        if api_key.startswith("psa"):
            source = "psa"
        elif api_key.startswith("bgs"):
            source = "bgs"
        elif api_key.startswith("cgc"):
            source = "cgc"
        else:
            source = "ebay"
        rows.append({
            "card_id":      card_id,
            "source":       source,
            "condition":    condition,
            "variant":      None,
            "market_price": avg,
            "low_price":    None,
            "high_price":   None,
            "captured_date": None,
        })

    return rows
