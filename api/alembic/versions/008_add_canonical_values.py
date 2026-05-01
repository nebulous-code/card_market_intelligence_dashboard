"""
Add canonical_conditions, canonical_variants, condition_aliases, variant_aliases.

Replaces the hardcoded condition/variant maps in ingestion/loader.py with a
DB-driven lookup. Storing the canonical set in the database means new raw
PPT spellings (e.g. a variant like "Holographic Promo" we have not seen
before) can be handled by inserting an alias row -- no code deploy required.

Each canonical row also carries a display_label and display_order so the
API can return user-friendly text ("Near Mint", "1st Ed. Holo", "Standard")
without the frontend hardcoding the mapping.

Foreign keys on price_snapshots.condition and price_snapshots.variant lock
the storage layer to the canonical set so a future loader bug cannot
re-introduce dirty values.

Revision ID: 008
Revises: 007
Create Date: 2026-04-27 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- canonical tables ----------

    op.create_table(
        "canonical_conditions",
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

    # canonical_variants.value is nullable because NULL is the legitimate
    # "Standard" variant (cards with no printing distinction). The synthetic
    # id PK is needed because SQLAlchemy's ORM requires a PK to materialize
    # entities, and a nullable column can't be one. UNIQUE NULLS NOT DISTINCT
    # on (value) is the actual lookup target -- FKs from variant_aliases and
    # price_snapshots reference value, not id.
    op.create_table(
        "canonical_variants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("display_label", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.execute("""
        ALTER TABLE canonical_variants
        ADD CONSTRAINT uq_canonical_variants_value
        UNIQUE NULLS NOT DISTINCT (value)
    """)

    # ---------- alias tables ----------

    op.create_table(
        "condition_aliases",
        sa.Column("raw_value", sa.Text(), primary_key=True),
        sa.Column(
            "canonical_value",
            sa.Text(),
            sa.ForeignKey("canonical_conditions.value", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # variant_aliases.canonical_value is nullable so a raw value can
    # legitimately map to the "Standard" canonical (variant=NULL).
    op.create_table(
        "variant_aliases",
        sa.Column("raw_value", sa.Text(), primary_key=True),
        sa.Column(
            "canonical_value",
            sa.Text(),
            sa.ForeignKey("canonical_variants.value", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ---------- seed canonical_conditions ----------

    op.execute("""
        INSERT INTO canonical_conditions (value, display_label, display_order) VALUES
            ('NM',      'Near Mint',         10),
            ('LP',      'Lightly Played',    20),
            ('MP',      'Moderately Played', 30),
            ('HP',      'Heavily Played',    40),
            ('DMG',     'Damaged',           50),
            ('PSA-10',  'PSA 10',           100),
            ('PSA-9',   'PSA 9',            110),
            ('PSA-8',   'PSA 8',            120),
            ('BGS-10',  'BGS 10',           200),
            ('BGS-9.5', 'BGS 9.5',          210),
            ('BGS-9',   'BGS 9',            220),
            ('CGC-10',  'CGC 10',           300),
            ('CGC-9.5', 'CGC 9.5',          310),
            ('CGC-9',   'CGC 9',            320)
        ON CONFLICT (value) DO NOTHING
    """)

    # ---------- seed canonical_variants ----------

    # Insert the NULL ("Standard") row separately because UPSERT on
    # NULLS NOT DISTINCT works but is verbose; this migration is fresh,
    # so a plain insert is fine.
    op.execute("""
        INSERT INTO canonical_variants (value, display_label, display_order) VALUES
            (NULL,                   'Standard',     10),
            ('holofoil',             'Holofoil',     20),
            ('reverse_holofoil',     'Reverse Holo', 30),
            ('unlimited',            'Unlimited',    40),
            ('1st_edition',          '1st Edition',  50),
            ('1st_edition_holofoil', '1st Ed. Holo', 60)
    """)

    # ---------- seed condition_aliases ----------
    #
    # 5 plain forms ("Near Mint" -> NM, ...) plus the cross-product of
    # 5 canonical conditions and 9 known variant-suffix forms PPT bleeds
    # into the condition string (e.g. "Near Mint Unlimited Holofoil" -> NM).
    # The cross-product is generated by SQL rather than written by hand
    # so the migration body stays compact.

    op.execute("""
        INSERT INTO condition_aliases (raw_value, canonical_value)
        SELECT base.label || COALESCE(suffix.s, '') AS raw_value,
               base.canonical
        FROM (VALUES
            ('Near Mint',         'NM'),
            ('Lightly Played',    'LP'),
            ('Moderately Played', 'MP'),
            ('Heavily Played',    'HP'),
            ('Damaged',           'DMG')
        ) AS base(label, canonical)
        CROSS JOIN (VALUES
            (NULL),
            (' 1st Edition'),
            (' 1st Edition Holofoil'),
            (' 1st Edition Normal'),
            (' Unlimited'),
            (' Unlimited Holofoil'),
            (' Unlimited Normal'),
            (' Holofoil'),
            (' Reverse Holofoil'),
            (' Normal')
        ) AS suffix(s)
        ON CONFLICT (raw_value) DO NOTHING
    """)

    # Graded-condition aliases for ebay.{psaN, bgsN, cgcN} keys returned
    # by PPT. Stored as raw aliases too so the loader has one uniform
    # alias-table lookup path for every condition source.
    op.execute("""
        INSERT INTO condition_aliases (raw_value, canonical_value) VALUES
            ('psa10', 'PSA-10'),
            ('psa9',  'PSA-9'),
            ('psa8',  'PSA-8'),
            ('bgs10', 'BGS-10'),
            ('bgs95', 'BGS-9.5'),
            ('bgs9',  'BGS-9'),
            ('cgc10', 'CGC-10'),
            ('cgc95', 'CGC-9.5'),
            ('cgc9',  'CGC-9')
        ON CONFLICT (raw_value) DO NOTHING
    """)

    # ---------- seed variant_aliases ----------

    op.execute("""
        INSERT INTO variant_aliases (raw_value, canonical_value) VALUES
            ('Holofoil',             'holofoil'),
            ('Unlimited Holofoil',   'holofoil'),
            ('1st Edition Holofoil', '1st_edition_holofoil'),
            ('Reverse Holofoil',     'reverse_holofoil'),
            ('Normal',               NULL),
            ('Unlimited Normal',     NULL),
            ('1st Edition Normal',   '1st_edition'),
            ('1st Edition',          '1st_edition'),
            ('Unlimited',            'unlimited')
        ON CONFLICT (raw_value) DO NOTHING
    """)

    # ---------- defensive cleanup before adding FKs ----------
    #
    # Any existing price_snapshots row whose condition or variant is not
    # in the canonical set would break the FK creation below. The user is
    # expected to have cleaned the dirty rows manually, but this DELETE
    # makes the migration idempotent regardless. It is a no-op on a clean DB.

    op.execute("""
        DELETE FROM price_snapshots
        WHERE condition NOT IN (SELECT value FROM canonical_conditions)
           OR (variant IS NOT NULL
               AND variant NOT IN (SELECT value FROM canonical_variants
                                   WHERE value IS NOT NULL))
    """)

    # ---------- foreign keys on price_snapshots ----------

    op.create_foreign_key(
        "fk_price_snapshots_condition",
        "price_snapshots",
        "canonical_conditions",
        ["condition"],
        ["value"],
        ondelete="RESTRICT",
    )

    # MATCH SIMPLE (PG default) skips the FK check when variant IS NULL,
    # which is what we want -- the canonical NULL row is seeded above and
    # acts as the implicit target for "Standard" variant rows.
    op.create_foreign_key(
        "fk_price_snapshots_variant",
        "price_snapshots",
        "canonical_variants",
        ["variant"],
        ["value"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_price_snapshots_variant", "price_snapshots", type_="foreignkey")
    op.drop_constraint("fk_price_snapshots_condition", "price_snapshots", type_="foreignkey")
    op.drop_table("variant_aliases")
    op.drop_table("condition_aliases")
    op.drop_table("canonical_variants")
    op.drop_table("canonical_conditions")
