"""
URL route handlers for set-related API endpoints.

This file defines what happens when a client makes a request to any URL
that starts with /sets. FastAPI reads the function signatures and return
type annotations to automatically validate inputs, serialize outputs, and
generate the interactive documentation at /docs.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.set import Set
from models.card import Card, PriceSnapshot
from schemas.card import CardResponse, PriceSnapshotResponse, SetCardPricesResponse
from schemas.set import SetResponse

# Create a router for the /sets URL prefix. All routes defined in this file
# will automatically be available under /sets. The tags parameter groups
# these endpoints together in the /docs page.
router = APIRouter(prefix="/sets", tags=["sets"])


@router.get("", response_model=list[SetResponse])
def list_sets(db: Session = Depends(get_db)):
    """
    Return all sets stored in the database.

    Sets are ordered by release date descending so the most recently
    released set appears first. This is the endpoint the frontend calls
    to populate the set selector dropdown.

    Args:
        db: Database session provided automatically by FastAPI's dependency
            injection system via the get_db function.

    Returns:
        list[SetResponse]: A list of all sets. Returns an empty list if no
            sets have been ingested yet.
    """
    # Query all sets and sort them newest first.
    # nulls_last() ensures sets without a release date sort to the bottom
    # rather than the top, which is PostgreSQL's default for DESC ordering.
    return db.query(Set).order_by(Set.release_date.desc().nulls_last()).all()


@router.get("/{set_id}", response_model=SetResponse)
def get_set(set_id: str, db: Session = Depends(get_db)):
    """
    Return a single set by its TCGdex ID.

    Args:
        set_id: The TCGdex set identifier from the URL path (e.g. "base1").
        db: Database session provided by dependency injection.

    Returns:
        SetResponse: The matching set object.

    Raises:
        HTTPException: 404 if no set with the given ID exists in the database.
    """
    # Look up the set by primary key.
    record = db.query(Set).filter(Set.id == set_id).first()

    # Return a 404 if the set was not found rather than returning null,
    # which would be ambiguous from the client's perspective.
    if record is None:
        raise HTTPException(status_code=404, detail=f"Set '{set_id}' not found")

    return record


@router.get("/{set_id}/cards", response_model=list[CardResponse])
def list_cards_for_set(set_id: str, db: Session = Depends(get_db)):
    """
    Return all cards belonging to a given set.

    Cards are ordered by their card number within the set. The set is
    validated first so the response is a 404 rather than an empty list
    if the set ID does not exist at all.

    Args:
        set_id: The TCGdex set identifier from the URL path (e.g. "base1").
        db: Database session provided by dependency injection.

    Returns:
        list[CardResponse]: All cards in the set ordered by card number.
            Returns an empty list if the set exists but has no cards.

    Raises:
        HTTPException: 404 if no set with the given ID exists in the database.
    """
    # Confirm the set exists before querying for its cards.
    # Without this check, a typo in the set ID would return an empty list
    # instead of a meaningful error.
    set_record = db.query(Set).filter(Set.id == set_id).first()
    if set_record is None:
        raise HTTPException(status_code=404, detail=f"Set '{set_id}' not found")

    # Fetch all cards for this set, sorted by card number.
    cards = (
        db.query(Card)
        .filter(Card.set_id == set_id)
        .order_by(Card.number)
        .all()
    )
    return cards


@router.get("/{set_id}/cards/prices", response_model=SetCardPricesResponse)
def get_prices_for_set(set_id: str, db: Session = Depends(get_db)):
    """
    Return the latest price snapshot per condition for every card in a set.

    This is a batch alternative to calling GET /cards/{id} once per card.
    The dashboard uses this endpoint to avoid firing 100+ parallel requests
    when a set is selected, which would exhaust the database connection pool.

    The query fetches all snapshots for the set in one round-trip, then
    deduplicates them in Python to keep only the most recent per (card, condition)
    pair -- the same logic as GET /cards/{id} but applied across the whole set.

    Args:
        set_id: The TCGdex set identifier from the URL path (e.g. "base1").
        db: Database session provided by dependency injection.

    Returns:
        SetCardPricesResponse: A dict mapping card ID to its latest prices list.
            Cards with no price data are omitted from the dict.

    Raises:
        HTTPException: 404 if no set with the given ID exists in the database.
    """
    set_record = db.query(Set).filter(Set.id == set_id).first()
    if set_record is None:
        raise HTTPException(status_code=404, detail=f"Set '{set_id}' not found")

    # Fetch all snapshots for the set in one query, ordered newest-first so
    # the deduplication loop below always sees the most recent row first.
    snapshots = (
        db.query(PriceSnapshot)
        .join(Card, PriceSnapshot.card_id == Card.id)
        .filter(Card.set_id == set_id)
        .order_by(PriceSnapshot.card_id, PriceSnapshot.captured_at.desc())
        .all()
    )

    # Deduplicate: keep only the latest snapshot per (card_id, condition).
    seen: dict[str, set[str]] = {}
    prices: dict[str, list] = {}
    for snap in snapshots:
        cid = snap.card_id
        if cid not in seen:
            seen[cid] = set()
        if snap.condition not in seen[cid]:
            seen[cid].add(snap.condition)
            prices.setdefault(cid, []).append(snap)

    return SetCardPricesResponse(
        prices={
            cid: [PriceSnapshotResponse.model_validate(s) for s in snaps]
            for cid, snaps in prices.items()
        }
    )
