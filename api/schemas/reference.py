"""
Pydantic schemas for the /reference endpoints.

The reference endpoints expose the canonical condition/variant values plus
their display labels. The frontend uses them to populate filter dropdowns
without having to hardcode label translations.
"""

from pydantic import BaseModel


class CanonicalValueResponse(BaseModel):
    """
    One row from canonical_conditions or canonical_variants.

    Attributes:
        value: The canonical value stored in price_snapshots
            (e.g. "NM", "holofoil"). Null is the legitimate "Standard"
            variant for cards with no printing distinction.
        label: The human-readable label for UI display.
        display_order: Sort key for dropdowns.
    """

    value: str | None
    label: str
    display_order: int

    model_config = {"from_attributes": True}
