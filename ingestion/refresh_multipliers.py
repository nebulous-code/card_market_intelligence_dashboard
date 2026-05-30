"""
Recompute the condition_multipliers table from current price_snapshots data.

The output of this module powers two downstream consumers:
  - the Market Trends "Condition Multipliers" heatmap on the frontend
  - the Excel collection workbook in M04_S04, which uses these ratios as
    the inferential fallback for cards a user owns whose specific
    condition has sparse pricing data

Algorithm (per set, run twice -- once grouped by rarity, once by supertype):

  1. Pull all `price_snapshots` rows from the last 6 months for cards in
     this set, restricted to source=tcgplayer, variant IS NULL, with a
     non-null market_price. Variants and graded copies are excluded
     because their condition-to-price relationship doesn't follow the
     same curve as raw cards.

  2. Aggregate to a monthly average per (card_id, condition). This
     smooths daily volatility without an arbitrary minimum-observations
     threshold -- a card with one snapshot in March still contributes
     one March data point.

  3. For each (card_id, month) compute the 10 forward pairwise ratios
     along the condition ladder (NM->LP, NM->MP, ..., HP->DMG).

  4. Group by (rarity OR supertype, from_condition, to_condition) and
     average the ratios. Count of card-month observations becomes
     `data_points`.

  5. Replace the rows for this set in `condition_multipliers` --
     delete-then-insert in a single transaction so a partial failure
     leaves the previous data intact for that set.

The function deliberately works set-by-set so a problem with one set's
data (e.g. all NM prices pulled at $0 by an upstream bug) doesn't wipe
the good data for every other set.
"""

import logging
import os
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


# Lazy module-level engine -- created on first use so importing the module
# during tests doesn't require DATABASE_URL to be set yet. Reset by the test
# fixtures via monkeypatch where needed.
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    return _engine


# Variants treated as "non-variant" for the purpose of this analysis.
# NULL is the modern Standard printing; 'unlimited' is the vintage
# equivalent for sets like Jungle/Fossil where TCGplayer never sold a
# raw / undistinguished printing. Holofoil, 1st Edition, and reverse
# holofoil printings are excluded -- their condition-to-price curves
# don't track raw cards.
NON_VARIANT_VALUES: tuple[str | None, ...] = (None, "unlimited")


# All forward transitions on the condition ladder. Backward transitions
# (e.g. LP->NM) are intentionally not stored -- multipliers represent the
# discount as a card degrades, not the premium of upgrading.
FORWARD_PAIRS: list[tuple[str, str]] = [
    ("NM", "LP"),
    ("NM", "MP"),
    ("NM", "HP"),
    ("NM", "DMG"),
    ("LP", "MP"),
    ("LP", "HP"),
    ("LP", "DMG"),
    ("MP", "HP"),
    ("MP", "DMG"),
    ("HP", "DMG"),
]


# Two grouping strategies are written for every set. Each entry pairs the
# `cards.<column>` source with the `grouping_type` literal stored in
# condition_multipliers. Adding a future grouping (e.g. supertype + rarity
# combined) is one entry here plus a UI control.
_GROUPINGS: list[tuple[str, str]] = [
    ("rarity", "rarity"),
    ("supertype", "supertype"),
]


def _pairs_values_clause() -> str:
    """Render FORWARD_PAIRS as a SQL VALUES list for inline use.

    Used inside the refresh CTE to constrain the cross-condition join to
    only the forward transitions we actually want. Inlining (rather than
    parameterising) is safe because the list is a hardcoded constant --
    not user input -- and avoids the bind-parameter gymnastics needed to
    pass a list of tuples to psycopg2.
    """
    return ", ".join(f"('{f}', '{t}')" for f, t in FORWARD_PAIRS)


def find_ungrouped_cards(session: Session, set_id: str) -> list[dict[str, Any]]:
    """Cards in this set whose rarity OR supertype is NULL.

    Such cards are excluded from the multiplier calculation because we
    can't bucket them into a grouping_value. Returned so the run summary
    can flag them -- they should be fixed in the source TCGdex data
    rather than left as silent gaps.
    """
    rows = session.execute(
        text(
            """
            SELECT id, name,
                   CASE
                     WHEN rarity IS NULL AND supertype IS NULL THEN 'rarity+supertype'
                     WHEN rarity IS NULL THEN 'rarity'
                     ELSE 'supertype'
                   END AS missing_field
            FROM cards
            WHERE set_id = :set_id
              AND (rarity IS NULL OR supertype IS NULL)
            ORDER BY id
            """
        ),
        {"set_id": set_id},
    ).fetchall()
    return [
        {
            "set_id": set_id,
            "card_id": r.id,
            "name": r.name,
            "missing_field": r.missing_field,
        }
        for r in rows
    ]


