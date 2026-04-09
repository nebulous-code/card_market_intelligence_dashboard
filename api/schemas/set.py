"""Pydantic schemas for set responses."""

from datetime import date, datetime

from pydantic import BaseModel


class SetResponse(BaseModel):
    id: str
    name: str
    series: str
    printed_total: int
    release_date: date | None
    symbol_url: str | None
    logo_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
