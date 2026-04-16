"""
Database models for the cards and price_snapshots tables.

A Card is an individual Pokemon card within a set. A PriceSnapshot is a
point-in-time record of what that card was selling for on a given date.

Price snapshots are append-only -- new rows are always inserted rather
than updating existing ones. This preserves the full price history so
that trends can be analyzed over time in later milestones.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Card(Base):
    """
    Represents a single Pokemon card in the database.

    Attributes:
        id: The unique identifier from TCGdex (e.g. "base1-4"). Used as
            the primary key because it is already globally unique.
        set_id: The ID of the set this card belongs to. This is a foreign
            key linking back to the sets table.
        name: The official name printed on the card (e.g. "Charizard").
        number: The card number within its set (e.g. "4"). Stored as text
            rather than an integer because some sets use alphanumeric
            numbering like "SV001" or "SWSH001".
        rarity: The rarity of the card as shown on the card itself
            (e.g. "Rare Holo"). Nullable because not all cards have a
            printed rarity.
        supertype: The broad category of the card. One of "Pokemon",
            "Trainer", or "Energy". Nullable for edge cases.
        image_url: A direct URL to the card image. The ingestion script
            appends "/low.png" to the base URL from TCGdex. Nullable
            because not all cards have images available.
        created_at: Timestamp of when this row was first inserted.
        set: The Set object this card belongs to. Virtual attribute
            managed by SQLAlchemy.
        price_snapshots: The list of PriceSnapshot objects for this card,
            ordered from most recent to oldest. Virtual attribute.
    """

    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    set_id: Mapped[str] = mapped_column(Text, ForeignKey("sets.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    number: Mapped[str] = mapped_column(Text, nullable=False)
    rarity: Mapped[str | None] = mapped_column(Text, nullable=True)
    supertype: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    # Relationship back to the parent set.
    set: Mapped["Set"] = relationship("Set", back_populates="cards")  # noqa: F821

    # Relationship to price snapshots, ordered newest first.
    # The ordering is applied here so that any code that accesses
    # card.price_snapshots always gets them in a predictable order.
    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(
        "PriceSnapshot", back_populates="card", order_by="PriceSnapshot.captured_at.desc()"
    )


class PriceSnapshot(Base):
    """
    Represents a single price observation for a card at a point in time.

    A new row is inserted every time the ingestion script runs. Existing
    rows are never modified. This means the table grows over time and
    contains the full pricing history for every card.

    Attributes:
        id: Auto-incrementing integer primary key.
        card_id: The ID of the card this price belongs to. Foreign key
            linking to the cards table.
        source: Where the price data came from (e.g. "tcgplayer",
            "ebay"). Allows multiple price sources to coexist.
        condition: The card condition or finish this price applies to.
            One of "normal", "holofoil", or "reverseHolofoil".
        market_price: The market price in USD. Nullable because a price
            source may not always have market price data available.
        low_price: The lowest recent sale price in USD. Nullable.
        high_price: The highest recent sale price in USD. Nullable.
        captured_at: Timestamp of when this price was recorded.
        captured_date: Date component of captured_at. Used as the deduplication
            key so re-running the ingestion on the same day updates the existing
            row rather than inserting a duplicate.
        card: The Card object this snapshot belongs to. Virtual attribute.
    """

    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[str] = mapped_column(Text, ForeignKey("cards.id"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[str] = mapped_column(Text, nullable=False)
    variant: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    captured_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Relationship back to the parent card.
    card: Mapped["Card"] = relationship("Card", back_populates="price_snapshots")
