"""
Response schemas for the /trends/* endpoints.

The shape mirrors the spec for the heatmap consumer: each grouping bundles
all its forward transitions, and every transition carries the underlying
data_points count so the UI can render confidence indicators if it wants.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class TransitionResponse(BaseModel):
    """One forward condition-pair multiplier within a grouping."""

    from_condition: str
    to_condition: str
    multiplier: Decimal
    data_points: int

    model_config = {"from_attributes": True}


class GroupingResponse(BaseModel):
    """All transitions for a single (rarity OR supertype) grouping value."""

    grouping_value: str
    grouping_label: str
    transitions: list[TransitionResponse]


class ConditionMultiplierResponse(BaseModel):
    """Top-level response for /trends/condition-multipliers."""

    set_id: str
    set_display_name: str
    grouping_type: str
    last_refreshed: datetime | None
    groupings: list[GroupingResponse]


class SetWithMultipliersEntry(BaseModel):
    """One entry in the /trends/sets-with-multipliers response."""

    set_id: str
    set_display_name: str


class SetsWithMultipliersResponse(BaseModel):
    """List of sets that have at least one row in condition_multipliers."""

    sets: list[SetWithMultipliersEntry]
