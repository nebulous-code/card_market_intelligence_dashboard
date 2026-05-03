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
