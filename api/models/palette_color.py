"""
ORM model for the palette_colors table.

Read-only from the API's perspective; new entries are added by the
operator via SQL. Used by the Collection Dashboard to assign a stable
color to each set.
"""

from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class PaletteColor(Base):
    """One color entry from the palette, ordered by display_order."""

    __tablename__ = "palette_colors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    color_hex: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
