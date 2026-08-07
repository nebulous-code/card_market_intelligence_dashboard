"""
Tests for api/services/pricing_coverage.py.

The distinction this module draws -- "we do not price that set" versus "that
card has no snapshot inside a set we do price" -- cannot be derived from a
null price alone. It is the difference between telling a user their set is
not covered yet and implying they made a mistake.
"""

from sqlalchemy import text

from services.pricing_coverage import (
    REASON_CARD_UNPRICED,
    REASON_SET_UNPRICED,
    coverage_reasons,
)


def _add_unpriced_set(db_session, set_id="jungle", card_id="jungle-1"):
    """A real set with real cards and no price snapshots at all."""
    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, created_at) "
            "VALUES (:sid, 'Jungle', 'Base', 64, NOW())"
        ),
        {"sid": set_id},
    )
    db_session.execute(
        text(
            "INSERT INTO cards (id, set_id, name, number, created_at) "
            "VALUES (:cid, :sid, 'Scyther', '10', NOW())"
        ),
        {"cid": card_id, "sid": set_id},
    )


def test_empty_input_short_circuits(db_session):
    assert coverage_reasons(db_session, []) == {}


def test_unknown_card_ids_are_absent_from_the_result(db_session):
    assert coverage_reasons(db_session, ["does-not-exist"]) == {}


def test_a_priced_card_has_no_reason(db_session, sample_set, sample_cards, sample_snapshots):
    reasons = coverage_reasons(db_session, ["base1-4"])
    assert reasons["base1-4"] is None


def test_a_card_with_no_snapshot_in_a_priced_set(db_session, sample_set, sample_cards, sample_snapshots):
    """base1-58 has a snapshot; a set-mate without one is a per-card gap,
    not a set-level one. This case exists in production today."""
    db_session.execute(
        text(
            "INSERT INTO cards (id, set_id, name, number, created_at) "
            "VALUES ('base1-8', 'base1', 'Machamp', '8', NOW())"
        )
    )
    reasons = coverage_reasons(db_session, ["base1-8"])
    assert reasons["base1-8"] == REASON_CARD_UNPRICED


def test_a_card_in_a_set_we_do_not_price(db_session, sample_set, sample_cards, sample_snapshots):
    _add_unpriced_set(db_session)
    reasons = coverage_reasons(db_session, ["jungle-1"])
    assert reasons["jungle-1"] == REASON_SET_UNPRICED


def test_distinguishes_all_three_cases_in_one_call(db_session, sample_set, sample_cards, sample_snapshots):
    """The whole point: one query, three different answers."""
    db_session.execute(
        text(
            "INSERT INTO cards (id, set_id, name, number, created_at) "
            "VALUES ('base1-8', 'base1', 'Machamp', '8', NOW())"
        )
    )
    _add_unpriced_set(db_session)

    reasons = coverage_reasons(db_session, ["base1-4", "base1-8", "jungle-1"])
    assert reasons == {
        "base1-4": None,
        "base1-8": REASON_CARD_UNPRICED,
        "jungle-1": REASON_SET_UNPRICED,
    }


def test_duplicate_card_ids_are_harmless(db_session, sample_set, sample_cards, sample_snapshots):
    reasons = coverage_reasons(db_session, ["base1-4", "base1-4", "base1-4"])
    assert reasons == {"base1-4": None}
