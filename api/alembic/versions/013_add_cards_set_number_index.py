"""
Add a composite index on cards (set_id, number).

The cards table carried no index beyond its primary key on id, and
Postgres does not index a foreign key column automatically -- so every
query filtering on set_id was a sequential scan. That is invisible at a
few hundred cards and becomes real work as sets are ingested.

Six production queries filter on set_id: the ingestion loader's per-set
prefetch, three endpoints in routers/sets.py, and two in the multiplier
refresh. The leading column of this index serves all of them. The set
detail endpoint filters set_id and orders by number, which the pair
serves exactly.

The collection validator resolves an uploaded row to a card on
(set_id, number) together, which is the pair this index is named for.

Deliberately NOT unique. The pair is unique in the data today, but
ingestion runs unattended nightly against an upstream API, and a unique
constraint would turn a single duplicate from TCGdex into a hard ingest
failure rather than a stray row. Lookups gain nothing from uniqueness.

Revision ID: 013
Revises: 012
Create Date: 2026-08-06 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_cards_set_number",
        "cards",
        ["set_id", "number"],
    )


def downgrade() -> None:
    op.drop_index("idx_cards_set_number", table_name="cards")
