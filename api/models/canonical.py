"""
Database models for canonical conditions/variants and their raw-value aliases.

The four tables in this module form the source of truth for:
  - which condition/variant values are allowed in price_snapshots
  - what display label each canonical value should show in the UI
  - which raw strings PPT (or any future source) maps onto each canonical

The ingestion loader reads the alias tables at the start of every run; the
API exposes the canonical tables via /reference/conditions and /reference/variants.
Adding a new raw spelling is an INSERT into the alias table -- no code deploy.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class CanonicalCondition(Base):
    """A canonical condition value plus its display metadata."""

    __tablename__ = "canonical_conditions"

    value: Mapped[str] = mapped_column(Text, primary_key=True)
    display_label: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    aliases: Mapped[list["ConditionAlias"]] = relationship(
        "ConditionAlias", back_populates="canonical"
    )


class CanonicalVariant(Base):
    """
    A canonical variant value plus its display metadata.

    `value` is nullable: NULL is the legitimate "Standard" variant for cards
    with no printing distinction. The unique constraint uses NULLS NOT DISTINCT
    so only one such row can exist. A synthetic integer PK is required because
    SQLAlchemy's ORM cannot use a nullable column as a primary key.
    """

    __tablename__ = "canonical_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_label: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    aliases: Mapped[list["VariantAlias"]] = relationship(
        "VariantAlias", back_populates="canonical"
    )


class ConditionAlias(Base):
    """Maps a raw PPT condition string to a canonical condition value."""

    __tablename__ = "condition_aliases"

    raw_value: Mapped[str] = mapped_column(Text, primary_key=True)
    canonical_value: Mapped[str] = mapped_column(
        Text, ForeignKey("canonical_conditions.value", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    canonical: Mapped["CanonicalCondition"] = relationship(
        "CanonicalCondition", back_populates="aliases"
    )


class VariantAlias(Base):
    """
    Maps a raw PPT variant string to a canonical variant value.

    canonical_value is nullable so a raw alias can legitimately point at the
    Standard (NULL) canonical row.
    """

    __tablename__ = "variant_aliases"

    raw_value: Mapped[str] = mapped_column(Text, primary_key=True)
    canonical_value: Mapped[str | None] = mapped_column(
        Text, ForeignKey("canonical_variants.value", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    canonical: Mapped["CanonicalVariant | None"] = relationship(
        "CanonicalVariant", back_populates="aliases"
    )


class CanonicalRarity(Base):
    """A canonical rarity value plus its display metadata.

    display_order is rarest-first (lower number = rarer) so a single ORDER BY
    on the column drives the box-and-whisker chart's rarest-on-the-left layout.
    """

    __tablename__ = "canonical_rarities"

    value: Mapped[str] = mapped_column(Text, primary_key=True)
    display_label: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    aliases: Mapped[list["RarityAlias"]] = relationship(
        "RarityAlias", back_populates="canonical"
    )


class RarityAlias(Base):
    """Maps a raw TCGdex rarity string to a canonical rarity value."""

    __tablename__ = "rarity_aliases"

    raw_value: Mapped[str] = mapped_column(Text, primary_key=True)
    canonical_value: Mapped[str] = mapped_column(
        Text, ForeignKey("canonical_rarities.value", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    canonical: Mapped["CanonicalRarity"] = relationship(
        "CanonicalRarity", back_populates="aliases"
    )
