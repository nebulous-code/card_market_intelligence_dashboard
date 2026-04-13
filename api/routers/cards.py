"""
URL route handlers for card-related API endpoints.

This file handles requests to /cards/{card_id}. It returns a single card
along with its most recent price snapshot for each available condition
(normal, holofoil, reverseHolofoil).

Price snapshots are deduplicated here rather than in the database query
so that the full price history is preserved in the database while clients
only receive the current prices they actually need.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models.card import Card, PriceSnapshot
from schemas.card import CardDetailResponse, PriceSnapshotResponse

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
