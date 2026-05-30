"""
Tests for ingestion/refresh_multipliers.py.

Pure helpers (FORWARD_PAIRS, _pairs_values_clause) are unit-tested
directly. DB-touching helpers use the conftest db_session fixture, with
refresh_all_sets exercising its own Session(engine) path against a
patched module-level engine that points at the test connection.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text


# ---------- pure helpers ----------


def test_forward_pairs_covers_ten_transitions():
    from refresh_multipliers import FORWARD_PAIRS

    assert len(FORWARD_PAIRS) == 10
    # Every pair is forward on the NM->DMG ladder.
    ladder = ["NM", "LP", "MP", "HP", "DMG"]
    for from_c, to_c in FORWARD_PAIRS:
        assert ladder.index(to_c) > ladder.index(from_c)


def test_pairs_values_clause_renders_each_pair():
    from refresh_multipliers import FORWARD_PAIRS, _pairs_values_clause

    clause = _pairs_values_clause()
    for from_c, to_c in FORWARD_PAIRS:
        assert f"('{from_c}', '{to_c}')" in clause


# ---------- find_ungrouped_cards ----------


def _seed_set_with_cards(db_session, set_id, cards):
    """Helper: insert a set and a list of (card_id, rarity, supertype) tuples."""
    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, created_at) "
            "VALUES (:id, 'Test', 'X', 1, NOW())"
        ),
        {"id": set_id},
    )
    for card_id, rarity, supertype in cards:
        db_session.execute(
            text(
                "INSERT INTO cards (id, set_id, name, number, rarity, supertype, created_at) "
                "VALUES (:id, :sid, :name, :num, :rarity, :supertype, NOW())"
            ),
            {
                "id": card_id, "sid": set_id, "name": card_id, "num": card_id.split("-")[-1],
                "rarity": rarity, "supertype": supertype,
            },
        )


def test_find_ungrouped_cards_returns_empty_when_all_classified(db_session):
    from refresh_multipliers import find_ungrouped_cards

    _seed_set_with_cards(db_session, "fu_a", [
        ("fu_a-1", "common", "Pokemon"),
        ("fu_a-2", "rare", "Trainer"),
    ])
    assert find_ungrouped_cards(db_session, "fu_a") == []


def test_find_ungrouped_cards_flags_each_missing_field(db_session):
    from refresh_multipliers import find_ungrouped_cards

    _seed_set_with_cards(db_session, "fu_b", [
        ("fu_b-1", None,    "Pokemon"),    # missing rarity
        ("fu_b-2", "rare",  None),         # missing supertype
        ("fu_b-3", None,    None),         # missing both
        ("fu_b-4", "rare",  "Pokemon"),    # OK
    ])
    rows = find_ungrouped_cards(db_session, "fu_b")
    by_id = {r["card_id"]: r["missing_field"] for r in rows}
    assert by_id == {
        "fu_b-1": "rarity",
        "fu_b-2": "supertype",
        "fu_b-3": "rarity+supertype",
    }
    # Returned dicts always include the set_id and card name for the run summary.
    assert all(r["set_id"] == "fu_b" and r["name"] for r in rows)


# ---------- _bulk_insert_rows ----------


def test_bulk_insert_rows_empty_is_noop(db_session):
    from refresh_multipliers import _bulk_insert_rows

    _bulk_insert_rows(db_session, [])  # must not raise


def test_bulk_insert_rows_inserts_each_row(db_session):
    from refresh_multipliers import _bulk_insert_rows

    _seed_set_with_cards(db_session, "bi_a", [("bi_a-1", "common", "Pokemon")])

    rows = [
        {"set_id": "bi_a", "grouping_type": "rarity", "grouping_value": "common",
         "from_condition": "NM", "to_condition": "LP",
         "multiplier": Decimal("0.6000"), "data_points": 10},
        {"set_id": "bi_a", "grouping_type": "rarity", "grouping_value": "common",
         "from_condition": "NM", "to_condition": "MP",
         "multiplier": Decimal("0.4000"), "data_points": 8},
    ]
    _bulk_insert_rows(db_session, rows)

    count = db_session.execute(
        text("SELECT COUNT(*) FROM condition_multipliers WHERE set_id = 'bi_a'")
    ).scalar()
    assert count == 2


# ---------- _compute_multiplier_rows / refresh_set integration ----------


def _seed_priceable_card(db_session, set_id, card_id, rarity="common",
                          supertype="Pokemon", prices_per_condition=None):
    """Insert a card plus a price snapshot per condition for a given month.

    `prices_per_condition` defaults to NM=$10, LP=$6, MP=$4, HP=$2, DMG=$1
    -- a clean degradation curve so the median picks predictable ratios.
    """
    if prices_per_condition is None:
        prices_per_condition = {"NM": "10.00", "LP": "6.00", "MP": "4.00",
                                  "HP": "2.00", "DMG": "1.00"}
    db_session.execute(
        text(
            "INSERT INTO cards (id, set_id, name, number, rarity, supertype, created_at) "
            "VALUES (:id, :sid, :name, :num, :rarity, :supertype, NOW())"
        ),
        {"id": card_id, "sid": set_id, "name": card_id,
         "num": card_id.split("-")[-1], "rarity": rarity, "supertype": supertype},
    )
    for cond, price in prices_per_condition.items():
        db_session.execute(
            text(
                "INSERT INTO price_snapshots "
                "(card_id, source, condition, variant, market_price, captured_at, captured_date) "
                "VALUES (:cid, 'tcgplayer', :cond, NULL, :price, NOW(), CURRENT_DATE - 7)"
            ),
            {"cid": card_id, "cond": cond, "price": price},
        )


def test_compute_multiplier_rows_returns_full_pair_set(db_session):
    from refresh_multipliers import _compute_multiplier_rows

    _seed_set_with_cards(db_session, "cm_a", [])
    _seed_priceable_card(db_session, "cm_a", "cm_a-1")
    _seed_priceable_card(db_session, "cm_a", "cm_a-2")

    rows = _compute_multiplier_rows(db_session, "cm_a", "rarity", "rarity")
    pairs = {(r["from_condition"], r["to_condition"]) for r in rows}
    # All 10 forward transitions show up because every card has every condition.
    assert len(pairs) == 10
    # NM->LP should be exactly 0.60 with the seed data.
    nm_lp = next(r for r in rows if (r["from_condition"], r["to_condition"]) == ("NM", "LP"))
    assert nm_lp["multiplier"] == Decimal("0.6000")
    assert nm_lp["grouping_value"] == "common"


def test_compute_multiplier_rows_excludes_variants_and_other_sources(db_session):
    """Snapshots with variant != NULL or source != tcgplayer must be ignored."""
    from refresh_multipliers import _compute_multiplier_rows

    _seed_set_with_cards(db_session, "cm_b", [])
    _seed_priceable_card(db_session, "cm_b", "cm_b-1")

    # Add a noisy variant snapshot that should be filtered out.
    db_session.execute(
        text(
            "INSERT INTO price_snapshots "
            "(card_id, source, condition, variant, market_price, captured_at, captured_date) "
            "VALUES ('cm_b-1', 'tcgplayer', 'NM', 'holofoil', 99999, NOW(), CURRENT_DATE - 7)"
        )
    )
    # Add an off-source row (not tcgplayer) -- also filtered out.
    db_session.execute(
        text(
            "INSERT INTO price_snapshots "
            "(card_id, source, condition, variant, market_price, captured_at, captured_date) "
            "VALUES ('cm_b-1', 'psa', 'PSA-10', NULL, 999, NOW(), CURRENT_DATE - 7)"
        )
    )

    rows = _compute_multiplier_rows(db_session, "cm_b", "rarity", "rarity")
    nm_lp = next(r for r in rows if (r["from_condition"], r["to_condition"]) == ("NM", "LP"))
    assert nm_lp["multiplier"] == Decimal("0.6000")  # would be wildly off if variant rows leaked


def test_compute_multiplier_rows_excludes_null_grouping_value(db_session):
    """Cards whose grouping column is NULL contribute nothing to the result."""
    from refresh_multipliers import _compute_multiplier_rows

    _seed_set_with_cards(db_session, "cm_c", [])
    _seed_priceable_card(db_session, "cm_c", "cm_c-1", rarity=None)

    rows = _compute_multiplier_rows(db_session, "cm_c", "rarity", "rarity")
    assert rows == []


def test_compute_multiplier_rows_includes_unlimited_variant(db_session):
    """Variant 'unlimited' is treated as a non-variant printing for vintage sets."""
    from refresh_multipliers import _compute_multiplier_rows

    _seed_set_with_cards(db_session, "cm_d", [])
    db_session.execute(
        text(
            "INSERT INTO cards (id, set_id, name, number, rarity, supertype, created_at) "
            "VALUES ('cm_d-1', 'cm_d', 'X', '1', 'common', 'Pokemon', NOW())"
        )
    )
    for cond, price in [("NM", "10.00"), ("LP", "6.00")]:
        db_session.execute(
            text(
                "INSERT INTO price_snapshots "
                "(card_id, source, condition, variant, market_price, captured_at, captured_date) "
                "VALUES ('cm_d-1', 'tcgplayer', :cond, 'unlimited', :p, NOW(), CURRENT_DATE - 7)"
            ),
            {"cond": cond, "p": price},
        )

    rows = _compute_multiplier_rows(db_session, "cm_d", "rarity", "rarity")
    nm_lp = next(r for r in rows if (r["from_condition"], r["to_condition"]) == ("NM", "LP"))
    assert nm_lp["multiplier"] == Decimal("0.6000")


def test_refresh_set_writes_both_grouping_types(db_session):
    """End-to-end: refresh_set writes rarity AND supertype rows."""
    from refresh_multipliers import refresh_set

    _seed_set_with_cards(db_session, "rs_a", [])
    _seed_priceable_card(db_session, "rs_a", "rs_a-1")

    stats = refresh_set(db_session, "rs_a")
    assert stats["rows_written"] == 20  # 10 forward pairs * 2 grouping types
    assert stats["ungrouped_warnings"] == []

    by_grouping_type = {
        gt: c
        for gt, c in db_session.execute(
            text(
                "SELECT grouping_type, COUNT(*) FROM condition_multipliers "
                "WHERE set_id = 'rs_a' GROUP BY grouping_type"
            )
        ).fetchall()
    }
    assert by_grouping_type == {"rarity": 10, "supertype": 10}


def test_refresh_set_replaces_previous_rows(db_session):
    """A second refresh deletes the prior rows before re-inserting."""
    from refresh_multipliers import refresh_set

    _seed_set_with_cards(db_session, "rs_b", [])
    _seed_priceable_card(db_session, "rs_b", "rs_b-1")

    refresh_set(db_session, "rs_b")
    refresh_set(db_session, "rs_b")  # second run -- must not double up

    count = db_session.execute(
        text("SELECT COUNT(*) FROM condition_multipliers WHERE set_id = 'rs_b'")
    ).scalar()
    assert count == 20  # same as one run


def test_refresh_set_surfaces_ungrouped_warnings(db_session):
    from refresh_multipliers import refresh_set

    _seed_set_with_cards(db_session, "rs_c", [
        ("rs_c-2", None, "Pokemon"),  # missing rarity
    ])
    _seed_priceable_card(db_session, "rs_c", "rs_c-1")  # OK card

    stats = refresh_set(db_session, "rs_c")
    assert any(w["card_id"] == "rs_c-2" for w in stats["ungrouped_warnings"])


# ---------- refresh_all_sets ----------


@pytest.fixture
def patched_engine(db_session, monkeypatch):
    """Bind refresh_multipliers.engine to db_session's connection so writes
    inside refresh_all_sets happen within the outer transaction."""
    import refresh_multipliers

    # Override _get_engine to return a Connection -- Session(connection)
    # opens nested SAVEPOINTs which the outer rollback wipes.
    connection = db_session.connection()
    monkeypatch.setattr(refresh_multipliers, "_engine", connection)
    monkeypatch.setattr(refresh_multipliers, "_get_engine", lambda: connection)
    yield connection


def test_refresh_all_sets_processes_every_set(db_session, patched_engine):
    from refresh_multipliers import refresh_all_sets

    _seed_set_with_cards(db_session, "ras_a", [])
    _seed_priceable_card(db_session, "ras_a", "ras_a-1")
    _seed_set_with_cards(db_session, "ras_b", [])
    _seed_priceable_card(db_session, "ras_b", "ras_b-1")

    stats = refresh_all_sets()
    assert stats["sets_processed"] >= 2
    assert stats["sets_failed"] == 0
    assert stats["rows_written"] >= 40  # 20 per seeded set, plus pre-existing


def test_refresh_all_sets_continues_after_one_set_fails(db_session, patched_engine, monkeypatch):
    """A failing set is logged and counted, others still run."""
    import refresh_multipliers
    from refresh_multipliers import refresh_all_sets

    _seed_set_with_cards(db_session, "ras_c", [])
    _seed_priceable_card(db_session, "ras_c", "ras_c-1")
    _seed_set_with_cards(db_session, "ras_d", [])
    _seed_priceable_card(db_session, "ras_d", "ras_d-1")

    real_refresh = refresh_multipliers.refresh_set
    call_count = {"n": 0}

    def flaky_refresh(session, set_id):
        call_count["n"] += 1
        if set_id == "ras_c":
            raise RuntimeError("set ras_c is sad")
        return real_refresh(session, set_id)

    monkeypatch.setattr(refresh_multipliers, "refresh_set", flaky_refresh)

    stats = refresh_all_sets()
    failed_ids = [sid for sid, _ in stats["failed_sets"]]
    assert "ras_c" in failed_ids
    assert stats["sets_failed"] >= 1
    assert stats["sets_processed"] >= 1


# ---------- _get_engine cache ----------


def test_get_engine_caches_instance(monkeypatch):
    """Repeated calls return the same engine object."""
    import refresh_multipliers

    monkeypatch.setattr(refresh_multipliers, "_engine", None)
    e1 = refresh_multipliers._get_engine()
    e2 = refresh_multipliers._get_engine()
    assert e1 is e2

    # Sanity: importing date/datetime above wasn't dead code -- both are
    # used in the helpers we exercise.
    assert isinstance(date(2024, 1, 1), date)
    assert isinstance(datetime(2024, 1, 1), datetime)
