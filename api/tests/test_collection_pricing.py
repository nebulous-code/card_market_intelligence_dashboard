"""
Tests for services.collection_pricing.

Fixtures hand-craft a small set of price snapshots so LOCF, threshold
filtering, and per-card aggregation can be asserted exactly. Each test
inserts the snapshots it needs through the per-test session, so
rollback at teardown wipes the data.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from schemas.collection import ParsedCollectionRow
from services.collection_pricing import (
    WINDOW_DAYS,
    cards_with_prices,
    daily_timeseries,
    movers,
    parse_window,
)


@pytest.fixture
def today():
    return date.today()


def _row(card_id: str, condition: str = "NM", **overrides) -> ParsedCollectionRow:
    base = dict(
        card_id=card_id,
        condition=condition,
        variant=[],
        is_first_edition=False,
        quantity=1,
        purchase_price=None,
    )
    base.update(overrides)
    return ParsedCollectionRow(**base)


def _add_snapshot(db_session, card_id, captured, market_price, variant=None):
    from datetime import datetime

    from models.card import PriceSnapshot

    db_session.add(
        PriceSnapshot(
            card_id=card_id,
            source="tcgplayer",
            condition="NM",
            variant=variant,
            market_price=Decimal(str(market_price)),
            captured_at=datetime.combine(captured, datetime.min.time()),
            captured_date=captured,
        )
    )


# ---------- parse_window ----------


def test_parse_window_default_is_30d():
    assert parse_window(None) == "30d"
    assert parse_window("") == "30d"


def test_parse_window_normalizes_case_and_whitespace():
    assert parse_window("  30D ") == "30d"


def test_parse_window_rejects_unknown():
    with pytest.raises(ValueError, match="window must be one of"):
        parse_window("yearly")


def test_window_days_constants_match_spec():
    """The plan locks in 7/30/90/183 days plus 'all'. A regression here
    would silently change everyone's chart range."""
    assert WINDOW_DAYS == {"7d": 7, "30d": 30, "90d": 90, "6m": 183, "all": None}


# ---------- cards_with_prices ----------


def test_cards_with_prices_empty_input_returns_empty():
    assert cards_with_prices(None, []) == []  # db arg unused on empty path


def test_cards_with_prices_joins_metadata_and_price(db_session, sample_cards, today):
    _add_snapshot(db_session, "base1-4", today, "120.00")
    db_session.flush()
    rows = [_row("base1-4", quantity=2, purchase_price=Decimal("100"))]
    out = cards_with_prices(db_session, rows)

    assert len(out) == 1
    entry = out[0]
    assert entry.card_id == "base1-4"
    assert entry.card_name == "Charizard"
    assert entry.set_name == "Base Set"
    assert entry.market_price == Decimal("120.00")
    assert entry.purchase_price == Decimal("100")
    assert entry.quantity == 2


def test_cards_with_prices_picks_latest_snapshot(db_session, sample_cards, today):
    _add_snapshot(db_session, "base1-4", today - timedelta(days=10), "100.00")
    _add_snapshot(db_session, "base1-4", today - timedelta(days=1), "150.00")
    db_session.flush()
    rows = [_row("base1-4")]
    [entry] = cards_with_prices(db_session, rows)
    assert entry.market_price == Decimal("150.00")


def test_cards_with_prices_prefers_null_variant_when_dates_tie(
    db_session, sample_cards, today
):
    """When two snapshots tie on captured_at, NULL variant wins."""
    _add_snapshot(db_session, "base1-4", today, "100.00", variant="holofoil")
    _add_snapshot(db_session, "base1-4", today, "200.00", variant=None)
    db_session.flush()
    rows = [_row("base1-4")]
    [entry] = cards_with_prices(db_session, rows)
    assert entry.market_price == Decimal("200.00")


def test_cards_with_prices_market_price_none_when_no_snapshot(
    db_session, sample_cards
):
    rows = [_row("base1-4")]
    [entry] = cards_with_prices(db_session, rows)
    assert entry.market_price is None