def _compute_multiplier_rows(
    session: Session, set_id: str, group_column: str, grouping_type: str
) -> list[dict[str, Any]]:
    """Run the ratio aggregation query for one set and one grouping.

    Returns a list of dicts ready to bulk-insert into condition_multipliers.
    `group_column` is one of {'rarity', 'supertype'} -- it's interpolated
    into the SQL because column names can't be parameterised. The caller
    (refresh_set) only ever passes whitelisted values.
    """
    pairs_clause = _pairs_values_clause()

    # The CTE chain is:
    #   monthly  -- avg market_price per (card, condition, month)
    #   ratios   -- pairwise ratios for the FORWARD_PAIRS, per (card, month)
    # then we GROUP BY the cards.* column and the (from, to) pair.
    #
    # ROUND to 4 decimal places so the result fits NUMERIC(5,4). A rare
    # condition pair could in theory exceed 1.0 (e.g. an LP listing
    # priced higher than the matched NM listing for the same card-month
    # due to listing variance), and NUMERIC(5,4) caps at 9.9999 -- well
    # above any realistic ratio.
    rows = session.execute(
        text(
            f"""
            WITH monthly AS (
                -- "Non-variant" here covers both the modern Standard
                -- printing (variant IS NULL) and the vintage Unlimited
                -- printing -- TCGplayer treats Unlimited as the default
                -- baseline for old sets that never had a single
                -- "raw" SKU. Per-set there's no overlap (modern sets
                -- use NULL only, Jungle/Fossil-era use 'unlimited' only),
                -- so this OR doesn't risk averaging multiple printings
                -- of the same card together.
                SELECT ps.card_id,
                       ps.condition,
                       date_trunc('month', ps.captured_date) AS month,
                       AVG(ps.market_price) AS avg_price
                FROM price_snapshots ps
                JOIN cards c ON c.id = ps.card_id
                WHERE c.set_id = :set_id
                  AND ps.source = 'tcgplayer'
                  AND (ps.variant IS NULL OR ps.variant = 'unlimited')
                  AND ps.market_price IS NOT NULL
                  AND ps.captured_date >= CURRENT_DATE - INTERVAL '6 months'
                GROUP BY ps.card_id, ps.condition, date_trunc('month', ps.captured_date)
            ),
            ratios AS (
                SELECT f.card_id,
                       f.month,
                       f.condition AS from_c,
                       t.condition AS to_c,
                       (t.avg_price / f.avg_price) AS ratio
                FROM monthly f
                JOIN monthly t
                  ON t.card_id = f.card_id AND t.month = f.month
                JOIN (VALUES {pairs_clause}) AS pairs(from_c, to_c)
                  ON pairs.from_c = f.condition AND pairs.to_c = t.condition
                WHERE f.avg_price > 0
            )
            SELECT c.{group_column} AS grouping_value,
                   r.from_c AS from_condition,
                   r.to_c   AS to_condition,
                   -- Median, not mean. The arithmetic mean is dominated by
                   -- sub-dollar listing noise: a $0.05 NM common with a
                   -- single $0.50 DMG listing produces a 10x ratio that
                   -- skews AVG well above 1.0 even with hundreds of
                   -- well-behaved card-month observations in the same
                   -- bucket. PERCENTILE_CONT(0.5) ignores those outliers
                   -- and reflects how a typical card actually trades.
                   ROUND(
                       PERCENTILE_CONT(0.5)
                           WITHIN GROUP (ORDER BY r.ratio)::numeric,
                       4
                   ) AS multiplier,
                   COUNT(*) AS data_points
            FROM ratios r
            JOIN cards c ON c.id = r.card_id
            WHERE c.{group_column} IS NOT NULL
            GROUP BY c.{group_column}, r.from_c, r.to_c
            """
        ),
        {"set_id": set_id},
    ).fetchall()

    return [
        {
            "set_id": set_id,
            "grouping_type": grouping_type,
            "grouping_value": r.grouping_value,
            "from_condition": r.from_condition,
            "to_condition": r.to_condition,
            "multiplier": r.multiplier,
            "data_points": r.data_points,
        }
        for r in rows
    ]


