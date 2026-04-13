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
from models.card import Card, PriceSnapshot
from schemas.card import CardDetailResponse, PriceHistoryResponse, PriceSnapshotResponse

# Create a router for the /cards URL prefix.
router = APIRouter(prefix="/cards", tags=["cards"])


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
    # Load the card and eagerly load its price snapshots in the same query.
    # joinedload avoids a second round-trip to the database for the snapshots.
    # Without it, accessing card.price_snapshots would trigger an extra query
    # for every card requested (known as the N+1 query problem).
    card = (
        db.query(Card)
        .options(joinedload(Card.price_snapshots))
        .filter(Card.id == card_id)
        .first()
    )

    if card is None:
        raise HTTPException(status_code=404, detail=f"Card '{card_id}' not found")

    # NOTE: latest_prices will always be empty in Milestone 1 because price
    # ingestion has not been implemented yet. It will be populated in
    # Milestone 2 via the eBay API. This is expected, not a bug.

    # Deduplicate snapshots to keep only the latest one per condition.
    # The relationship is already ordered by captured_at descending, so
    # the first time we see a condition it is guaranteed to be the newest.
    seen: set[str] = set()
    latest_prices: list[PriceSnapshot] = []
    for snap in card.price_snapshots:
        if snap.condition not in seen:
            seen.add(snap.condition)
            latest_prices.append(snap)

    # Build and return the response object. model_validate reads all fields
    # declared on CardDetailResponse directly from the ORM object, so adding
    # a new column to the model and schema is sufficient -- this line never
    # needs to change.
    return CardDetailResponse.model_validate(
        {**card.__dict__, "latest_prices": [PriceSnapshotResponse.model_validate(s) for s in latest_prices]}
    )


@router.get("/{card_id}/price-history", response_model=PriceHistoryResponse)
def get_price_history(
    card_id: str,
    source: Optional[str] = Query(None, description="Filter by price source (e.g. 'tcgplayer', 'psa')"),
    condition: Optional[str] = Query(None, description="Filter by condition (e.g. 'NM', 'PSA-10')"),
    db: Session = Depends(get_db),
):
    """
    Return the full price history for a single card.

    Snapshots are ordered oldest-first so the caller can chart them in
    chronological order without any additional sorting. Optionally filtered
    by source (e.g. "tcgplayer", "psa") and/or condition (e.g. "NM",
    "PSA-10") to reduce response size for charts that show a single series.

    Args:
        card_id: The TCGdex card identifier from the URL path (e.g. "base1-4").
        source: Optional query parameter to filter snapshots by price source.
        condition: Optional query parameter to filter snapshots by condition.
        db: Database session provided by FastAPI's dependency injection.

    Returns:
        PriceHistoryResponse: The card ID and a list of all matching
            price snapshots ordered by captured_at ascending.

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
    snapshots = query.order_by(PriceSnapshot.captured_at.asc()).all()

    return PriceHistoryResponse(
        card_id=card_id,
        snapshots=[PriceSnapshotResponse.model_validate(s) for s in snapshots],
    )
