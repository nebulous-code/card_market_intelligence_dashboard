"""
Add set_identifiers table and seed Base Set mappings.

Creates the set_identifiers table that maps canonical set IDs to the names
and IDs used by each external data source (TCGdex, PokemonPriceTracker, etc.).
Also inserts seed rows for Base Set, which is already present in the database.

Revision ID: 005
Revises: 004
Create Date: 2025-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "set_identifiers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("set_id", sa.Text(), sa.ForeignKey("sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("identifier_type", sa.Text(), nullable=False, server_default="name"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("set_id", "source", "identifier_type", name="uq_set_identifiers_set_source_type"),
    )

    op.create_index("idx_set_identifiers_source", "set_identifiers", ["source"])
    op.create_index("idx_set_identifiers_identifier", "set_identifiers", ["identifier"])

    # Seed Base Set mappings. Only insert if base1 is already in the sets table
    # so the migration doesn't fail on a fresh database that hasn't been ingested yet.
    op.execute("""
        INSERT INTO set_identifiers (set_id, source, identifier, identifier_type)
        SELECT vals.set_id, vals.source, vals.identifier, vals.identifier_type
        FROM (VALUES
            ('base1', 'tcgdex', 'base1',    'id'),
            ('base1', 'tcgdex', 'Base Set', 'name'),
            ('base1', 'ppt',    'Base Set', 'name')
        ) AS vals(set_id, source, identifier, identifier_type)
        WHERE EXISTS (SELECT 1 FROM sets WHERE id = 'base1')
        ON CONFLICT (set_id, source, identifier_type) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("idx_set_identifiers_identifier", table_name="set_identifiers")
    op.drop_index("idx_set_identifiers_source", table_name="set_identifiers")
    op.drop_table("set_identifiers")
