"""Pydantic schemas for card and price snapshot responses."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PriceSnapshotResponse(BaseModel):
    id: int
    source: str
    condition: str
    market_price: Decimal | None
    low_price: Decimal | None
    high_price: Decimal | None
    captured_at: datetime

    model_config = {"from_attributes": True}


class CardResponse(BaseModel):
    id: str
    set_id: str
    name: str
    number: str
    rarity: str | None
    supertype: str | None
    image_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CardDetailResponse(CardResponse):
    """Card with its most recent price snapshot per condition."""

    latest_prices: list[PriceSnapshotResponse]
