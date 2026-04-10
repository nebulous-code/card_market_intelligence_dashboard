"""
Initial database schema: sets, cards, price_snapshots.

This is the first and only migration for Milestone 1. It creates the three
tables that the application needs. Every subsequent time the API starts, the
migration runner checks whether this migration has been applied and skips it
if it has. It only runs once per database.

Revision ID: 001
Revises: (none -- this is the first migration)
Create Date: 2024-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Alembic uses these identifiers to track which migrations have been applied
# and in what order. revision is this migration's ID, down_revision is the
# ID of the migration that must be applied before this one (None here because
# this is the first migration).
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create all three tables in the database.

    This function is called when migrating forward (applying the migration).
    Tables must be created in dependency order: sets first, then cards
    (which references sets), then price_snapshots (which references cards).
    """

    # The sets table stores information about each Pokemon card set release,
    # such as Base Set or Jungle. The id column uses the TCGdex identifier
    # (e.g. "base1") as the primary key rather than an auto-increment number.
    op.create_table(
        "sets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("series", sa.Text(), nullable=False),
        sa.Column("printed_total", sa.Integer(), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("symbol_url", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.Text(), nullable=True),
        # server_default means the database itself sets this value on insert
        # rather than the application code, which guarantees accuracy.
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # The cards table stores individual Pokemon cards. Each card belongs to
    # one set via the set_id foreign key. The number column is text rather
    # than integer because some sets use codes like "SV001" for card numbers.
    op.create_table(
        "cards",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("set_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("rarity", sa.Text(), nullable=True),
        sa.Column("supertype", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        # Foreign key ensures every card references a valid set.
        sa.ForeignKeyConstraint(["set_id"], ["sets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # The price_snapshots table records what a card was selling for at a
    # specific point in time. Rows are only ever inserted, never updated.
    # This preserves the full pricing history for trend analysis.
    # The id column uses SERIAL (auto-increment) because there is no natural
    # unique identifier for a price observation.
    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("card_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("market_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("low_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("high_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("captured_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """
    Remove all three tables from the database.

    This function is called when rolling back this migration. Tables must
    be dropped in reverse dependency order to satisfy foreign key constraints:
    price_snapshots first (depends on cards), then cards (depends on sets),
    then sets.
    """
    op.drop_table("price_snapshots")
    op.drop_table("cards")
    op.drop_table("sets")
