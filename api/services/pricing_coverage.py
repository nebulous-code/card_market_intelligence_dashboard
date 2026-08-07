"""
Why a card in someone's collection has no price.

Pricing costs money per card, so we will never cover all ~218 Pokemon sets.
That is a permanent condition, not a gap to close. The catalogue ingest puts
every real set in the database so uploads validate against reality; this
module answers the question that follows -- given that a card has no price,
is that because we do not price its set, or because that particular card has
no snapshot inside a set we do price?

The distinction cannot be derived from a null price alone, which is why it
lives here rather than being recomputed ad hoc at each call site. Both the
Excel export and the web dashboard read it from this one function, so the
workbook and the dashboard cannot tell the user different stories.

Deliberately re-derived on every read rather than frozen onto the session
row at upload time: coverage changes when a nightly run adds a set, and a
stored reason would go stale while the price it explains did not.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

# The two reasons a row can be excluded from a valuation. Fixed strings
# rather than free text: these are user-facing copy AND the thing you grep
# when someone emails asking why their card is missing, so they have to be
# stable and enumerable.
REASON_SET_UNPRICED = "Set not priced yet"
REASON_CARD_UNPRICED = "Card not priced yet"

# Only reachable from the web dashboard. The Excel export falls back to the
# NM price for an unpriced condition and flags it with pricing_warning, so
# it lands on a number; the dashboard does not fall back, so a card we price
# in NM but not in the user's condition shows no price and needs saying so.
REASON_CONDITION_UNPRICED = "Condition not priced yet"


def coverage_reasons(db: Session, card_ids: list[str]) -> dict[str, str | None]:
    """
    Map each card id to why it has no price, or None when it has one.

    Args:
        db: Active database session.
        card_ids: The cards to check. Duplicates are harmless.

    Returns:
        dict[str, str | None]: card_id -> REASON_* constant, or None when the
            card has at least one price snapshot. Cards that do not exist in
            the database are absent from the result entirely.
    """
    if not card_ids:
        return {}

    unique_ids = sorted(set(card_ids))

    # Which of these cards live in which set, and which have any snapshot.
    # A LEFT JOIN over an EXISTS keeps this to one row per card regardless of
    # how much price history a card has -- some carry hundreds of snapshots.
    rows = db.execute(
        text("""
            SELECT c.id,
                   c.set_id,
                   EXISTS (
                       SELECT 1 FROM price_snapshots p WHERE p.card_id = c.id
                   ) AS card_priced
            FROM cards c
            WHERE c.id = ANY(:card_ids)
        """),
        {"card_ids": unique_ids},
    ).fetchall()

    if not rows:
        return {}

    # Set-level coverage is asked once per distinct set rather than once per
    # card. A collection spanning every priced set is a handful of ids.
    set_ids = sorted({r.set_id for r in rows})
    priced_sets = {
        r.set_id for r in db.execute(
            text("""
                SELECT DISTINCT c.set_id
                FROM cards c
                JOIN price_snapshots p ON p.card_id = c.id
                WHERE c.set_id = ANY(:set_ids)
            """),
            {"set_ids": set_ids},
        ).fetchall()
    }

    out: dict[str, str | None] = {}
    for r in rows:
        if r.card_priced:
            out[r.id] = None
        elif r.set_id in priced_sets:
            # The set is covered, this card just has no snapshot -- a genuine
            # per-card gap. base1-8 (Machamp) is one of these today.
            out[r.id] = REASON_CARD_UNPRICED
        else:
            out[r.id] = REASON_SET_UNPRICED
    return out
