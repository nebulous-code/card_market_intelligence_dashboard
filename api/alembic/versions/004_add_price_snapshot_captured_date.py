"""
Add captured_date to price_snapshots and deduplicate existing rows.

Adds a DATE column (captured_date) derived from the captured_at timestamp,
then adds a unique constraint on (card_id, source, condition, captured_date)
so that re-running the ingestion script on the same day updates the existing
row rather than inserting a duplicate.

The migration also cleans up any duplicate rows already in the database by
keeping only the most recently inserted row per (card_id, source, condition,
captured_date) group, identified dynamically by the highest id value.

Revision ID: 004
Revises: 003
Create Date: 2025-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add the captured_date column as nullable so existing rows
    # can be backfilled before the NOT NULL constraint is applied.
    op.add_column(
        "price_snapshots",
        sa.Column("captured_date", sa.Date(), nullable=True),
    )

    # Step 2: Backfill captured_date from the date component of captured_at
    # for all existing rows.
    op.execute("UPDATE price_snapshots SET captured_date = captured_at::date")

    # Step 3: Now that all rows have a value, tighten the column to NOT NULL.
    op.alter_column("price_snapshots", "captured_date", nullable=False)

    # Step 4: Delete duplicate rows, keeping only the most recently inserted
    # row per (card_id, source, condition, captured_date) group. The highest
    # id value is used as the tiebreaker because id is auto-incrementing --
    # the highest id in a group is always the most recent insert.
    op.execute("""
        DELETE FROM price_snapshots
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM price_snapshots
            GROUP BY card_id, source, condition, captured_date
        )
    """)

    # Step 5: Add the unique constraint. This will succeed because duplicates
    # have just been removed in the previous step.
    op.create_unique_constraint(
        "uq_price_snapshot_card_source_condition_date",
        "price_snapshots",
        ["card_id", "source", "condition", "captured_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_price_snapshot_card_source_condition_date",
        "price_snapshots",
        type_="unique",
    )
    op.drop_column("price_snapshots", "captured_date")
