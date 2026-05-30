"""
Response schema for GET /palette.
"""

from pydantic import BaseModel


class PaletteResponse(BaseModel):
    """Ordered list of hex color strings."""

    colors: list[str]
