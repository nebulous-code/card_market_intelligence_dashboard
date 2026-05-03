"""
URL route handler for the /palette endpoint.

Returns the full palette in display_order. The Collection Dashboard
fetches this once on mount and assigns colors to sets in the order they
appear in its data, cycling if there are more sets than colors.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.palette_color import PaletteColor
from schemas.palette import PaletteResponse

router = APIRouter(tags=["palette"])


@router.get("/palette", response_model=PaletteResponse)
def get_palette(db: Session = Depends(get_db)) -> PaletteResponse:
    rows = (
        db.query(PaletteColor)
        .order_by(PaletteColor.display_order)
        .all()
    )
    return PaletteResponse(colors=[r.color_hex for r in rows])
