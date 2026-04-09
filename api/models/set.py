"""SQLAlchemy model for the `sets` table."""

from datetime import datetime

from sqlalchemy import Date, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Set(Base):
    __tablename__ = "sets"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    series: Mapped[str] = mapped_column(Text, nullable=False)
    printed_total: Mapped[int] = mapped_column(Integer, nullable=False)
    release_date: Mapped[datetime] = mapped_column(Date, nullable=True)
    symbol_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now(), nullable=False)

    cards: Mapped[list["Card"]] = relationship("Card", back_populates="set")  # noqa: F821
