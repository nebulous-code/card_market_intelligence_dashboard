"""
Models package init.

Imports all models so that importing this package in alembic/env.py is
sufficient to register all four tables on Base.metadata. Without these
imports Alembic would not know about the models and could not generate
or apply migrations correctly.
"""

from models.canonical import (
    CanonicalCondition,
    CanonicalRarity,
    CanonicalVariant,
    ConditionAlias,
    RarityAlias,
    VariantAlias,
)
from models.card import Card, PriceSnapshot
from models.collection_session import CollectionSession
from models.condition_multiplier import ConditionMultiplier
from models.palette_color import PaletteColor
from models.set import Set
from models.set_identifier import SetIdentifier
from models.watermark import IngestionWatermark

__all__ = [
    "Set",
    "Card",
    "PriceSnapshot",
    "IngestionWatermark",
    "SetIdentifier",
    "CanonicalCondition",
    "CanonicalRarity",
    "CanonicalVariant",
    "ConditionAlias",
    "ConditionMultiplier",
    "CollectionSession",
    "PaletteColor",
    "RarityAlias",
    "VariantAlias",
]
