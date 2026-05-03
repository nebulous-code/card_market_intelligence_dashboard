"""
ORM model for the collection_sessions table.

A row holds one user's parsed collection plus its expiration. Reads and
writes are both done through the /collection/* endpoints; nothing else
in the codebase touches this table.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class CollectionSession(Base):
    """One uploaded collection scoped to a single browser session."""

    __tablename__ = "collection_sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    collection: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
