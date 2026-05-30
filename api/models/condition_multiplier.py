"""
ORM model for the condition_multipliers table.

The table is rebuilt nightly by ingestion/refresh_multipliers.py from the
last 6 months of price_snapshots data. The API layer only ever reads from
this table -- writes are exclusively done by the refresh script -- so the
model has no relationship attributes back to Set or Card.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ConditionMultiplier(Base):
    """One pairwise condition-ratio observation for a (set, grouping) bucket.

    `grouping_type` is either ``"rarity"`` or ``"supertype"`` and selects
    which `cards.*` column the `grouping_value` was bucketed by during
    refresh. The same (from_condition, to_condition) pair appears once per
    grouping_value per grouping_type, so a typical set has 10 transitions
    times (rarities + supertypes) rows.
    """

    __tablename__ = "condition_multipliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sets.id", ondelete="CASCADE"), nullable=False
    )
    grouping_type: Mapped[str] = mapped_column(Text, nullable=False)
    grouping_value: Mapped[str] = mapped_column(Text, nullable=False)
    from_condition: Mapped[str] = mapped_column(Text, nullable=False)
    to_condition: Mapped[str] = mapped_column(Text, nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    data_points: Mapped[int] = mapped_column(Integer, nullable=False)
    last_refreshed: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
