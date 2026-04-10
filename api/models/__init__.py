"""
Models package init.

Imports all models so that importing this package in alembic/env.py is
sufficient to register all three tables on Base.metadata. Without these
imports Alembic would not know about the models and could not generate
or apply migrations correctly.
"""

from models.card import Card, PriceSnapshot
from models.set import Set

__all__ = ["Set", "Card", "PriceSnapshot"]
