"""
Database model for the set_identifiers table.

A set identifier maps a canonical set ID (e.g. "base1") to the name or ID
that a specific external data source (e.g. PokemonPriceTracker) uses for
the same set. Different sources use different naming conventions:

  - TCGdex uses slug IDs like "base1"
  - PokemonPriceTracker uses display names like "Base Set"
  - TCGPlayer uses numeric IDs

This table is the single source of truth for those mappings. The ingestion
scripts always resolve through this table rather than hard-coding names.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class SetIdentifier(Base):
    """
    Maps a canonical set ID to the identifier used by one external source.

    Attributes:
        id: Auto-incrementing integer primary key.
        set_id: FK → sets.id. The canonical set ID this mapping belongs to.
        source: The data source this identifier belongs to.
            Use "tcgdex", "ppt", or "tcgplayer".
        identifier: The name or ID that source uses for this set.
        identifier_type: "id" for slug/numeric identifiers, "name" for
            display names. Together with set_id and source this is unique.
        created_at: Timestamp of when this row was inserted.
        set: The Set object this identifier belongs to. Virtual attribute.
    """

    __tablename__ = "set_identifiers"
    __table_args__ = (
        UniqueConstraint("set_id", "source", "identifier_type", name="uq_set_identifiers_set_source_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    set_id: Mapped[str] = mapped_column(Text, ForeignKey("sets.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    identifier: Mapped[str] = mapped_column(Text, nullable=False)
    identifier_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="name")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    set: Mapped["Set"] = relationship("Set")  # noqa: F821
