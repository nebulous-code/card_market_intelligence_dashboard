"""
Add ingestion_watermarks table.

Tracks per-set ingestion state for each pricing source. Allows the nightly
ingestion script to resume where it left off if interrupted by a rate limit
or other error, and to record whether the one-time historical backfill has
been completed for each set on the API tier.

Revision ID: 002
Revises: 001
Create Date: 2025-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create the ingestion_watermarks table.

    The (source, set_id) pair is given a unique constraint so the application
    can safely upsert watermark rows without creating duplicates.
    """
    op.create_table(
        "ingestion_watermarks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("set_id", sa.Text(), nullable=False),
        # Nullable because the row may be created before the first successful run.
        sa.Column("last_ingested_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("backfilled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["set_id"], ["sets.id"]),
        sa.PrimaryKeyConstraint("id"),
        # Ensures one watermark row per source per set.
        sa.UniqueConstraint("source", "set_id", name="uq_watermark_source_set"),
    )


def downgrade() -> None:
    """Remove the ingestion_watermarks table."""
    op.drop_table("ingestion_watermarks")