def _bulk_insert_rows(session: Session, rows: list[dict[str, Any]]) -> None:
    """Single-statement multi-row INSERT for one set's rows.

    Mirrors the bulk-insert style used by ingestion/loader.py for
    price_snapshots. Sub-9000 bind params per statement is well above the
    realistic per-set row count (a few hundred at most), so no chunking
    is needed here -- a set with 8 rarities × 10 transitions × 2 groupings
    is 160 rows.
    """
    if not rows:
        return

    placeholders = []
    params: dict[str, Any] = {}
    for i, r in enumerate(rows):
        placeholders.append(
            f"(:set_id_{i}, :gt_{i}, :gv_{i}, :fc_{i}, :tc_{i}, :m_{i}, :dp_{i}, NOW())"
        )
        params[f"set_id_{i}"] = r["set_id"]
        params[f"gt_{i}"] = r["grouping_type"]
        params[f"gv_{i}"] = r["grouping_value"]
        params[f"fc_{i}"] = r["from_condition"]
        params[f"tc_{i}"] = r["to_condition"]
        params[f"m_{i}"] = r["multiplier"]
        params[f"dp_{i}"] = r["data_points"]

    session.execute(
        text(
            f"""
            INSERT INTO condition_multipliers
                (set_id, grouping_type, grouping_value,
                 from_condition, to_condition, multiplier, data_points,
                 last_refreshed)
            VALUES {", ".join(placeholders)}
            """
        ),
        params,
    )


def refresh_set(session: Session, set_id: str) -> dict[str, Any]:
    """Recompute condition_multipliers rows for a single set.

    Wipes the existing rows for `set_id` then writes the freshly computed
    set in one transaction. The caller is responsible for the transaction
    boundary.

    Returns:
        dict with keys:
            rows_written       -- total rows inserted for this set
            ungrouped_warnings -- list of {set_id, card_id, name,
                                  missing_field} for cards excluded from
                                  the calculation due to NULL grouping
                                  fields
    """
    log.info("Refreshing multipliers for set %s", set_id)

    ungrouped = find_ungrouped_cards(session, set_id)
    if ungrouped:
        log.warning(
            "Set %s has %d card(s) with NULL rarity or supertype -- "
            "excluded from multiplier calculation. Fix the source data "
            "in TCGdex and re-ingest to recover them.",
            set_id, len(ungrouped),
        )

    all_rows: list[dict[str, Any]] = []
    for group_column, grouping_type in _GROUPINGS:
        group_rows = _compute_multiplier_rows(session, set_id, group_column, grouping_type)
        all_rows.extend(group_rows)

    # Replace previous rows for this set. Done after the SELECTs so a
    # query failure doesn't leave the table empty for this set.
    session.execute(
        text("DELETE FROM condition_multipliers WHERE set_id = :set_id"),
        {"set_id": set_id},
    )
    _bulk_insert_rows(session, all_rows)

    log.info(
        "Set %s: wrote %d multiplier row(s) (%d ungrouped card(s) skipped)",
        set_id, len(all_rows), len(ungrouped),
    )

    return {"rows_written": len(all_rows), "ungrouped_warnings": ungrouped}


def refresh_all_sets() -> dict[str, Any]:
    """Recompute multipliers for every set in the database.

    Each set is processed in its own transaction so a failure on one set
    doesn't roll back the others. The returned stats are intended to feed
    the run-summary log block emitted by run_refresh_multipliers.py and
    surfaced in the nightly email.

    Returns:
        dict with keys:
            sets_processed     -- number of sets the refresh succeeded on
            sets_failed        -- number of sets that raised mid-refresh
            rows_written       -- total rows inserted across all sets
            ungrouped_warnings -- aggregated list across all sets
            failed_sets        -- list of (set_id, error message)
    """
    engine = _get_engine()

    # Pull set list outside any per-set transaction.
    with Session(engine) as session:
        set_ids = [
            row.id
            for row in session.execute(text("SELECT id FROM sets ORDER BY id")).fetchall()
        ]

    log.info("Refreshing multipliers for %d set(s)", len(set_ids))

    stats: dict[str, Any] = {
        "sets_processed": 0,
        "sets_failed": 0,
        "rows_written": 0,
        "ungrouped_warnings": [],
        "failed_sets": [],
    }

    for set_id in set_ids:
        try:
            with Session(engine) as session:
                with session.begin():
                    set_stats = refresh_set(session, set_id)
            stats["sets_processed"] += 1
            stats["rows_written"] += set_stats["rows_written"]
            stats["ungrouped_warnings"].extend(set_stats["ungrouped_warnings"])
        except Exception as exc:
            log.exception("Failed to refresh set %s: %s", set_id, exc)
            stats["sets_failed"] += 1
            stats["failed_sets"].append((set_id, str(exc)))

    return stats