def test_cards_with_prices_filters_to_tcgplayer_source(
    db_session, sample_cards, today
):
    """A snapshot from a non-tcgplayer source is ignored by the dashboard."""
    from datetime import datetime

    from models.card import PriceSnapshot

    db_session.add(
        PriceSnapshot(
            card_id="base1-4",
            source="ebay",
            condition="NM",
            variant=None,
            market_price=Decimal("999.00"),
            captured_at=datetime.combine(today, datetime.min.time()),
            captured_date=today,
        )
    )
    db_session.flush()
    rows = [_row("base1-4")]
    [entry] = cards_with_prices(db_session, rows)
    assert entry.market_price is None


# ---------- daily_timeseries ----------


def test_timeseries_empty_input_returns_empty():
    points, earliest = daily_timeseries(None, [], "30d")
    assert points == []
    assert earliest is None


def test_timeseries_no_snapshots_returns_empty(db_session, sample_cards):
    points, earliest = daily_timeseries(
        db_session, [_row("base1-4")], "30d"
    )
    assert points == []
    assert earliest is None


def test_timeseries_locf_carries_last_known_price(
    db_session, sample_cards, today
):
    """A 30-day window where the only snapshot is at day 0 should produce
    30 points all carrying that price forward."""
    _add_snapshot(db_session, "base1-4", today - timedelta(days=29), "10.00")
    db_session.flush()
    rows = [_row("base1-4", quantity=2)]
    points, earliest = daily_timeseries(db_session, rows, "30d")
    assert len(points) == 30
    assert all(p.value == Decimal("20.00") for p in points)
    assert earliest == today - timedelta(days=29)


def test_timeseries_locf_falls_back_to_earliest_for_predating_dates(
    db_session, sample_cards, today
):
    """When the window predates every snapshot, the earliest snapshot
    is used as a flat baseline rather than zero."""
    _add_snapshot(db_session, "base1-4", today - timedelta(days=2), "5.00")
    db_session.flush()
    rows = [_row("base1-4", quantity=1)]
    points, _ = daily_timeseries(db_session, rows, "7d")
    # First few points predate the snapshot; LOCF falls back to earliest.
    assert points[0].value == Decimal("5.00")
    assert points[-1].value == Decimal("5.00")


def test_timeseries_handles_price_step_change(db_session, sample_cards, today):
    _add_snapshot(db_session, "base1-4", today - timedelta(days=6), "10.00")
    _add_snapshot(db_session, "base1-4", today - timedelta(days=2), "20.00")
    db_session.flush()
    rows = [_row("base1-4", quantity=1)]
    points, _ = daily_timeseries(db_session, rows, "7d")
    # Last 3 points (today, day-1, day-2) are at 20.00; earlier four at 10.00.
    values = [p.value for p in points]
    assert values[0] == Decimal("10.00")
    assert values[-1] == Decimal("20.00")


def test_timeseries_aggregates_quantity_across_rows(
    db_session, sample_cards, today
):
    """Two session rows for the same (card, condition) sum quantities."""
    _add_snapshot(db_session, "base1-4", today, "10.00")
    db_session.flush()
    rows = [
        _row("base1-4", quantity=1),
        _row("base1-4", quantity=3),
    ]
    points, _ = daily_timeseries(db_session, rows, "7d")
    assert points[-1].value == Decimal("40.00")


def test_timeseries_all_window_with_no_snapshots(db_session, sample_cards):
    """``all`` window with no historical data returns empty without raising."""
    rows = [_row("base1-4")]
    points, earliest = daily_timeseries(db_session, rows, "all")
    assert points == []
    assert earliest is None


