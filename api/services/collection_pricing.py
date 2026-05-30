"""
Pricing helpers for the Collection Dashboard.

The session stores ``ParsedCollectionRow`` objects. The dashboard wants
three derived views on top of that:

1. **Current cards-with-prices** -- one row per session line item joined
   to the latest market price + card metadata. Drives KPIs / pie /
   treemap / Top 10 / Sets Ranked.

2. **Daily timeseries** -- total ``quantity * price`` per day over the
   chosen window. Uses **LOCF** (Last Observation Carried Forward): on
   any day a card has no snapshot, use the most recent prior snapshot;
   if no prior snapshot exists, use the earliest snapshot ever recorded
   for that card.

3. **Gainers/losers** -- per-card start-of-window vs current price,
   filtered by a minimum absolute percentage threshold.

The variant matching from the session's free-form variant strings to
``price_snapshots.variant`` (which uses source-specific labels like
``"holofoil"``) is unresolved -- so all queries here ignore variant for
the price lookup and use latest snapshot per ``(card_id, condition)``,
preferring the row with ``variant IS NULL`` when ties exist.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from schemas.collection import (
    CollectionCardWithPrice,
    CollectionMover,
    ParsedCollectionRow,
    TimeseriesPoint,
)


WINDOW_DAYS: dict[str, int | None] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "6m": 183,
    "all": None,
}


def cards_with_prices(
    db: Session, rows: list[ParsedCollectionRow]
) -> list[CollectionCardWithPrice]:
    """Join each session row to its latest market price + card metadata.

    Returns one entry per session row in the same order. Cards with no
    snapshot data have ``market_price=None`` so the frontend can either
    show a placeholder or exclude them from value calculations.
    """
    if not rows:
        return []

    card_ids = sorted({r.card_id for r in rows})
    cards = _fetch_card_metadata(db, card_ids)
    latest_prices = _fetch_latest_prices(db, card_ids)

    out: list[CollectionCardWithPrice] = []
    for row in rows:
        meta = cards.get(row.card_id)
        if meta is None:  # pragma: no cover -- session rows reference live cards
            continue
        market_price = latest_prices.get((row.card_id, row.condition))
        out.append(
            CollectionCardWithPrice(
                card_id=row.card_id,
                card_name=meta["name"],
                image_url=meta["image_url"],
                rarity=meta["rarity"],
                supertype=meta["supertype"],
                set_id=meta["set_id"],
                set_name=meta["set_name"],
                printed_total=meta["printed_total"],
                total_count=meta["total_count"],
                condition=row.condition,
                variant=list(row.variant),
                is_first_edition=row.is_first_edition,
                quantity=row.quantity,
                market_price=market_price,
                purchase_price=row.purchase_price,
            )
        )
    return out


def daily_timeseries(
    db: Session, rows: list[ParsedCollectionRow], window: str
) -> tuple[list[TimeseriesPoint], date | None]:
    """Return ``(points, earliest_snapshot_anywhere)`` for the chart."""
    if not rows:
        return [], None

    earliest = _earliest_snapshot(db, list({r.card_id for r in rows}))
    today = date.today()
    days = WINDOW_DAYS[window]
    if days is None:
        if earliest is None:
            return [], None
        start = earliest
    else:
        start = today - timedelta(days=days - 1)
        if earliest is not None and start < earliest:
            start = earliest

    if earliest is None:
        return [], None

    history = _fetch_history(
        db,
        card_conditions=[(r.card_id, r.condition) for r in rows],
    )
    quantities: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        quantities[(r.card_id, r.condition)] += r.quantity

    points: list[TimeseriesPoint] = []
    current = start
    while current <= today:
        total = Decimal("0")
        for key, snaps in history.items():
            qty = quantities.get(key)
            if qty is None:  # pragma: no cover -- history keys derive from quantities
                continue
            price = _locf_price(snaps, current)
            if price is None:  # pragma: no cover -- _fetch_history skips empty keys
                continue
            total += price * qty
        points.append(TimeseriesPoint(date=current.isoformat(), value=total))
        current += timedelta(days=1)
    return points, earliest


def movers(
    db: Session,
    rows: list[ParsedCollectionRow],
    window: str,
    count: int,
    min_pct: Decimal,
) -> tuple[list[CollectionMover], list[CollectionMover]]:
    """Return ``(gainers, losers)`` capped at ``count`` each."""
    if not rows:
        return [], []

    days = WINDOW_DAYS[window]
    today = date.today()
    if days is None:
        # "all" -- compare current to the earliest snapshot.
        earliest = _earliest_snapshot(db, list({r.card_id for r in rows}))
        if earliest is None:
            return [], []
        start_date = earliest
    else:
        start_date = today - timedelta(days=days - 1)

    history = _fetch_history(
        db,
        card_conditions=[(r.card_id, r.condition) for r in rows],
    )
    cards = _fetch_card_metadata(db, sorted({r.card_id for r in rows}))

    movers_list: list[CollectionMover] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.card_id, row.condition)
        if key in seen:
            # Duplicate (card_id, condition) entries collapse for movers
            # since the per-card percentage is identical regardless of
            # quantity or variant.
            continue
        seen.add(key)
        snaps = history.get(key)
        if not snaps:
            continue
        start_price = _locf_price(snaps, start_date)
        current_price = _locf_price(snaps, today)
        if start_price is None or current_price is None or start_price == 0:
            continue
        change_dollars = current_price - start_price
        change_pct = (change_dollars / start_price).quantize(Decimal("0.0001"))
        if abs(change_pct) < min_pct:
            continue
        meta = cards.get(row.card_id)
        if meta is None:
            continue  # pragma: no cover -- mirrors cards_with_prices guard
        movers_list.append(
            CollectionMover(
                card_id=row.card_id,
                card_name=meta["name"],
                set_id=meta["set_id"],
                set_name=meta["set_name"],
                condition=row.condition,
                variant=list(row.variant),
                is_first_edition=row.is_first_edition,
                start_price=start_price,
                current_price=current_price,
                change_pct=change_pct,
                change_dollars=change_dollars,
            )
        )

    gainers = sorted(
        (m for m in movers_list if m.change_pct > 0),
        key=lambda m: (-m.change_pct, m.card_id),
    )[:count]
    losers = sorted(
        (m for m in movers_list if m.change_pct < 0),
        key=lambda m: (m.change_pct, m.card_id),
    )[:count]
    return gainers, losers


# ----- private helpers -------------------------------------------------------


@dataclass(frozen=True)
class _Snap:
    captured_date: date
    market_price: Decimal


def _fetch_card_metadata(db: Session, card_ids: list[str]) -> dict[str, dict]:
    if not card_ids:  # pragma: no cover -- callers short-circuit on empty rows
        return {}
    rows = db.execute(
        text(
            """
            SELECT
                c.id            AS card_id,
                c.name          AS name,
                c.image_url     AS image_url,
                c.rarity        AS rarity,
                c.supertype     AS supertype,
                c.set_id        AS set_id,
                s.name          AS set_name,
                s.printed_total AS printed_total,
                (SELECT COUNT(*) FROM cards c2 WHERE c2.set_id = s.id) AS total_count
            FROM cards c
            JOIN sets s ON s.id = c.set_id
            WHERE c.id = ANY(:ids)
            """
        ),
        {"ids": card_ids},
    ).fetchall()
    return {
        r.card_id: {
            "name": r.name,
            "image_url": r.image_url,
            "rarity": r.rarity,
            "supertype": r.supertype,
            "set_id": r.set_id,
            "set_name": r.set_name,
            "printed_total": r.printed_total,
            "total_count": r.total_count,
        }
        for r in rows
    }


def _fetch_latest_prices(
    db: Session, card_ids: list[str]
) -> dict[tuple[str, str], Decimal]:
    """Latest snapshot per ``(card_id, condition)``.

    Variant ties are broken by preferring ``variant IS NULL`` (the
    "standard" finish), then alphabetically. Source restricted to
    tcgplayer to match the ingest pipeline's primary feed.
    """
    if not card_ids:  # pragma: no cover -- callers short-circuit on empty rows
        return {}
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (card_id, condition)
                card_id, condition, market_price
            FROM price_snapshots
            WHERE card_id = ANY(:ids)
              AND source = 'tcgplayer'
              AND market_price IS NOT NULL
            ORDER BY
                card_id,
                condition,
                captured_at DESC,
                (variant IS NULL) DESC,
                variant
            """
        ),
        {"ids": card_ids},
    ).fetchall()
    return {(r.card_id, r.condition): r.market_price for r in rows}


