"""
Add canonical_rarities and rarity_aliases.

Mirrors migration 008 (canonical_conditions / canonical_variants). The cards
table currently stores rarity as the raw TCGdex string ("Hyper rare",
"Double rare", "Common", ...). That works for display but blocks anything
that needs a stable ordering -- the Set Detail box-and-whisker chart wants
to sort columns rarest -> most common, and the dashboard wants a single
canonical key per rarity rather than relying on the loader-imported casing.

The migration:
  1. Creates canonical_rarities (snake_case canonical value + display label
     + display_order) and rarity_aliases (raw_value -> canonical_value).
  2. Seeds canonical_rarities with 8 values spaced 10 / 50 / 100 / 200 /
     300 / 500 / 700 / 900 (rarest first). "Rare Holo" is intentionally
     skipped: TCGdex marks classic-era holos as plain "Rare" -- the holo
     printing is captured by price_snapshots.variant, not cards.rarity.
  3. Seeds rarity_aliases for every TCGdex string currently present in the
     database so the in-place UPDATE below has a target for every row.
  4. Rewrites cards.rarity in place using the alias lookup (idempotent --
     a row already storing the canonical value resolves through the
     identity-style alias seeded in step 3 too).
  5. Adds an FK on cards.rarity -> canonical_rarities.value so a future
     loader change cannot reintroduce a raw string. Stays nullable so the
     loader can still upsert cards whose rarity field is missing from
     TCGdex (FK MATCH SIMPLE skips the check on NULL).

Revision ID: 009
Revises: 008
Create Date: 2026-05-02 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- canonical_rarities ----------

    op.create_table(
        "canonical_rarities",
        sa.Column("value", sa.Text(), primary_key=True),
        sa.Column("display_label", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ---------- rarity_aliases ----------

    op.create_table(
        "rarity_aliases",
        sa.Column("raw_value", sa.Text(), primary_key=True),
        sa.Column(
            "canonical_value",
            sa.Text(),
            sa.ForeignKey("canonical_rarities.value", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ---------- seed canonical_rarities ----------
    #
    # display_order is rarest-first with gaps so a future rarity tier (Crown
    # Zenith / Trainer Gallery / etc.) can wedge in without renumbering.

    op.execute("""
        INSERT INTO canonical_rarities (value, display_label, display_order) VALUES
            ('hyper_rare',                'Hyper Rare',                 10),
            ('special_illustration_rare', 'Special Illustration Rare',  50),
            ('illustration_rare',         'Illustration Rare',         100),
            ('ultra_rare',                'Ultra Rare',                200),
            ('double_rare',               'Double Rare',               300),
            ('rare',                      'Rare',                      500),
            ('uncommon',                  'Uncommon',                  700),
            ('common',                    'Common',                    900)
        ON CONFLICT (value) DO NOTHING
    """)

    # ---------- seed rarity_aliases ----------
    #
    # The raw TCGdex strings currently in cards.rarity (verified 2026-05-02
    # against dev). Includes both the casing TCGdex uses today and a
    # snake_case identity alias so a future re-ingest can submit either form
    # without breaking.

    op.execute("""
        INSERT INTO rarity_aliases (raw_value, canonical_value) VALUES
            ('Hyper rare',                'hyper_rare'),
            ('Special illustration rare', 'special_illustration_rare'),
            ('Illustration rare',         'illustration_rare'),
            ('Ultra Rare',                'ultra_rare'),
            ('Double rare',               'double_rare'),
            ('Rare',                      'rare'),
            ('Uncommon',                  'uncommon'),
            ('Common',                    'common'),
            ('hyper_rare',                'hyper_rare'),
            ('special_illustration_rare', 'special_illustration_rare'),
            ('illustration_rare',         'illustration_rare'),
            ('ultra_rare',                'ultra_rare'),
            ('double_rare',               'double_rare'),
            ('rare',                      'rare'),
            ('uncommon',                  'uncommon'),
            ('common',                    'common')
        ON CONFLICT (raw_value) DO NOTHING
    """)

    # ---------- rewrite cards.rarity to canonical ----------
    #
    # Every existing rarity string must resolve through the alias map before
    # the FK is created. Anything that does not resolve is left as-is and
    # the FK creation will fail loudly -- that is the desired behavior:
    # the migration should not silently drop unrecognized rarities.

    op.execute("""
        UPDATE cards
        SET rarity = ra.canonical_value
        FROM rarity_aliases ra
        WHERE cards.rarity = ra.raw_value
          AND cards.rarity IS NOT NULL
    """)

    # ---------- foreign key on cards.rarity ----------
    #
    # MATCH SIMPLE (PG default) skips the FK check when rarity IS NULL,
    # so cards with no printed rarity remain valid.

    op.create_foreign_key(
        "fk_cards_rarity",
        "cards",
        "canonical_rarities",
        ["rarity"],
        ["value"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_cards_rarity", "cards", type_="foreignkey")
    # Reverse the canonical -> raw rewrite using a representative display label
    # so a downgraded DB stays human-readable (the alias table is gone, so we
    # can't reverse-lookup the original casing).
    op.execute("""
        UPDATE cards c
        SET rarity = cr.display_label
        FROM canonical_rarities cr
        WHERE c.rarity = cr.value
    """)
    op.drop_table("rarity_aliases")
    op.drop_table("canonical_rarities")