def test_timeseries_all_window_starts_at_earliest_snapshot(
    db_session, sample_cards, today
):
    earliest = today - timedelta(days=4)
    _add_snapshot(db_session, "base1-4", earliest, "5.00")
    db_session.flush()
    rows = [_row("base1-4", quantity=1)]
    points, retrieved_earliest = daily_timeseries(db_session, rows, "all")
    assert retrieved_earliest == earliest
    assert points[0].date == earliest.isoformat()


def test_timeseries_clips_window_start_to_earliest(
    db_session, sample_cards, today
):
    """A 30D window with only 5 days of history should clip to those 5
    days rather than returning 25 zero-value points."""
    earliest = today - timedelta(days=4)
    _add_snapshot(db_session, "base1-4", earliest, "5.00")
    db_session.flush()
    rows = [_row("base1-4", quantity=1)]
    points, _ = daily_timeseries(db_session, rows, "30d")
    assert points[0].date == earliest.isoformat()
    assert len(points) == 5


def test_timeseries_skips_session_rows_without_snapshots(
    db_session, sample_cards, today
):
    """A session row whose card has no snapshots contributes 0 each day."""
    _add_snapshot(db_session, "base1-4", today, "10.00")
    db_session.flush()
    rows = [
        _row("base1-4", quantity=1),
        _row("base1-58", quantity=5),  # no snapshots
    ]
    points, _ = daily_timeseries(db_session, rows, "7d")
    assert points[-1].value == Decimal("10.00")


# ---------- movers ----------


def test_movers_empty_input_returns_empty():
    g, l = movers(None, [], "30d", count=5, min_pct=Decimal("0.05"))
    assert g == [] and l == []


def test_movers_no_snapshots_returns_empty(db_session, sample_cards):
    rows = [_row("base1-4")]
    g, l = movers(db_session, rows, "30d", 5, Decimal("0.05"))
    assert g == [] and l == []


def test_movers_classifies_gainer_above_threshold(db_session, sample_cards, today):
    _add_snapshot(db_session, "base1-4", today - timedelta(days=29), "10.00")
    _add_snapshot(db_session, "base1-4", today, "12.00")
    db_session.flush()
    rows = [_row("base1-4")]
    g, l = movers(db_session, rows, "30d", 5, Decimal("0.05"))
    assert len(g) == 1
    assert g[0].card_name == "Charizard"
    assert g[0].change_pct == Decimal("0.2000")
    assert l == []


def test_movers_classifies_loser_below_threshold(db_session, sample_cards, today):
    _add_snapshot(db_session, "base1-4", today - timedelta(days=29), "20.00")
    _add_snapshot(db_session, "base1-4", today, "15.00")
    db_session.flush()
    rows = [_row("base1-4")]
    g, l = movers(db_session, rows, "30d", 5, Decimal("0.05"))
    assert g == []
    assert len(l) == 1
    assert l[0].change_pct == Decimal("-0.2500")


def test_movers_excludes_below_min_pct(db_session, sample_cards, today):
    """A 3% movement is below the 5% threshold and is dropped entirely."""
    _add_snapshot(db_session, "base1-4", today - timedelta(days=29), "100.00")
    _add_snapshot(db_session, "base1-4", today, "103.00")
    db_session.flush()
    rows = [_row("base1-4")]
    g, l = movers(db_session, rows, "30d", 5, Decimal("0.05"))
    assert g == [] and l == []


def test_movers_collapses_duplicate_card_condition_pairs(
    db_session, sample_cards, today
):
    """Two session rows for the same (card, condition) only show once."""
    _add_snapshot(db_session, "base1-4", today - timedelta(days=29), "10.00")
    _add_snapshot(db_session, "base1-4", today, "20.00")
    db_session.flush()
    rows = [
        _row("base1-4", quantity=1),
        _row("base1-4", quantity=2),
    ]
    g, _ = movers(db_session, rows, "30d", 5, Decimal("0.05"))
    assert len(g) == 1


