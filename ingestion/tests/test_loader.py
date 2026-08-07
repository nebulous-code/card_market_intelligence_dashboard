"""
Tests for ingestion/loader.py -- the database writer for the ingestion pipeline.

Strategy:

  - Pure helpers (_parse_date, _asset_url, _nearby_numbers, _load_aliases,
    _load_rarity_aliases, _build_snapshot_rows) are unit-tested directly.
  - upsert_set, upsert_card, _bulk_insert_snapshots take a Session argument
    -- those are tested with the conftest db_session fixture.
  - load_set and insert_price_snapshots open their own Session(engine).
    The `engine_in_test` fixture rebinds loader.engine to db_session's
    connection so writes happen inside the same outer transaction the test
    rolls back at teardown. This avoids leaking rows between tests while
    still exercising the real begin/commit logic.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import text


# ---------- pure helpers ----------


def test_parse_date_valid_string():
    from loader import _parse_date

    assert _parse_date("2024-05-01") == date(2024, 5, 1)


def test_parse_date_none():
    from loader import _parse_date

    assert _parse_date(None) is None


def test_parse_date_empty():
    from loader import _parse_date

    assert _parse_date("") is None


def test_parse_date_invalid_format():
    from loader import _parse_date

    assert _parse_date("not-a-date") is None
    assert _parse_date("2024/05/01") is None


def test_asset_url_none():
    from loader import _asset_url

    assert _asset_url(None) is None
    assert _asset_url("") is None


def test_asset_url_appends_png_when_no_extension():
    from loader import _asset_url

    assert _asset_url("https://x.com/logo") == "https://x.com/logo.png"


def test_asset_url_returns_unchanged_when_extension_present():
    from loader import _asset_url

    assert _asset_url("https://x.com/logo.svg") == "https://x.com/logo.svg"


def test_nearby_numbers_returns_three_closest():
    from loader import _nearby_numbers

    # Distances from 12: 10->2, 5->7, 1->11, 50->38, 100->88. Closest 3.
    info = {str(i): (f"id-{i}", f"name-{i}") for i in (1, 5, 10, 50, 100)}
    sorted_keys = sorted(info, key=int)

    assert _nearby_numbers("12", sorted_keys, info) == ["10", "5", "1"]


def test_nearby_numbers_non_numeric_target():
    from loader import _nearby_numbers

    info = {"1": ("a", "x")}
    assert _nearby_numbers("SV001", ["1"], info) == []


def test_nearby_numbers_empty_universe():
    from loader import _nearby_numbers

    assert _nearby_numbers("5", [], {}) == []


def test_nearby_numbers_excludes_target_itself():
    from loader import _nearby_numbers

    info = {"5": ("a", "x"), "6": ("b", "y"), "7": ("c", "z")}
    sorted_keys = ["5", "6", "7"]
    out = _nearby_numbers("6", sorted_keys, info)
    assert "6" not in out


# ---------- DB-touching helpers (use db_session directly) ----------


def test_load_aliases_reads_canonical_tables(db_session):
    from loader import _load_aliases

    aliases = _load_aliases(db_session)
    assert "Near Mint" in aliases["condition"]
    assert aliases["condition"]["Near Mint"] == "NM"
    assert "Holofoil" in aliases["variant"]
    assert aliases["variant"]["Holofoil"] == "holofoil"


def test_load_rarity_aliases_reads_table(db_session):
    from loader import _load_rarity_aliases

    aliases = _load_rarity_aliases(db_session)
    assert aliases["Common"] == "common"
    assert aliases["Hyper rare"] == "hyper_rare"


def test_upsert_set_inserts_and_then_updates(db_session):
    """Calling upsert_set twice with different name updates the same row."""
    from loader import upsert_set

    upsert_set(
        db_session,
        {
            "id": "loader_t1",
            "name": "Original",
            "serie": {"name": "Series"},
            "cardCount": {"official": 100},
            "releaseDate": "2020-01-01",
            "symbol": "https://x.com/s",
            "logo": "https://x.com/l",
        },
    )
    upsert_set(
        db_session,
        {
            "id": "loader_t1",
            "name": "Renamed",
            "serie": {"name": "Series"},
            "cardCount": {"official": 100},
            "releaseDate": None,
            "symbol": None,
            "logo": None,
        },
    )

    row = db_session.execute(
        text("SELECT name, release_date FROM sets WHERE id = 'loader_t1'")
    ).fetchone()
    assert row.name == "Renamed"
    assert row.release_date is None


def test_upsert_card_with_known_rarity(db_session):
    from loader import upsert_card, upsert_set

    upsert_set(
        db_session,
        {
            "id": "loader_t2", "name": "S", "serie": {"name": "X"},
            "cardCount": {"official": 1}, "releaseDate": None, "symbol": None, "logo": None,
        },
    )
    upsert_card(
        db_session,
        {
            "id": "loader_t2-1", "set": {"id": "loader_t2"},
            "name": "C", "localId": "1", "rarity": "Rare",
            "category": "Pokemon", "image": "https://x.com/img",
        },
        rarity_aliases={"Rare": "rare"},
        unknowns={},
    )

    row = db_session.execute(
        text("SELECT rarity, image_url FROM cards WHERE id = 'loader_t2-1'")
    ).fetchone()
    assert row.rarity == "rare"
    assert row.image_url == "https://x.com/img/low.png"


def test_upsert_card_with_unknown_rarity_records_unknown(db_session):
    from loader import upsert_card, upsert_set

    upsert_set(
        db_session,
        {
            "id": "loader_t3", "name": "S", "serie": {"name": "X"},
            "cardCount": {"official": 1}, "releaseDate": None, "symbol": None, "logo": None,
        },
    )
    unknowns: dict = {}
    upsert_card(
        db_session,
        {
            "id": "loader_t3-1", "set": {"id": "loader_t3"},
            "name": "C", "localId": "1", "rarity": "Mythical Glittering",
            "category": None, "image": None,
        },
        rarity_aliases={"Rare": "rare"},  # doesn't include the raw value
        unknowns=unknowns,
    )

    row = db_session.execute(
        text("SELECT rarity FROM cards WHERE id = 'loader_t3-1'")
    ).fetchone()
    assert row.rarity is None
    assert unknowns == {("rarity", "Mythical Glittering"): 1}


def test_upsert_card_no_rarity(db_session):
    from loader import upsert_card, upsert_set

    upsert_set(
        db_session,
        {
            "id": "loader_t4", "name": "S", "serie": {"name": "X"},
            "cardCount": {"official": 1}, "releaseDate": None, "symbol": None, "logo": None,
        },
    )
    upsert_card(
        db_session,
        {
            "id": "loader_t4-1", "set": {"id": "loader_t4"},
            "name": "C", "localId": "1", "rarity": None,
            "category": None, "image": None,
        },
        rarity_aliases={},
        unknowns={},
    )
    row = db_session.execute(
        text("SELECT rarity, image_url FROM cards WHERE id = 'loader_t4-1'")
    ).fetchone()
    assert row.rarity is None
    assert row.image_url is None


def test_upsert_card_unknown_rarity_without_unknowns_dict(db_session):
    """Unknown raw rarity + unknowns=None still inserts NULL silently."""
    from loader import upsert_card, upsert_set

    upsert_set(
        db_session,
        {
            "id": "loader_t6", "name": "S", "serie": {"name": "X"},
            "cardCount": {"official": 1}, "releaseDate": None, "symbol": None, "logo": None,
        },
    )
    upsert_card(
        db_session,
        {
            "id": "loader_t6-1", "set": {"id": "loader_t6"},
            "name": "C", "localId": "1", "rarity": "Imaginary",
            "category": None, "image": None,
        },
        rarity_aliases={"Rare": "rare"},
        unknowns=None,  # exercises the `if unknowns is not None` False branch
    )
    row = db_session.execute(
        text("SELECT rarity FROM cards WHERE id = 'loader_t6-1'")
    ).fetchone()
    assert row.rarity is None


def test_upsert_card_no_aliases_passes_through_raw(db_session):
    """Calling without rarity_aliases keeps the raw value (legacy path)."""
    from loader import upsert_card, upsert_set

    upsert_set(
        db_session,
        {
            "id": "loader_t5", "name": "S", "serie": {"name": "X"},
            "cardCount": {"official": 1}, "releaseDate": None, "symbol": None, "logo": None,
        },
    )
    # Use a raw value that matches an existing canonical so the FK is happy.
    upsert_card(
        db_session,
        {
            "id": "loader_t5-1", "set": {"id": "loader_t5"},
            "name": "C", "localId": "1", "rarity": "common",
            "category": None, "image": None,
        },
        rarity_aliases=None,
        unknowns=None,
    )
    row = db_session.execute(text("SELECT rarity FROM cards WHERE id = 'loader_t5-1'")).fetchone()
    assert row.rarity == "common"


def test_bulk_insert_snapshots_writes_rows(db_session):
    from loader import _bulk_insert_snapshots

    # Set + card to satisfy FKs.
    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, created_at) "
            "VALUES ('loader_b', 'B', 'X', 1, NOW())"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO cards (id, set_id, name, number, created_at) "
            "VALUES ('loader_b-1', 'loader_b', 'C', '1', NOW())"
        )
    )

    rows = [
        {
            "card_id": "loader_b-1", "source": "tcgplayer",
            "condition": "NM", "variant": None, "market_price": "10.00",
            "low_price": None, "high_price": None,
            "captured_date": date(2026, 5, 1),
        },
        {
            "card_id": "loader_b-1", "source": "tcgplayer",
            "condition": "NM", "variant": "holofoil", "market_price": "20.00",
            "low_price": None, "high_price": None,
            "captured_date": None,
        },
    ]
    _bulk_insert_snapshots(db_session, rows)

    count = db_session.execute(
        text("SELECT COUNT(*) FROM price_snapshots WHERE card_id = 'loader_b-1'")
    ).scalar()
    assert count == 2


def test_bulk_insert_snapshots_empty_is_noop(db_session):
    from loader import _bulk_insert_snapshots

    _bulk_insert_snapshots(db_session, [])  # Must not raise.


# ---------- _build_snapshot_rows: pure but lots of branches ----------


def _aliases_fixture():
    return {
        "condition": {"Near Mint": "NM", "Lightly Played": "LP", "psa10": "PSA-10"},
        "variant": {"Holofoil": "holofoil", "Normal": None},
    }


def test_build_snapshot_rows_history_path():
    from loader import _build_snapshot_rows

    card = {
        "priceHistory": {
            "variants": {
                "Holofoil": {
                    "Near Mint": {
                        "history": [
                            {"date": "2026-04-01T12:00", "market": 50.0},
                            {"date": "2026-05-01T12:00", "market": 55.0},
                        ],
                        "latestPrice": 60.0,
                    },
                },
            },
        },
    }
    rows = _build_snapshot_rows("c1", card, _aliases_fixture())
    # 2 history rows + 1 latestPrice row.
    assert len(rows) == 3
    assert all(r["card_id"] == "c1" for r in rows)
    assert all(r["variant"] == "holofoil" for r in rows)
    assert all(r["condition"] == "NM" for r in rows)
    # Latest row has captured_date=None so the INSERT uses CURRENT_DATE.
    assert any(r["captured_date"] is None for r in rows)


def test_build_snapshot_rows_skips_unknown_variant_and_condition():
    from loader import _build_snapshot_rows

    card = {
        "priceHistory": {
            "variants": {
                "MysteryFoil": {  # not in aliases -> skip whole bucket
                    "Near Mint": {"history": [], "latestPrice": 1.0},
                },
                "Holofoil": {
                    "Mystery Condition": {  # not in aliases -> skip
                        "history": [], "latestPrice": 1.0,
                    },
                },
            },
        },
    }
    unknowns: dict = {}
    rows = _build_snapshot_rows("c1", card, _aliases_fixture(), unknowns)
    assert rows == []
    assert ("variant", "MysteryFoil") in unknowns
    assert ("condition", "Mystery Condition") in unknowns


def test_build_snapshot_rows_skips_malformed_inner_structures():
    """Non-dict variants/conditions/history points are silently skipped."""
    from loader import _build_snapshot_rows

    card = {
        "priceHistory": {
            "variants": {
                "Holofoil": "not-a-dict",  # skip
            },
        },
    }
    assert _build_snapshot_rows("c1", card, _aliases_fixture()) == []

    card = {
        "priceHistory": {
            "variants": {
                "Holofoil": {
                    "Near Mint": "not-a-dict",  # skip
                },
            },
        },
    }
    assert _build_snapshot_rows("c1", card, _aliases_fixture()) == []

    card = {
        "priceHistory": {
            "variants": {
                "Holofoil": {
                    "Near Mint": {
                        "history": ["not-a-dict", {"date": "", "market": None}, {"date": None, "market": None}],
                        "latestPrice": None,  # falsy, no latest row
                    },
                },
            },
        },
    }
    assert _build_snapshot_rows("c1", card, _aliases_fixture()) == []


def test_build_snapshot_rows_history_present_but_empty_falls_back():
    """priceHistory key exists but variants is empty -> fall back to prices."""
    from loader import _build_snapshot_rows

    card = {
        "priceHistory": {"variants": {}},
        "prices": {"market": 1.5, "low": 1.0, "high": 2.0},
    }
    rows = _build_snapshot_rows("c1", card, _aliases_fixture())
    assert len(rows) == 1
    assert rows[0]["market_price"] == 1.5
    assert rows[0]["low_price"] == 1.0
    assert rows[0]["high_price"] == 2.0


def test_build_snapshot_rows_prices_variants_path():
    """No history; prices.variants supplies per-variant current prices."""
    from loader import _build_snapshot_rows

    card = {
        "prices": {
            "variants": {
                "Holofoil": {
                    "Near Mint": {"price": 50.0},
                    "Lightly Played": {"price": 40.0},
                    "Mystery": "skip-non-dict",  # non-dict cond -> skipped
                    "Heavily Played": {"price": None},  # no price -> skipped
                },
                "MysteryFoil": {  # unknown variant -> entire bucket skipped
                    "Near Mint": {"price": 99.0},
                },
            },
        },
    }
    rows = _build_snapshot_rows("c1", card, _aliases_fixture())
    assert {(r["condition"], r["market_price"]) for r in rows} == {
        ("NM", 50.0), ("LP", 40.0),
    }


def test_build_snapshot_rows_prices_variants_skips_non_dict_variant():
    from loader import _build_snapshot_rows

    card = {"prices": {"variants": {"Holofoil": "not-a-dict"}}}
    assert _build_snapshot_rows("c1", card, _aliases_fixture()) == []


def test_build_snapshot_rows_prices_variants_skips_unknown_condition():
    from loader import _build_snapshot_rows

    card = {
        "prices": {
            "variants": {
                "Holofoil": {"Mystery": {"price": 1.0}},
            },
        },
    }
    unknowns: dict = {}
    rows = _build_snapshot_rows("c1", card, _aliases_fixture(), unknowns)
    assert rows == []
    assert ("condition", "Mystery") in unknowns


def test_build_snapshot_rows_bare_market_fallback():
    """No priceHistory, no prices.variants -> single NM/null row from market."""
    from loader import _build_snapshot_rows

    card = {"prices": {"market": 7.0, "low": 5.0, "high": 9.0}}
    rows = _build_snapshot_rows("c1", card, _aliases_fixture())
    assert len(rows) == 1
    row = rows[0]
    assert row["condition"] == "NM"
    assert row["variant"] is None
    assert row["market_price"] == 7.0


def test_build_snapshot_rows_no_data_returns_empty():
    """Card with absolutely no price data -> []."""
    from loader import _build_snapshot_rows

    assert _build_snapshot_rows("c1", {}, _aliases_fixture()) == []


def test_build_snapshot_rows_ebay_known_graders():
    from loader import _build_snapshot_rows

    card = {
        "ebay": {
            "psa10": {"avg": 100.0},
            "bgs95": {"avg": 90.0},
            "cgc10": {"avg": 95.0},
            "psa9": "not-a-dict",  # skipped
            "bgs10": {"avg": None},  # skipped
        },
    }
    aliases = _aliases_fixture()
    aliases["condition"].update({"bgs95": "BGS-9.5", "cgc10": "CGC-10"})
    rows = _build_snapshot_rows("c1", card, aliases)
    sources = {(r["source"], r["condition"]) for r in rows}
    assert sources == {("psa", "PSA-10"), ("bgs", "BGS-9.5"), ("cgc", "CGC-10")}


def test_build_snapshot_rows_ebay_unknown_grader_falls_back_to_ebay_source():
    """An unknown prefix on ebay key uses 'ebay' as source after alias lookup."""
    from loader import _build_snapshot_rows

    card = {"ebay": {"weird10": {"avg": 50.0}}}
    aliases = _aliases_fixture()
    aliases["condition"]["weird10"] = "PSA-10"  # alias matches
    rows = _build_snapshot_rows("c1", card, aliases)
    assert rows[0]["source"] == "ebay"


def test_build_snapshot_rows_ebay_unknown_alias_skipped():
    from loader import _build_snapshot_rows

    card = {"ebay": {"unknownGrade": {"avg": 50.0}}}
    unknowns: dict = {}
    rows = _build_snapshot_rows("c1", card, _aliases_fixture(), unknowns)
    assert rows == []
    assert ("condition", "unknownGrade") in unknowns


def test_build_snapshot_rows_unknowns_default_empty():
    """When unknowns is None, the function still runs without erroring."""
    from loader import _build_snapshot_rows

    card = {"prices": {"market": 1.0}}
    rows = _build_snapshot_rows("c1", card, _aliases_fixture(), None)
    assert len(rows) == 1


# ---------- load_set with patched engine ----------


@pytest.fixture
def loader_engine_in_test(db_session, monkeypatch):
    """
    Bind loader.engine to db_session's underlying connection so writes done
    inside load_set / insert_price_snapshots happen within the same outer
    transaction db_session rolls back at teardown.

    SQLAlchemy supports `Session(connection)`; the inner `session.begin()`
    starts a SAVEPOINT instead of a real transaction when an outer one is
    open, which is exactly what we want for test isolation.
    """
    import loader

    monkeypatch.setattr(loader, "engine", db_session.connection())
    yield


def test_load_set_writes_set_and_cards(db_session, loader_engine_in_test):
    from loader import load_set

    set_data = {
        "id": "loader_full", "name": "Full Set",
        "serie": {"name": "Series"},
        "cardCount": {"official": 2},
        "releaseDate": "2020-01-01",
        "symbol": "https://x.com/symbol",
        "logo": "https://x.com/logo",
    }
    cards = [
        {
            "id": "loader_full-1", "set": {"id": "loader_full"},
            "name": "A", "localId": "1", "rarity": "Common",
            "category": "Pokemon", "image": "https://x.com/1",
        },
        {
            "id": "loader_full-2", "set": {"id": "loader_full"},
            "name": "B", "localId": "2", "rarity": "Common",
            "category": "Pokemon", "image": "https://x.com/2",
        },
    ]
    stats = load_set(set_data, cards)
    assert stats["cards_upserted"] == 2
    assert stats["unknowns"] == {}

    count = db_session.execute(
        text("SELECT COUNT(*) FROM cards WHERE set_id = 'loader_full'")
    ).scalar()
    assert count == 2


def test_load_set_collects_rarity_unknowns(db_session, loader_engine_in_test):
    from loader import load_set

    set_data = {
        "id": "loader_unk", "name": "U",
        "serie": {"name": "S"}, "cardCount": {"official": 1},
        "releaseDate": None, "symbol": None, "logo": None,
    }
    cards = [
        {
            "id": "loader_unk-1", "set": {"id": "loader_unk"},
            "name": "A", "localId": "1", "rarity": "FAKERARITY",
            "category": None, "image": None,
        },
    ]
    stats = load_set(set_data, cards)
    assert stats["unknowns"] == {("rarity", "FAKERARITY"): 1}


def test_load_set_propagates_errors(monkeypatch):
    """Exceptions raised during the transaction are logged and re-raised.

    This test patches _load_rarity_aliases to raise so we can prove the
    re-raise path without polluting the test DB or destabilising the
    shared connection used by other tests.
    """
    import loader

    monkeypatch.setattr(
        loader,
        "_load_rarity_aliases",
        lambda *_: (_ for _ in ()).throw(RuntimeError("alias load failed")),
    )

    set_data = {
        "id": "loader_err", "name": "E",
        "serie": {"name": "S"}, "cardCount": {"official": 0},
        "releaseDate": None, "symbol": None, "logo": None,
    }
    with pytest.raises(RuntimeError, match="alias load failed"):
        loader.load_set(set_data, [])


# ---------- insert_price_snapshots ----------


def _seed_set_and_cards(db_session, set_id="loader_ips"):
    """Insert a parent set and a few numbered cards for snapshot tests."""
    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, created_at) "
            "VALUES (:id, 'X', 'S', 5, NOW())"
        ),
        {"id": set_id},
    )
    for n in (1, 2, 3, 5, 10):
        db_session.execute(
            text(
                "INSERT INTO cards (id, set_id, name, number, created_at) "
                "VALUES (:cid, :sid, :name, :num, NOW())"
            ),
            {"cid": f"{set_id}-{n}", "sid": set_id, "name": f"Card {n}", "num": str(n)},
        )


def test_insert_price_snapshots_matches_and_writes(db_session, loader_engine_in_test):
    from loader import insert_price_snapshots

    _seed_set_and_cards(db_session)
    ppt_cards = [
        {
            "name": "Card 1", "cardNumber": "1/102",
            "priceHistory": {
                "variants": {
                    "Holofoil": {
                        "Near Mint": {
                            "history": [{"date": "2026-04-01T12:00", "market": 10.0}],
                            "latestPrice": 11.0,
                        },
                    },
                },
            },
        },
    ]
    stats = insert_price_snapshots(ppt_cards, "loader_ips")
    assert stats["matched"] == 1
    assert stats["skipped"] == 0
    assert stats["errors"] == 0


def test_insert_price_snapshots_no_match_records_skip(db_session, loader_engine_in_test):
    from loader import insert_price_snapshots

    _seed_set_and_cards(db_session)
    ppt_cards = [
        {"name": "Ghost", "cardNumber": "999"},  # number not in our DB
    ]
    stats = insert_price_snapshots(ppt_cards, "loader_ips")
    assert stats["matched"] == 0
    assert stats["skipped"] == 1
    assert stats["skipped_cards"][0][2] == "no match"


def test_insert_price_snapshots_no_match_when_cardnumber_missing(db_session, loader_engine_in_test):
    """A missing cardNumber falls through to the no-match path. The actual
    `if not card_number:` branch in the loader is structurally unreachable
    (covered by # pragma: no cover) because `lstrip("0") or "0"` always
    returns a non-empty string -- so we land on the no-match arm instead."""
    from loader import insert_price_snapshots

    _seed_set_and_cards(db_session)
    stats = insert_price_snapshots([{"name": "Numberless"}], "loader_ips")
    assert stats["skipped"] == 1
    assert stats["skipped_cards"][0][2] == "no match"


def test_insert_price_snapshots_matched_but_no_price_data(db_session, loader_engine_in_test):
    from loader import insert_price_snapshots

    _seed_set_and_cards(db_session)
    # Match by number 1 but provide no priceHistory and no prices.
    ppt_cards = [{"name": "Card 1", "cardNumber": "1"}]
    stats = insert_price_snapshots(ppt_cards, "loader_ips")
    assert stats["matched"] == 0
    assert stats["skipped"] == 1
    assert stats["skipped_cards"][0][2] == "no price data"


def test_insert_price_snapshots_swallows_per_card_errors(db_session, loader_engine_in_test, monkeypatch):
    """An exception inside _build_snapshot_rows increments errors but lets
    the run continue with the rest of the cards."""
    import loader

    _seed_set_and_cards(db_session)

    def boom(*args, **kwargs):
        raise RuntimeError("explode")

    monkeypatch.setattr(loader, "_build_snapshot_rows", boom)

    ppt_cards = [
        {"name": "Card 1", "cardNumber": "1"},
        {"name": "Card 2", "cardNumber": "2"},
    ]
    stats = loader.insert_price_snapshots(ppt_cards, "loader_ips")
    assert stats["errors"] == 2
    assert stats["matched"] == 0


def test_insert_price_snapshots_propagates_outer_failure(db_session, loader_engine_in_test, monkeypatch):
    """An exception OUTSIDE the per-card loop raises out of the function."""
    import loader

    # Patch _load_aliases to fail before the loop even starts.
    monkeypatch.setattr(loader, "_load_aliases", lambda *_: (_ for _ in ()).throw(RuntimeError("db error")))

    with pytest.raises(RuntimeError, match="db error"):
        loader.insert_price_snapshots([], "anyset")


def test_insert_price_snapshots_zero_padded_numbers_match(db_session, loader_engine_in_test):
    """Cards with zero-padded numbers in the DB still match unpadded PPT input."""
    from loader import insert_price_snapshots

    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, created_at) "
            "VALUES ('loader_pad', 'X', 'S', 1, NOW())"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO cards (id, set_id, name, number, created_at) "
            "VALUES ('loader_pad-1', 'loader_pad', 'X', '001', NOW())"
        )
    )
    ppt_cards = [
        {
            "name": "X", "cardNumber": "1",
            "prices": {"market": 5.0},
        },
    ]
    stats = insert_price_snapshots(ppt_cards, "loader_pad")
    assert stats["matched"] == 1


def test_module_imports_at_top_level(monkeypatch):
    """Importing loader sets up engine via DATABASE_URL."""
    import importlib

    import loader

    importlib.reload(loader)
    assert loader.engine is not None
    # Sanity: datetime import is the ddl path used by _parse_date.
    assert datetime.strptime("2024-01-01", "%Y-%m-%d").year == 2024


# ---------------------------------------------------------------------------
# Conflict-key deduplication
#
# Postgres rejects an ON CONFLICT DO UPDATE statement that proposes the
# same constrained values twice, and it rejects the whole statement --
# so one duplicate loses every row for that card. This surfaced in
# production the first time price history was enabled.
# ---------------------------------------------------------------------------


def test_dedupe_collapses_history_point_and_latest_price():
    """The row builder emits a history point for today AND a latestPrice
    row dated None (CURRENT_DATE). PPT's history includes today, so those
    two collide -- this was the live failure."""
    from datetime import date as _date

    from loader import _dedupe_by_conflict_key

    today = _date.today().isoformat()
    rows = [
        {"card_id": "c1", "source": "tcgplayer", "condition": "LP",
         "variant": "holofoil", "market_price": 40.6, "captured_date": today},
        {"card_id": "c1", "source": "tcgplayer", "condition": "LP",
         "variant": "holofoil", "market_price": 41.9, "captured_date": None},
    ]
    out = _dedupe_by_conflict_key(rows)
    assert len(out) == 1
    # Later row wins: latestPrice is the fresher of the two numbers.
    assert out[0]["market_price"] == 41.9


def test_dedupe_treats_date_objects_and_iso_strings_as_equal():
    """Callers are inconsistent about date types. Comparing them raw
    would let a genuine duplicate through."""
    from datetime import date as _date

    from loader import _dedupe_by_conflict_key

    rows = [
        {"card_id": "c1", "source": "tcgplayer", "condition": "NM",
         "variant": None, "market_price": 1, "captured_date": _date(2026, 5, 1)},
        {"card_id": "c1", "source": "tcgplayer", "condition": "NM",
         "variant": None, "market_price": 2, "captured_date": "2026-05-01"},
    ]
    assert len(_dedupe_by_conflict_key(rows)) == 1


def test_dedupe_collapses_variants_that_normalize_together():
    """Two raw variant strings can normalize to one canonical value,
    which collides the same way."""
    from loader import _dedupe_by_conflict_key

    rows = [
        {"card_id": "c1", "source": "tcgplayer", "condition": "NM",
         "variant": "holofoil", "market_price": 1, "captured_date": "2026-05-01"},
        {"card_id": "c1", "source": "tcgplayer", "condition": "NM",
         "variant": "holofoil", "market_price": 2, "captured_date": "2026-05-01"},
    ]
    assert len(_dedupe_by_conflict_key(rows)) == 1


def test_dedupe_keeps_genuinely_distinct_rows():
    """Every component of the conflict key must actually discriminate."""
    from loader import _dedupe_by_conflict_key

    base = {"card_id": "c1", "source": "tcgplayer", "condition": "NM",
            "variant": None, "market_price": 1, "captured_date": "2026-05-01"}
    rows = [
        base,
        {**base, "card_id": "c2"},
        {**base, "condition": "LP"},
        {**base, "variant": "holofoil"},
        {**base, "captured_date": "2026-05-02"},
        {**base, "source": "other"},
    ]
    assert len(_dedupe_by_conflict_key(rows)) == 6


def test_dedupe_empty_input():
    from loader import _dedupe_by_conflict_key

    assert _dedupe_by_conflict_key([]) == []


def test_bulk_insert_survives_duplicate_conflict_keys(db_session):
    """Regression for the live failure: a duplicated conflict key used to
    abort the whole statement with CardinalityViolation, rolling back
    every row for the card and leaving the watermark unmoved, so the run
    retried the same doomed batch forever."""
    from datetime import date as _date

    from loader import _bulk_insert_snapshots

    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, created_at) "
            "VALUES ('loader_dup', 'D', 'X', 1, NOW())"
        )
    )
    db_session.execute(
        text(
            "INSERT INTO cards (id, set_id, name, number, created_at) "
            "VALUES ('loader_dup-1', 'loader_dup', 'C', '1', NOW())"
        )
    )

    today = _date.today().isoformat()
    rows = [
        {"card_id": "loader_dup-1", "source": "tcgplayer", "condition": "LP",
         "variant": "holofoil", "market_price": "40.60", "low_price": None,
         "high_price": None, "captured_date": today},
        {"card_id": "loader_dup-1", "source": "tcgplayer", "condition": "LP",
         "variant": "holofoil", "market_price": "41.90", "low_price": None,
         "high_price": None, "captured_date": None},
    ]
    _bulk_insert_snapshots(db_session, rows)  # Must not raise.

    row = db_session.execute(
        text(
            "SELECT market_price FROM price_snapshots "
            "WHERE card_id = 'loader_dup-1'"
        )
    ).fetchall()
    assert len(row) == 1
    assert float(row[0].market_price) == 41.90


# --- identity-only card ingest ---------------------------------------------


def _seed_detailed_card(db_session, card_id="idt-1", set_id="idt_set"):
    """A fully-populated set + card, as the priced sets look in production."""
    db_session.execute(
        text(
            "INSERT INTO sets (id, name, series, printed_total, created_at) "
            "VALUES (:sid, 'Identity Set', 'X', 10, NOW()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"sid": set_id},
    )
    db_session.execute(
        text(
            "INSERT INTO cards (id, set_id, name, number, rarity, supertype, image_url, created_at) "
            "VALUES (:cid, :sid, 'Old Name', '1', 'rare', 'Pokemon', 'http://img/low.png', NOW())"
        ),
        {"cid": card_id, "sid": set_id},
    )


def test_identity_upsert_preserves_rarity_supertype_and_image(db_session):
    """The reason this function exists instead of reusing upsert_card.

    Brief cards from the set-detail endpoint carry no rarity, no category,
    and often no image key at all. Reusing upsert_card's ON CONFLICT clause
    would write EXCLUDED.rarity -- i.e. NULL -- over every card of every
    priced set the first time a catalogue walk ran.
    """
    from loader import upsert_cards_identity

    _seed_detailed_card(db_session)

    stats = upsert_cards_identity(
        db_session,
        "idt_set",
        # Exactly what /sets/{id} sends: no rarity, no category, no "image".
        [{"id": "idt-1", "name": "New Name", "localId": "7"}],
    )

    assert stats["cards_upserted"] == 1
    row = db_session.execute(
        text("SELECT name, number, rarity, supertype, image_url FROM cards WHERE id = 'idt-1'")
    ).fetchone()
    # Identity fields updated...
    assert row.name == "New Name"
    assert row.number == "7"
    # ...and the expensive metadata untouched.
    assert row.rarity == "rare"
    assert row.supertype == "Pokemon"
    assert row.image_url == "http://img/low.png"


def test_identity_upsert_inserts_new_cards_with_null_metadata(db_session):
    """A card we have never seen gets identity only; rarity stays NULL."""
    from loader import upsert_cards_identity

    _seed_detailed_card(db_session)

    upsert_cards_identity(
        db_session, "idt_set",
        [{"id": "idt-new", "name": "Fresh", "localId": "9", "image": "http://i/x"}],
    )

    row = db_session.execute(
        text("SELECT name, number, rarity, supertype, image_url FROM cards WHERE id = 'idt-new'")
    ).fetchone()
    assert row.name == "Fresh"
    assert row.number == "9"
    assert row.rarity is None
    assert row.supertype is None
    assert row.image_url == "http://i/x/low.png"


def test_identity_upsert_empty_list_is_a_no_op(db_session):
    from loader import upsert_cards_identity

    assert upsert_cards_identity(db_session, "idt_set", []) == {
        "cards_upserted": 0, "duplicates_skipped": 0, "malformed_skipped": 0,
    }


def test_identity_upsert_dedupes_repeated_ids(db_session):
    """A repeated id in one multi-row INSERT would abort the whole statement."""
    from loader import upsert_cards_identity

    _seed_detailed_card(db_session)

    stats = upsert_cards_identity(
        db_session, "idt_set",
        [
            {"id": "idt-dup", "name": "First", "localId": "1"},
            {"id": "idt-dup", "name": "Second", "localId": "2"},
        ],
    )

    assert stats["cards_upserted"] == 1
    assert stats["duplicates_skipped"] == 1
    # Last one wins.
    row = db_session.execute(
        text("SELECT name FROM cards WHERE id = 'idt-dup'")
    ).fetchone()
    assert row.name == "Second"


def test_identity_upsert_skips_malformed_briefs(db_session):
    """cards.name and cards.number are NOT NULL; one bad brief must not
    abort the ~300 good cards sharing its statement."""
    from loader import upsert_cards_identity

    _seed_detailed_card(db_session)

    stats = upsert_cards_identity(
        db_session, "idt_set",
        [
            {"id": "idt-ok", "name": "Good", "localId": "1"},
            {"id": "idt-bad"},                                  # no name/localId
            {"name": "No id", "localId": "2"},                  # no id
            {"id": "idt-bad2", "name": "No localId"},           # no localId
        ],
    )

    assert stats["cards_upserted"] == 1
    assert stats["malformed_skipped"] == 3


def test_identity_upsert_all_malformed_returns_early(db_session):
    """Every brief rejected -- no statement should be issued at all."""
    from loader import upsert_cards_identity

    stats = upsert_cards_identity(db_session, "idt_set", [{"nope": True}])
    assert stats == {
        "cards_upserted": 0, "duplicates_skipped": 0, "malformed_skipped": 1,
    }


def test_card_image_url_handles_missing_and_present():
    from loader import _card_image_url

    assert _card_image_url({"image": "http://i/x"}) == "http://i/x/low.png"
    assert _card_image_url({"image": None}) is None
    assert _card_image_url({}) is None


# --- upsert_set robustness --------------------------------------------------


def test_upsert_set_falls_back_when_series_and_count_are_missing(db_session, caplog):
    """series and printed_total are NOT NULL. A malformed payload must not
    turn a KeyError into an IntegrityError that rolls back the whole set."""
    import logging

    from loader import upsert_set

    with caplog.at_level(logging.WARNING):
        upsert_set(db_session, {"id": "idt_bare", "name": "Bare"})

    row = db_session.execute(
        text("SELECT series, printed_total FROM sets WHERE id = 'idt_bare'")
    ).fetchone()
    assert row.series == "Unknown"
    assert row.printed_total == 0
    assert "missing serie.name" in caplog.text


def test_upsert_set_uses_total_when_official_is_absent(db_session):
    """cardCount.total is a worse answer than .official but a far better one
    than refusing to store the set."""
    from loader import upsert_set

    upsert_set(db_session, {
        "id": "idt_tot", "name": "Totals",
        "serie": {"name": "S"}, "cardCount": {"total": 42},
    })

    row = db_session.execute(
        text("SELECT printed_total FROM sets WHERE id = 'idt_tot'")
    ).fetchone()
    assert row.printed_total == 42


def test_upsert_set_does_not_clobber_stored_values_with_placeholders(db_session):
    """On UPDATE the prior row is the better answer than 'Unknown'/0."""
    from loader import upsert_set

    upsert_set(db_session, {
        "id": "idt_keep", "name": "Keep",
        "serie": {"name": "Real Series"}, "cardCount": {"official": 99},
    })
    # Second pass with a degraded payload, as a flaky TCGdex response.
    upsert_set(db_session, {"id": "idt_keep", "name": "Keep Renamed"})

    row = db_session.execute(
        text("SELECT name, series, printed_total FROM sets WHERE id = 'idt_keep'")
    ).fetchone()
    assert row.name == "Keep Renamed"
    assert row.series == "Real Series"
    assert row.printed_total == 99


def test_load_set_identity_commits_and_reports(db_session, loader_engine_in_test):
    from loader import load_set_identity

    result = load_set_identity({
        "id": "idt_load", "name": "Loaded",
        "serie": {"name": "S"}, "cardCount": {"official": 2},
        "cards": [
            {"id": "idt_load-1", "name": "One", "localId": "1"},
            {"id": "idt_load-2", "name": "Two", "localId": "2"},
        ],
    })

    assert result["set_id"] == "idt_load"
    assert result["cards_upserted"] == 2
    count = db_session.execute(
        text("SELECT count(*) FROM cards WHERE set_id = 'idt_load'")
    ).scalar()
    assert count == 2


def test_load_set_identity_handles_a_set_with_no_cards(db_session, loader_engine_in_test):
    from loader import load_set_identity

    result = load_set_identity({
        "id": "idt_empty", "name": "Empty",
        "serie": {"name": "S"}, "cardCount": {"official": 0},
    })
    assert result["cards_upserted"] == 0


def test_load_set_identity_reraises_and_rolls_back(db_session, loader_engine_in_test):
    """A set that blows up mid-transaction leaves nothing behind, so one bad
    set in a 218-set walk cannot half-write itself."""
    import pytest

    from loader import load_set_identity

    # upsert_set indexes set_data["name"] directly -- name is NOT NULL and
    # universally present, so its absence is a genuine payload fault. It
    # raises after the transaction has opened.
    with pytest.raises(KeyError):
        load_set_identity({
            "id": "idt_bad",
            "serie": {"name": "S"}, "cardCount": {"official": 1},
            "cards": [{"id": "idt_bad-1", "name": "C", "localId": "1"}],
        })

    count = db_session.execute(
        text("SELECT count(*) FROM sets WHERE id = 'idt_bad'")
    ).scalar()
    assert count == 0
