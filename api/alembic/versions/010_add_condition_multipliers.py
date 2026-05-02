"""
Add condition_multipliers table.

Stores the per-set, per-grouping average price ratios between conditions
along the condition ladder (NM, LP, MP, HP, DMG). The table is rebuilt
nightly by ingestion/refresh_multipliers.py from the most recent 6 months
of price_snapshots data and consumed by the Market Trends heatmap as well
as the Excel collection workbook (later in M04).

One row per (set_id, grouping_type, grouping_value, from_condition,
to_condition) combination -- only the 10 forward transitions on the
ladder are stored (NM->LP/MP/HP/DMG, LP->MP/HP/DMG, MP->HP/DMG, HP->DMG).
The unique constraint catches any duplicate writes from a misbehaving
refresh.

Revision ID: 010
Revises: 009
Create Date: 2026-05-02 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "condition_multipliers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "set_id",
            sa.Text(),
            sa.ForeignKey("sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 'rarity' or 'supertype' -- indicates which cards.* column the
        # grouping_value comes from. The refresh script writes one row per
        # grouping per transition, doubling the row count vs a single
        # grouping but keeping queries dead simple ("WHERE grouping_type =
        # 'rarity'") rather than UNION-ing two structures.
        sa.Column("grouping_type", sa.Text(), nullable=False),
        sa.Column("grouping_value", sa.Text(), nullable=False),
        sa.Column("from_condition", sa.Text(), nullable=False),
        sa.Column("to_condition", sa.Text(), nullable=False),
        # NUMERIC(6,4) -- max 99.9999. The "expected" range is 0.0-1.0 but
        # noisy low-value commons can produce ratios >1 (a single $1 listing
        # of an HP common against a $0.50 NM avg yields HP/NM = 2.0). The
        # extra digit lets us store these outliers so the data is visible
        # rather than rejected; a future story can add outlier trimming
        # (winsorisation, minimum-price floor, etc.) if those values prove
        # too noisy to be useful.
        sa.Column("multiplier", sa.Numeric(6, 4), nullable=False),
        sa.Column("data_points", sa.Integer(), nullable=False),
        sa.Column(
            "last_refreshed",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "set_id",
            "grouping_type",
            "grouping_value",
            "from_condition",
            "to_condition",
            name="uq_condition_multipliers_lookup",
        ),
    )

    op.create_index(
        "idx_condition_multipliers_set",
        "condition_multipliers",
        ["set_id"],
    )
    op.create_index(
        "idx_condition_multipliers_lookup",
        "condition_multipliers",
        ["set_id", "grouping_type", "grouping_value"],
    )


def downgrade() -> None:
    op.drop_index("idx_condition_multipliers_lookup", table_name="condition_multipliers")
    op.drop_index("idx_condition_multipliers_set", table_name="condition_multipliers")
    op.drop_table("condition_multipliers")