def test_movers_caps_results_at_count(db_session, sample_set, today):
    from models.card import Card

    # Insert 7 distinct cards each with a >5% gainer profile.
    for i in range(1, 8):
        db_session.add(
            Card(
                id=f"base1-{i}",
                set_id=sample_set.id,
                name=f"Card {i}",
                number=str(i),
                rarity="rare",
                supertype="Pokemon",
            )
        )
    db_session.flush()
    for i in range(1, 8):
        _add_snapshot(db_session, f"base1-{i}", today - timedelta(days=29), "10.00")
        _add_snapshot(db_session, f"base1-{i}", today, str(20 + i))
    db_session.flush()
    rows = [_row(f"base1-{i}") for i in range(1, 8)]
    g, _ = movers(db_session, rows, "30d", count=3, min_pct=Decimal("0.05"))
    assert len(g) == 3
    # Sorted by largest gain first.
    assert [m.card_id for m in g] == ["base1-7", "base1-6", "base1-5"]


def test_movers_sorts_losers_largest_drop_first(db_session, sample_cards, today):
    """Two losers; the larger absolute drop sorts first."""
    _add_snapshot(db_session, "base1-4", today - timedelta(days=29), "100.00")
    _add_snapshot(db_session, "base1-4", today, "50.00")  # -50%
    _add_snapshot(db_session, "base1-58", today - timedelta(days=29), "100.00")
    _add_snapshot(db_session, "base1-58", today, "75.00")  # -25%
    db_session.flush()
    rows = [_row("base1-4"), _row("base1-58")]
    _, l = movers(db_session, rows, "30d", 5, Decimal("0.05"))
    assert [m.card_id for m in l] == ["base1-4", "base1-58"]


def test_movers_excludes_cards_with_zero_start_price(
    db_session, sample_cards, today
):
    """A card whose start_price is 0 (rare but possible) is dropped to
    avoid divide-by-zero on the percentage calculation."""
    _add_snapshot(db_session, "base1-4", today - timedelta(days=29), "0.00")
    _add_snapshot(db_session, "base1-4", today, "10.00")
    db_session.flush()
    rows = [_row("base1-4")]
    g, l = movers(db_session, rows, "30d", 5, Decimal("0.05"))
    assert g == [] and l == []


def test_movers_all_window_uses_earliest_snapshot(
    db_session, sample_cards, today
):
    earliest = today - timedelta(days=120)
    _add_snapshot(db_session, "base1-4", earliest, "10.00")
    _add_snapshot(db_session, "base1-4", today, "15.00")
    db_session.flush()
    rows = [_row("base1-4")]
    g, _ = movers(db_session, rows, "all", 5, Decimal("0.05"))
    assert len(g) == 1
    assert g[0].start_price == Decimal("10.00")
    assert g[0].current_price == Decimal("15.00")


def test_movers_locf_falls_back_to_earliest_when_window_predates_history(
    db_session, sample_cards, today
):
    """For a fixed window that predates the earliest snapshot, the
    ``start_price`` returned should be that earliest snapshot's price
    (LOCF's defensive fallback) rather than ``None`` / zero."""
    earliest = today - timedelta(days=2)
    _add_snapshot(db_session, "base1-4", earliest, "10.00")
    _add_snapshot(db_session, "base1-4", today, "12.00")
    db_session.flush()
    rows = [_row("base1-4")]
    g, l = movers(db_session, rows, "30d", 5, Decimal("0.05"))
    # start_date = today - 29; LOCF for that date predates the earliest
    # snapshot, so it falls back to 10.00. current_price is 12.00 -> 20% gain.
    assert len(g) == 1
    assert g[0].start_price == Decimal("10.00")
    assert g[0].change_pct == Decimal("0.2000")
    assert l == []


def test_movers_all_window_with_no_snapshots(db_session, sample_cards):
    """`all` window with no snapshots anywhere should short-circuit to
    empty results without raising."""
    rows = [_row("base1-4")]
    g, l = movers(db_session, rows, "all", 5, Decimal("0.05"))
    assert g == [] and l == []
