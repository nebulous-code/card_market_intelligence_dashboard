"""
URL route handlers for card-related API endpoints.

This file handles two endpoints:
  GET /cards/{card_id}               -- single card with latest prices
  GET /cards/{card_id}/price-history -- full price history, filterable

Price snapshots are deduplicated in get_card so clients only receive the
most recent price per condition. The price-history endpoint returns the
full unfiltered history for charting over time.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models.canonical import CanonicalCondition, CanonicalVariant
from models.card import Card, PriceSnapshot
from schemas.card import CardDetailResponse, PriceHistoryResponse, PriceSnapshotResponse

# Create a router for the /cards URL prefix.
router = APIRouter(prefix="/cards", tags=["cards"])


def _label_maps(db: Session) -> tuple[dict[str, str], dict[str | None, str]]:
    """
    Load the two canonical label dicts once per request.

    Returns (condition_label_by_value, variant_label_by_value). Each map
    falls back to the raw value if a snapshot row contains a value that
    isn't in the canonical table (shouldn't happen post-FK, but keeps
    the response stable if a row is somehow stale).
    """
    cond = {row.value: row.display_label for row in db.query(CanonicalCondition).all()}
    var = {row.value: row.display_label for row in db.query(CanonicalVariant).all()}
    return cond, var


def _to_snapshot_response(
    snap: PriceSnapshot,
    cond_labels: dict[str, str],
    variant_labels: dict[str | None, str],
) -> PriceSnapshotResponse:
    """Build a PriceSnapshotResponse with display labels stamped in."""
    return PriceSnapshotResponse(
        id=snap.id,
        source=snap.source,
        condition=snap.condition,
        condition_label=cond_labels.get(snap.condition, snap.condition),
        variant=snap.variant,
        variant_label=variant_labels.get(snap.variant, snap.variant or "Standard"),
        market_price=snap.market_price,
        low_price=snap.low_price,
        high_price=snap.high_price,
        captured_at=snap.captured_at,
        captured_date=snap.captured_date,
    )


@router.get("/{card_id}", response_model=CardDetailResponse)
def get_card(card_id: str, db: Session = Depends(get_db)):
    """
    Return a single card with its latest price per condition.

    The price_snapshots table is append-only and may contain many rows
    for the same card if the ingestion script has been run multiple times.
    This endpoint filters down to only the most recent snapshot for each
    condition so the response stays compact.

    Args:
        card_id: The TCGdex card identifier from the URL path (e.g. "base1-4").
        db: Database session provided by FastAPI's dependency injection.

    Returns:
        CardDetailResponse: The card object with a latest_prices list
            containing at most one entry per condition.

    Raises:
        HTTPException: 404 if no card with the given ID exists in the database.
    """
    # Load the card with its price snapshots and its parent set in one query.
    card = (
        db.query(Card)
        .options(joinedload(Card.price_snapshots), joinedload(Card.set))
        .filter(Card.id == card_id)
        .first()
    )

    if card is None:
        raise HTTPException(status_code=404, detail=f"Card '{card_id}' not found")

    # NOTE: latest_prices will always be empty in Milestone 1 because price
    # ingestion has not been implemented yet. It will be populated in
    # Milestone 2 via the eBay API. This is expected, not a bug.

    # Deduplicate snapshots to keep only the latest one per (condition, variant)
    # pair. The relationship is already ordered by captured_at descending, so
    # the first time we see a combination it is guaranteed to be the newest.
    seen: set[tuple] = set()
    latest_prices: list[PriceSnapshot] = []
    for snap in card.price_snapshots:
        key = (snap.condition, snap.variant)
        if key not in seen:
            seen.add(key)
            latest_prices.append(snap)

    cond_labels, variant_labels = _label_maps(db)

    return CardDetailResponse.model_validate(
        {
            **card.__dict__,
            "latest_prices": [
                _to_snapshot_response(s, cond_labels, variant_labels)
                for s in latest_prices
            ],
            "set_display_name": card.set.name if card.set else card.set_id,
            "set_printed_total": card.set.printed_total if card.set else 0,
        }
    )


@router.get("/{card_id}/price-history", response_model=PriceHistoryResponse)
def get_price_history(
    card_id: str,
    source: Optional[str] = Query(None, description="Filter by price source (e.g. 'tcgplayer', 'psa')"),
    condition: Optional[str] = Query(None, description="Filter by condition (e.g. 'NM', 'LP')"),
    variant: Optional[str] = Query(None, description="Filter by variant (e.g. 'holofoil', '1st_edition_holofoil')"),
    db: Session = Depends(get_db),
):
    """
    Return the full price history for a single card.

    Snapshots are ordered oldest-first so the caller can chart them in
    chronological order without any additional sorting. Optionally filtered
    by source, condition, and/or variant to reduce response size for charts
    that show a single series.

    Args:
        card_id: The TCGdex card identifier from the URL path (e.g. "base1-4").
        source: Optional filter by price source (e.g. "tcgplayer", "psa").
        condition: Optional filter by condition (e.g. "NM", "LP").
        variant: Optional filter by printing variant (e.g. "holofoil",
            "1st_edition_holofoil"). Omit to return all variants.
        db: Database session provided by FastAPI's dependency injection.

    Returns:
        PriceHistoryResponse: The card ID and a list of all matching
            price snapshots ordered by captured_date ascending.

    Raises:
        HTTPException: 404 if no card with the given ID exists in the database.
    """
    # Confirm the card exists before querying its snapshots.
    card = db.query(Card).filter(Card.id == card_id).first()
    if card is None:
        raise HTTPException(status_code=404, detail=f"Card '{card_id}' not found")

    # Build the snapshot query with optional filters and chronological order.
    query = db.query(PriceSnapshot).filter(PriceSnapshot.card_id == card_id)
    if source:
        query = query.filter(PriceSnapshot.source == source)
    if condition:
        query = query.filter(PriceSnapshot.condition == condition)
    if variant == "__none__":
        # Sentinel sent by the UI to filter for cards with no printing variant
        # (e.g. modern non-holos stored with variant=NULL). Treated separately
        # because variant=NULL can't be matched with `== None` in SQL.
        query = query.filter(PriceSnapshot.variant.is_(None))
    elif variant:
        query = query.filter(PriceSnapshot.variant == variant)
    snapshots = query.order_by(PriceSnapshot.captured_date.asc()).all()

    cond_labels, variant_labels = _label_maps(db)
    return PriceHistoryResponse(
        card_id=card_id,
        snapshots=[
            _to_snapshot_response(s, cond_labels, variant_labels) for s in snapshots
        ],
    )
