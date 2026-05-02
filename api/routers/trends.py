"""
URL route handlers for the /trends/* endpoints.

These power the Market Trends page on the frontend. Today there is one
analysis (condition multipliers) and a small index endpoint for the set
selector chips; future stories can add more analyses on the same prefix.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func
from sqlalchemy.orm import Session

from database import get_db
from models.canonical import CanonicalRarity
from models.condition_multiplier import ConditionMultiplier
from models.set import Set
from schemas.trends import (
    ConditionMultiplierResponse,
    GroupingResponse,
    SetsWithMultipliersResponse,
    SetWithMultipliersEntry,
    TransitionResponse,
)

router = APIRouter(prefix="/trends", tags=["trends"])


_VALID_GROUPING_TYPES = ("rarity", "supertype")


@router.get("/sets-with-multipliers", response_model=SetsWithMultipliersResponse)
def list_sets_with_multipliers(db: Session = Depends(get_db)):
    """
    Return the sets that have at least one row in condition_multipliers.

    Used by the heatmap page's set selector chips. Sets without any
    multiplier rows are intentionally excluded -- selecting them would
    just show the empty state and clutters the chip list.

    Ordered by release_date descending (newest first), matching the
    /sets endpoint convention.
    """
    rows = (
        db.query(Set.id, Set.name)
        .filter(
            exists().where(ConditionMultiplier.set_id == Set.id)
        )
        .order_by(Set.release_date.desc().nulls_last())
        .all()
    )
    return SetsWithMultipliersResponse(
        sets=[
            SetWithMultipliersEntry(set_id=r.id, set_display_name=r.name)
            for r in rows
        ]
    )


@router.get("/condition-multipliers", response_model=ConditionMultiplierResponse)
def get_condition_multipliers(
    set_id: str = Query(..., description="Canonical set ID, e.g. 'base1'"),
    grouping_type: str = Query(
        ..., description="Either 'rarity' or 'supertype'"
    ),
    db: Session = Depends(get_db),
):
    """
    Return all multiplier rows for one (set, grouping_type) pair, structured
    by grouping_value with each grouping carrying its full transition list.

    For grouping_type='rarity' the response is ordered by canonical
    display_order (rarest first) and grouping_label is the canonical
    display_label. For 'supertype' the value is its own label and ordering
    is alphabetical -- supertypes are not canonicalised.
    """
    if grouping_type not in _VALID_GROUPING_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"grouping_type must be one of {_VALID_GROUPING_TYPES}; "
                f"got {grouping_type!r}"
            ),
        )

    set_record = db.query(Set).filter(Set.id == set_id).first()
    if set_record is None:
        raise HTTPException(status_code=404, detail=f"Set '{set_id}' not found")

    rows = (
        db.query(ConditionMultiplier)
        .filter(
            ConditionMultiplier.set_id == set_id,
            ConditionMultiplier.grouping_type == grouping_type,
        )
        .all()
    )

    # last_refreshed is reported as the most recent refresh across all rows
    # for this (set, grouping_type). Per-row precision isn't useful to the
    # frontend; one timestamp answers "when was this view last updated".
    last_refreshed = (
        db.query(func.max(ConditionMultiplier.last_refreshed))
        .filter(
            ConditionMultiplier.set_id == set_id,
            ConditionMultiplier.grouping_type == grouping_type,
        )
        .scalar()
    )

    # Build a label + sort-order lookup so rarity rows can render display
    # names ("Hyper Rare") and sort by canonical display_order. Supertype
    # rows skip the lookup since their raw value is also their label.
    rarity_meta: dict[str, tuple[str, int]] = {}
    if grouping_type == "rarity":
        rarity_meta = {
            r.value: (r.display_label, r.display_order)
            for r in db.query(CanonicalRarity).all()
        }

    # Group the flat rowset by grouping_value while preserving iteration
    # order in a way we can sort later.
    grouped: dict[str, list[ConditionMultiplier]] = {}
    for row in rows:
        grouped.setdefault(row.grouping_value, []).append(row)

    def sort_key(grouping_value: str) -> tuple:
        if grouping_type == "rarity":
            meta = rarity_meta.get(grouping_value)
            if meta is not None:
                return (meta[1], grouping_value)
            # Unknown rarity -- shouldn't happen post-FK, but keep the
            # response stable rather than raising.
            return (10**9, grouping_value)
        return (grouping_value,)

    groupings: list[GroupingResponse] = []
    for grouping_value in sorted(grouped, key=sort_key):
        label = (
            rarity_meta.get(grouping_value, (grouping_value, 0))[0]
            if grouping_type == "rarity"
            else grouping_value
        )
        groupings.append(
            GroupingResponse(
                grouping_value=grouping_value,
                grouping_label=label,
                transitions=[
                    TransitionResponse(
                        from_condition=cm.from_condition,
                        to_condition=cm.to_condition,
                        multiplier=cm.multiplier,
                        data_points=cm.data_points,
                    )
                    for cm in grouped[grouping_value]
                ],
            )
        )

    return ConditionMultiplierResponse(
        set_id=set_record.id,
        set_display_name=set_record.name,
        grouping_type=grouping_type,
        last_refreshed=last_refreshed,
        groupings=groupings,
    )
