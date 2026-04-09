"""Routes for /sets endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.card import Card
from models.set import Set
from schemas.card import CardResponse
from schemas.set import SetResponse

router = APIRouter(prefix="/sets", tags=["sets"])


@router.get("", response_model=list[SetResponse])
def list_sets(db: Session = Depends(get_db)):
    """Return all sets in the database."""
    return db.query(Set).order_by(Set.release_date.desc()).all()


@router.get("/{set_id}", response_model=SetResponse)
def get_set(set_id: str, db: Session = Depends(get_db)):
    """Return a single set by its pokemontcg.io ID."""
    record = db.query(Set).filter(Set.id == set_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail=f"Set '{set_id}' not found")
    return record


@router.get("/{set_id}/cards", response_model=list[CardResponse])
def list_cards_for_set(set_id: str, db: Session = Depends(get_db)):
    """Return all cards belonging to the given set."""
    set_record = db.query(Set).filter(Set.id == set_id).first()
    if set_record is None:
        raise HTTPException(status_code=404, detail=f"Set '{set_id}' not found")

    cards = (
        db.query(Card)
        .filter(Card.set_id == set_id)
        .order_by(Card.number)
        .all()
    )
    return cards
