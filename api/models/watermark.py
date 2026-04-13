"""
Database model for the ingestion_watermarks table.

A watermark tracks the last time a set was successfully priced by the
ingestion pipeline. This allows the nightly run to resume from where it
left off if it is interrupted by a rate limit or other error — sets that
were already processed are skipped; sets that were not are retried.

Each row is keyed to a (source, set_id) pair so that multiple pricing
sources can each maintain their own watermark independently.
"""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class IngestionWatermark(Base):
    """
    Tracks ingestion state for one pricing source and one set.

    Attributes:
        id: Auto-incrementing integer primary key.
        source: The pricing source this watermark belongs to
            (e.g. "pokemonpricetracker").
        set_id: Foreign key linking to the sets table. Together with
            source, this uniquely identifies the watermark row.
        last_ingested_at: Timestamp of the most recent successful
            ingestion run for this source/set combination.
        backfilled: Whether the one-time historical backfill has been
            completed for this set. Only relevant on the API tier where
            a 180-day history pull is done on first run.
        updated_at: Timestamp of the last time this row was written.
            Set automatically by the database server.
        set: The Set object this watermark belongs to. Virtual attribute
            managed by SQLAlchemy.
    """

    __tablename__ = "ingestion_watermarks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    set_id: Mapped[str] = mapped_column(Text, ForeignKey("sets.id"), nullable=False)
    last_ingested_at: Mapped[datetime | None] = mapped_column(nullable=True)
    backfilled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    # Relationship to the parent set. back_populates is not set on Set because
    # we don't need to navigate watermarks from a set object.
    set: Mapped["Set"] = relationship("Set")  # noqa: F821
