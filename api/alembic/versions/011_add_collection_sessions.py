"""
Add collection_sessions table.

Stores parsed user collections uploaded via the /collection/upload flow.
Each session is keyed by a UUID written to an HttpOnly cookie; the
collection itself lives in a JSONB blob because the access pattern is
"load my entire collection in one read" -- a normalized child table
would add complexity without enabling any required workflow. Sessions
expire 24 hours after creation and a nightly cleanup job sweeps any
rows past expires_at.

Revision ID: 011
Revises: 010
Create Date: 2026-05-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collection_sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("collection", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
    )
    op.create_index(
        "idx_collection_sessions_expires",
        "collection_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_collection_sessions_expires", table_name="collection_sessions"
    )
    op.drop_table("collection_sessions")
