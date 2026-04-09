"""SQLAlchemy models for the `cards` and `price_snapshots` tables."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    set_id: Mapped[str] = mapped_column(Text, ForeignKey("sets.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    number: Mapped[str] = mapped_column(Text, nullable=False)
    rarity: Mapped[str | None] = mapped_column(Text, nullable=True)
    supertype: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    set: Mapped["Set"] = relationship("Set", back_populates="cards")  # noqa: F821
    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(
        "PriceSnapshot", back_populates="card", order_by="PriceSnapshot.captured_at.desc()"
    )


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[str] = mapped_column(Text, ForeignKey("cards.id"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[str] = mapped_column(Text, nullable=False)
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    card: Mapped["Card"] = relationship("Card", back_populates="price_snapshots")
