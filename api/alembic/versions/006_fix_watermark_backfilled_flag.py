"""
Fix incorrectly set backfilled flags on interrupted ingestion runs.

A bug in run.py wrote backfilled=true to the watermark even when a set's
ingestion was interrupted mid-pagination (last_offset > 0). On the next
resume, the history flag was already True so the remaining cards were fetched
without history, leaving gaps in the price_snapshots table.

This migration resets backfilled=false for any watermark row where
last_offset > 0, so the next ingestion run will re-request history for
the cards that were not yet fetched when the run was interrupted.

Rows where last_offset=0 (fully completed sets) are left untouched — their
backfill was genuine and does not need to be repeated.

Revision ID: 006
Revises: 005
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reset backfilled=false only for rows that were interrupted (last_offset > 0).
    # These sets never finished their history fetch, so the flag was set in error.
    op.execute("""
        UPDATE ingestion_watermarks
        SET backfilled = false
        WHERE last_offset > 0
          AND backfilled = true
    """)


def downgrade() -> None:
    # There is no safe way to reverse this — we cannot know which rows were
    # incorrectly set vs correctly set before this migration ran.
    pass
