"""
Database model for the sets table.

A "set" is an official release of Pokemon cards -- for example, Base Set
or Jungle. This model tells SQLAlchemy what columns the sets table has and
how they map to Python objects.

Each Set can have many Cards associated with it. SQLAlchemy manages that
relationship automatically through the cards attribute.
"""

from datetime import datetime

from sqlalchemy import Date, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Set(Base):
    """
    Represents a single Pokemon card set in the database.

    Attributes:
        id: The unique identifier from TCGdex (e.g. "base1"). Used as the
            primary key rather than an auto-incrementing number because the
            TCGdex ID is already unique and human-readable.
        name: The display name of the set (e.g. "Base Set").
        series: The series the set belongs to (e.g. "Base").
        printed_total: The number of cards printed in the set as shown on
            the physical cards. This is the "official" count.
        release_date: The date the set was officially released. Nullable
            because some older sets do not have a reliable release date
            in the TCGdex data.
        symbol_url: URL to the set symbol image (the small icon shown on
            card backs). Nullable because not all sets have a symbol.
        logo_url: URL to the set logo image. Nullable because not all sets
            have a logo available from TCGdex.
        created_at: Timestamp of when this row was first inserted into the
            database. Set automatically by the database server.
        cards: The list of Card objects that belong to this set. This is a
            virtual attribute managed by SQLAlchemy -- it does not map to
            a column but lets you access related cards directly.
    """

    __tablename__ = "sets"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    series: Mapped[str] = mapped_column(Text, nullable=False)
    printed_total: Mapped[int] = mapped_column(Integer, nullable=False)
    release_date: Mapped[datetime] = mapped_column(Date, nullable=True)
    symbol_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    # Relationship to the Card model. back_populates="set" tells SQLAlchemy
    # that Card.set points back to this side of the relationship.
    cards: Mapped[list["Card"]] = relationship("Card", back_populates="set")  # noqa: F821