def _fetch_history(
    db: Session,
    card_conditions: Iterable[tuple[str, str]],
) -> dict[tuple[str, str], list[_Snap]]:
    """All snapshots per ``(card_id, condition)``, ordered ASC by date.

    Within the same captured_date, keep one row -- prefer the standard
    (NULL) variant, then the earliest captured_at. The result is an
    ascending-by-date list per key, ready for binary-search LOCF.
    """
    keys = list({(c, cond) for c, cond in card_conditions})
    if not keys:  # pragma: no cover -- callers short-circuit on empty rows
        return {}
    card_ids = sorted({c for c, _ in keys})
    conditions = sorted({cond for _, cond in keys})
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (card_id, condition, captured_date)
                card_id,
                condition,
                captured_date,
                market_price
            FROM price_snapshots
            WHERE card_id = ANY(:card_ids)
              AND condition = ANY(:conditions)
              AND source = 'tcgplayer'
              AND market_price IS NOT NULL
            ORDER BY
                card_id,
                condition,
                captured_date,
                (variant IS NULL) DESC,
                captured_at
            """
        ),
        {"card_ids": card_ids, "conditions": conditions},
    ).fetchall()

    by_key: dict[tuple[str, str], list[_Snap]] = defaultdict(list)
    keys_set = set(keys)
    for r in rows:
        key = (r.card_id, r.condition)
        if key not in keys_set:  # pragma: no cover -- ANY/ANY filter is exact
            continue
        by_key[key].append(_Snap(captured_date=r.captured_date, market_price=r.market_price))
    return by_key


def _earliest_snapshot(db: Session, card_ids: list[str]) -> date | None:
    if not card_ids:  # pragma: no cover -- callers short-circuit on empty rows
        return None
    row = db.execute(
        text(
            """
            SELECT MIN(captured_date) AS earliest
            FROM price_snapshots
            WHERE card_id = ANY(:ids)
              AND source = 'tcgplayer'
              AND market_price IS NOT NULL
            """
        ),
        {"ids": card_ids},
    ).fetchone()
    return row.earliest if row and row.earliest else None


def _locf_price(snaps: list[_Snap], target: date) -> Decimal | None:
    """Return the snapshot price on or before ``target``; fall back to
    the earliest snapshot if ``target`` predates all available history."""
    if not snaps:  # pragma: no cover -- _fetch_history only buckets non-empty
        return None
    # Snapshots are ascending by date.
    chosen: Decimal | None = None
    for s in snaps:
        if s.captured_date <= target:
            chosen = s.market_price
        else:
            break
    if chosen is None:
        # Target predates every snapshot we have -- fall back to the
        # earliest known price so the chart starts at a real value
        # instead of zero.
        return snaps[0].market_price
    return chosen


def parse_window(window: str | None) -> str:
    """Normalize and validate a window string."""
    if window is None or window == "":
        return "30d"
    candidate = window.strip().lower()
    if candidate not in WINDOW_DAYS:
        raise ValueError(
            f"window must be one of {sorted(WINDOW_DAYS)}; got {window!r}"
        )
    return candidate
