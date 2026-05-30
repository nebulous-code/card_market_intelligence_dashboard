"""
URL route handlers for canonical-value reference data.

These endpoints expose the closed set of allowed condition and variant
values plus their display labels so the frontend can render dropdowns
without hardcoding either side of the mapping.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.canonical import CanonicalCondition, CanonicalRarity, CanonicalVariant
from schemas.reference import CanonicalValueResponse

router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/conditions", response_model=list[CanonicalValueResponse])
def list_canonical_conditions(db: Session = Depends(get_db)):
    """
    Return every canonical condition (NM, LP, ..., PSA-10, BGS-9.5, ...).

    Ordered by display_order so the frontend can render the list as-is.
    """
    rows = (
        db.query(CanonicalCondition)
        .order_by(CanonicalCondition.display_order, CanonicalCondition.value)
        .all()
    )
    return [
        CanonicalValueResponse(
            value=row.value,
            label=row.display_label,
            display_order=row.display_order,
        )
        for row in rows
    ]


@router.get("/variants", response_model=list[CanonicalValueResponse])
def list_canonical_variants(db: Session = Depends(get_db)):
    """
    Return every canonical variant (Standard, Holofoil, ..., 1st Ed. Holo).

    The Standard row has value=null. Ordered by display_order.
    """
    rows = (
        db.query(CanonicalVariant)
        .order_by(CanonicalVariant.display_order, CanonicalVariant.value)
        .all()
    )
    return [
        CanonicalValueResponse(
            value=row.value,
            label=row.display_label,
            display_order=row.display_order,
        )
        for row in rows
    ]


@router.get("/rarities", response_model=list[CanonicalValueResponse])
def list_canonical_rarities(db: Session = Depends(get_db)):
    """
    Return every canonical rarity (hyper_rare, ..., common).

    Ordered rarest-first so a single ORDER BY display_order drives the
    box-and-whisker chart's rarest-on-the-left column layout.
    """
    rows = (
        db.query(CanonicalRarity)
        .order_by(CanonicalRarity.display_order, CanonicalRarity.value)
        .all()
    )
    return [
        CanonicalValueResponse(
            value=row.value,
            label=row.display_label,
            display_order=row.display_order,
        )
        for row in rows
    ]
