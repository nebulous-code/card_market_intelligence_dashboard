"""
Add last_offset column to ingestion_watermarks.

Tracks pagination progress within a set so that a run interrupted by a
daily credit limit can resume from where it left off rather than starting
from card 1 again. When a run completes the full set, last_offset is reset
to 0 so the next day's run starts fresh.

Revision ID: 003
Revises: 002
Create Date: 2025-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ingestion_watermarks",
        sa.Column("last_offset", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("ingestion_watermarks", "last_offset")
