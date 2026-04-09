"""Routes for /cards endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models.card import Card, PriceSnapshot
from schemas.card import CardDetailResponse, PriceSnapshotResponse

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("/{card_id}", response_model=CardDetailResponse)
def get_card(card_id: str, db: Session = Depends(get_db)):
    """
    Return a single card with its latest price snapshot per condition.

    Only the most recent snapshot for each condition is returned so the
    response stays compact while still reflecting current prices.
    """
    card = (
        db.query(Card)
        .options(joinedload(Card.price_snapshots))
        .filter(Card.id == card_id)
        .first()
    )
    if card is None:
        raise HTTPException(status_code=404, detail=f"Card '{card_id}' not found")

    # Deduplicate: keep only the latest snapshot per condition.
    seen: set[str] = set()
    latest_prices: list[PriceSnapshot] = []
    for snap in card.price_snapshots:  # already ordered by captured_at desc
        if snap.condition not in seen:
            seen.add(snap.condition)
            latest_prices.append(snap)

    return CardDetailResponse(
        **{col: getattr(card, col) for col in [
            "id", "set_id", "name", "number", "rarity", "supertype", "image_url", "created_at"
        ]},
        latest_prices=[PriceSnapshotResponse.model_validate(s) for s in latest_prices],
    )
