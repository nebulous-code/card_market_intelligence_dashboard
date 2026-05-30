"""
Add palette_colors table.

The Collection Dashboard assigns a stable color to each set across all
charts (pie, treemap, etc.). Storing the palette in the database means
the user can add or replace entries via SQL without redeploying. The
frontend cycles through the list when there are more sets than colors.

Revision ID: 012
Revises: 011
Create Date: 2026-05-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_COLORS = (
    ("#E8412A", 1),  # Magikarp red (primary)
    ("#F5C842", 2),  # Magikarp gold (secondary)
    ("#A0A0B8", 3),  # Muted grey-blue
    ("#1E1E30", 4),  # Surface navy (only useful as outline contrast)
    ("#4CAF82", 5),  # Success green
    ("#FFA726", 6),  # Warning amber
    ("#CF6679", 7),  # Error red
    ("#F5EDD6", 8),  # Cream
)


def upgrade() -> None:
    op.create_table(
        "palette_colors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("color_hex", sa.Text(), nullable=False),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            unique=True,
        ),
    )
    for color_hex, display_order in SEED_COLORS:
        op.execute(
            sa.text(
                "INSERT INTO palette_colors (color_hex, display_order) "
                "VALUES (:color_hex, :display_order)"
            ).bindparams(color_hex=color_hex, display_order=display_order)
        )


def downgrade() -> None:
    op.drop_table("palette_colors")
