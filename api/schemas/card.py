"""
Pydantic response schemas for card and price snapshot data.

These schemas define the JSON shape that the API returns for card-related
endpoints. There are three schemas here that build on each other:

  PriceSnapshotResponse -- a single price record for one card condition
  CardResponse          -- a card without price data (used in list views)
  CardDetailResponse    -- a card with its latest prices attached
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PriceSnapshotResponse(BaseModel):
    """
    The shape of a single price snapshot returned by the API.

    A price snapshot captures what a card was selling for at a specific
    moment in time. The condition field distinguishes between different
    versions of the same card (e.g. a holofoil sells for more than a
    normal copy).

    Attributes:
        id: Auto-incrementing database ID for this snapshot row.
        source: Where the price came from (e.g. "tcgplayer").
        condition: The card finish this price applies to. One of
            "normal", "holofoil", or "reverseHolofoil".
        market_price: The market price in USD. Can be null if not available.
        low_price: The lowest recent sale price in USD. Can be null.
        high_price: The highest recent sale price in USD. Can be null.
        captured_at: When this price was recorded.
    """

    id: int
    source: str
    condition: str
    market_price: Decimal | None
    low_price: Decimal | None
    high_price: Decimal | None
    captured_at: datetime

    model_config = {"from_attributes": True}


class CardResponse(BaseModel):
    """
    The shape of a card object returned by list endpoints.

    This is the slimmer card representation used when returning many cards
    at once, such as in GET /sets/{set_id}/cards. It does not include price
    data to keep the response size manageable.

    Attributes:
        id: The TCGdex card identifier (e.g. "base1-4").
        set_id: The ID of the set this card belongs to.
        name: The card's official name (e.g. "Charizard").
        number: The card number within its set (e.g. "4").
        rarity: The rarity printed on the card. Can be null.
        supertype: The card category: "Pokemon", "Trainer", or "Energy".
            Can be null for edge cases.
        image_url: Direct URL to the card image. Can be null.
        created_at: When this record was added to the database.
    """

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
    """
    A card with its most recent price snapshot per condition attached.

    Returned by GET /cards/{card_id}. Extends CardResponse with a
    latest_prices list so the caller gets everything they need in one
    request. Only one snapshot per condition is included -- the most
    recent one -- rather than the full history.

    Attributes:
        latest_prices: List of the most recent price snapshots for this
            card, one per available condition. Empty if no price data
            has been ingested for this card yet.
    """

    latest_prices: list[PriceSnapshotResponse]
