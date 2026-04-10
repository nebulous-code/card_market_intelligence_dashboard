"""
Pydantic response schema for set data.

Schemas define the shape of the JSON that the API sends back to clients.
They are separate from the database models intentionally -- the database
model describes how data is stored, while the schema describes how it is
presented over the API. This separation makes it easy to change one
without affecting the other.

Pydantic validates the data automatically when a response is built and
will raise a clear error if any field is missing or has the wrong type.
"""

from datetime import date, datetime

from pydantic import BaseModel


class SetResponse(BaseModel):
    """
    The shape of a set object returned by the API.

    This is what a client receives when they call GET /sets or
    GET /sets/{set_id}. Every field maps directly to a column in the
    sets database table.

    Attributes:
        id: The TCGdex set identifier (e.g. "base1").
        name: The display name of the set (e.g. "Base Set").
        series: The series the set belongs to (e.g. "Base").
        printed_total: Number of cards officially printed in the set.
        release_date: The date the set was released. Can be null.
        symbol_url: URL to the set symbol image. Can be null.
        logo_url: URL to the set logo image. Can be null.
        created_at: When this record was added to the database.
    """

    id: str
    name: str
    series: str
    printed_total: int
    release_date: date | None
    symbol_url: str | None
    logo_url: str | None
    created_at: datetime

    # from_attributes=True allows Pydantic to read values from a SQLAlchemy
    # model object directly, rather than requiring a plain dictionary.
    model_config = {"from_attributes": True}
