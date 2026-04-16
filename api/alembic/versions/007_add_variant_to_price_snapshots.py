"""
Add variant column to price_snapshots and update unique constraint.

PPT returns per-variant pricing (e.g. Holofoil vs 1st Edition Holofoil) in
the priceHistory.variants structure. The variant column stores which printing
the price applies to (e.g. "holofoil", "1st_edition_holofoil"). NULL means the
snapshot predates this migration or comes from a source that doesn't distinguish
printings.

The old unique constraint covered (card_id, source, condition, captured_date).
With variant added, that constraint would incorrectly block inserting two rows
for the same card/date with different variants. This migration drops the old
constraint and replaces it with one that includes variant.

Existing NULL-variant rows are preserved. After this migration, new ingestion
runs will write rows with variant set, and the two sets coexist because NULL
is treated as distinct from any non-NULL value in a unique constraint.

Revision ID: 007
Revises: 006
Create Date: 2026-04-16 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add the variant column as nullable. NULL means "no variant
    # distinction" — either old rows from before this migration, or cards
    # from sources that don't break down pricing by printing.
    op.add_column(
        "price_snapshots",
        sa.Column("variant", sa.Text(), nullable=True),
    )

    # Step 2: Drop the old unique constraint that did not include variant.
    op.drop_constraint(
        "uq_price_snapshot_card_source_condition_date",
        "price_snapshots",
        type_="unique",
    )

    # Step 3: Add the new unique constraint that includes variant.
    # NULLS NOT DISTINCT ensures two NULL-variant rows for the same
    # (card, source, condition, date) still conflict — preserving
    # idempotency for old-style single-NM rows.
    op.execute("""
        ALTER TABLE price_snapshots
        ADD CONSTRAINT uq_price_snapshot_card_source_condition_variant_date
        UNIQUE NULLS NOT DISTINCT (card_id, source, condition, variant, captured_date)
    """)


def downgrade() -> None:
    op.drop_constraint(
        "uq_price_snapshot_card_source_condition_variant_date",
        "price_snapshots",
        type_="unique",
    )

    # Restore the original constraint. Re-running on a database that had
    # variant rows with the same (card, source, condition, date) but different
    # variants could fail — acceptable since downgrade is a last resort.
    op.create_unique_constraint(
        "uq_price_snapshot_card_source_condition_date",
        "price_snapshots",
        ["card_id", "source", "condition", "captured_date"],
    )

    op.drop_column("price_snapshots", "variant")
