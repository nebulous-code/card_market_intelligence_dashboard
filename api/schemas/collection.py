"""
Response and helper schemas for the /collection/* endpoints.

The validator emits ParsedCollectionRow objects which are also what we
serialize into the collection_sessions JSONB column. RowError is the
per-row failure shape returned to the frontend on validation failure.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class ParsedCollectionRow(BaseModel):
    """One validated, matched row of the user's uploaded workbook.

    `variant` is a list because the upload allows comma/pipe/slash/&
    -separated values in one cell (e.g. ``Reverse Holo, Misprint``).
    Each entry is normalized via variant_normalizer.normalize. An empty
    list means the user left the variant cell blank.
    """

    card_id: str
    condition: str
    variant: list[str]
    is_first_edition: bool
    quantity: int
    purchase_price: Decimal | None = None


class RowError(BaseModel):
    """One row that failed validation, surfaced back to the frontend."""

    row_number: int
    message: str


class UploadValidationFailure(BaseModel):
    """Returned when the workbook parsed but individual rows failed."""

    structural_error: str | None = None
    total_rows: int
    error_rows: list[RowError]
    distinct_error_messages: list[str]


class UploadSuccess(BaseModel):
    """Returned when an upload (or mock load) creates a session."""

    session_id: str
    card_count: int
    set_count: int


class SessionResponse(BaseModel):
    """Returned by GET /collection/session for the dashboard view."""

    session_id: str
    rows: list[ParsedCollectionRow]
    card_count: int
    set_count: int


class CollectionCardWithPrice(BaseModel):
    """One session row joined to current pricing + card metadata.

    The dashboard treats each row as a single line item; the same card
    can appear multiple times if the user owns it in different
    conditions / variants / 1st-edition states.
    """

    card_id: str
    card_name: str
    image_url: str | None = None
    rarity: str | None = None
    supertype: str | None = None
    set_id: str
    set_name: str
    printed_total: int
    total_count: int
    condition: str
    variant: list[str]
    is_first_edition: bool
    quantity: int
    market_price: Decimal | None = None
    purchase_price: Decimal | None = None


class CollectionCardsWithPricesResponse(BaseModel):
    """Top-level response for GET /collection/cards-with-prices."""

    cards: list[CollectionCardWithPrice]


class TimeseriesPoint(BaseModel):
    """One day on the price-over-time chart."""

    date: str  # ISO date (YYYY-MM-DD)
    value: Decimal


class CollectionTimeseriesResponse(BaseModel):
    """Daily total collection value across the chosen window.

    ``earliest_snapshot`` is the oldest snapshot in the user's collection
    (across all cards) so the frontend can disable presets that predate
    the available data.
    """

    points: list[TimeseriesPoint]
    earliest_snapshot: str | None = None


class CollectionMover(BaseModel):
    """One row of the gainers or losers list."""

    card_id: str
    card_name: str
    set_id: str
    set_name: str
    condition: str
    variant: list[str]
    is_first_edition: bool
    start_price: Decimal
    current_price: Decimal
    change_pct: Decimal
    change_dollars: Decimal


class CollectionMoversResponse(BaseModel):
    """Top-level response for GET /collection/movers."""

    gainers: list[CollectionMover]
    losers: list[CollectionMover]
