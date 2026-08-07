"""
Tests for ingestion/priced_sets.py.

priced_sets.yml is the control on spend: every entry is a set we pay
PokemonPriceTracker to refresh. Validation is deliberately strict, because
a typo that silently drops a set is worse than a loud failure that stops
the sync -- the failure mode of a wrong ppt_name is not an error, it is a
zero-result fetch that looks exactly like a set with no prices.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def cleanup_priced_sets():
    """Reset the resolver's cached engine and clear seed rows."""
    import set_resolver

    set_resolver._engine = None
    yield
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        with session.begin():
            session.execute(text("DELETE FROM set_identifiers WHERE set_id LIKE 'ps_%'"))
            session.execute(text("DELETE FROM sets WHERE id LIKE 'ps_%'"))


def _write(tmp_path, body: str):
    path = tmp_path / "priced_sets.yml"
    path.write_text(body, encoding="utf-8")
    return path


def _seed(set_ids):
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        with session.begin():
            for sid in set_ids:
                session.execute(
                    text(
                        "INSERT INTO sets (id, name, series, printed_total, created_at) "
                        "VALUES (:sid, :name, 'X', 1, NOW()) ON CONFLICT (id) DO NOTHING"
                    ),
                    {"sid": sid, "name": sid.upper()},
                )


# --- loading and validation -------------------------------------------------


def test_loads_entries_and_defaults_tcgdex_id(tmp_path):
    from priced_sets import load_priced_sets

    path = _write(tmp_path, """
sets:
  - set_id: base1
    ppt_name: Base Set
  - set_id: base2
    ppt_name: Jungle
    tcgdex_id: custom2
""")
    entries = load_priced_sets(path)
    assert entries[0] == {"set_id": "base1", "ppt_name": "Base Set", "tcgdex_id": "base1"}
    assert entries[1]["tcgdex_id"] == "custom2"


def test_uses_the_default_path_when_none_given():
    """The shipped file must itself be valid -- this is the guard against
    committing a broken priced_sets.yml."""
    from priced_sets import load_priced_sets

    entries = load_priced_sets()
    assert entries
    assert all(e["set_id"] and e["ppt_name"] for e in entries)


@pytest.mark.parametrize(
    "body, fragment",
    [
        ("just a string\n", "mapping at the top level"),
        ("other_key: 1\n", "non-empty 'sets' list"),
        ("sets: []\n", "non-empty 'sets' list"),
        ("sets:\n  - just a string\n", "is not a mapping"),
        ("sets:\n  - set_id: a\n    ppt_name: A\n    bogus: 1\n", "unrecognized key"),
        ("sets:\n  - ppt_name: A\n", "missing or has blank"),
        ("sets:\n  - set_id: a\n    ppt_name: '  '\n", "missing or has blank"),
        ("sets:\n  - set_id: a\n    ppt_name: A\n  - set_id: a\n    ppt_name: B\n", "more than once"),
    ],
)
def test_rejects_malformed_files(tmp_path, body, fragment):
    from priced_sets import PricedSetsError, load_priced_sets

    with pytest.raises(PricedSetsError) as exc:
        load_priced_sets(_write(tmp_path, body))
    assert fragment in str(exc.value)


def test_rejects_a_missing_file(tmp_path):
    from priced_sets import PricedSetsError, load_priced_sets

    with pytest.raises(PricedSetsError) as exc:
        load_priced_sets(tmp_path / "nope.yml")
    assert "Could not read" in str(exc.value)


def test_rejects_invalid_yaml(tmp_path):
    from priced_sets import PricedSetsError, load_priced_sets

    with pytest.raises(PricedSetsError) as exc:
        load_priced_sets(_write(tmp_path, "sets: [unclosed\n"))
    assert "not valid YAML" in str(exc.value)


# --- syncing ----------------------------------------------------------------


def test_sync_inserts_then_reports_unchanged():
    from priced_sets import sync_priced_sets

    _seed(["ps_a"])
    entries = [{"set_id": "ps_a", "ppt_name": "Set A", "tcgdex_id": "ps_a"}]

    first = sync_priced_sets(entries)
    # Two rows per entry: ('ppt','name') and ('tcgdex','id').
    assert len(first["inserted"]) == 2
    assert first["unchanged"] == 0
    assert first["missing_sets"] == []

    second = sync_priced_sets(entries)
    assert second["inserted"] == []
    assert second["unchanged"] == 2


def test_sync_reports_an_updated_ppt_name():
    from priced_sets import sync_priced_sets

    _seed(["ps_b"])
    sync_priced_sets([{"set_id": "ps_b", "ppt_name": "Old", "tcgdex_id": "ps_b"}])
    result = sync_priced_sets([{"set_id": "ps_b", "ppt_name": "New", "tcgdex_id": "ps_b"}])

    assert [r[2] for r in result["updated"]] == ["New"]
    assert result["unchanged"] == 1  # the tcgdex/id row did not change


def test_sync_skips_a_set_that_is_not_catalogued_yet():
    """Transient and self-healing: the catalogue step runs immediately
    before this one, so a set added on a night TCGdex was down resolves
    on the next run. Aborting would block every other new set."""
    from priced_sets import sync_priced_sets

    _seed(["ps_real"])
    result = sync_priced_sets([
        {"set_id": "ps_real", "ppt_name": "Real", "tcgdex_id": "ps_real"},
        {"set_id": "ps_ghost", "ppt_name": "Ghost", "tcgdex_id": "ps_ghost"},
    ])

    assert result["missing_sets"] == ["ps_ghost"]
    # The good entry still went through.
    assert len(result["inserted"]) == 2


def test_sync_does_not_touch_tcgdex_name_aliases():
    """('tcgdex','name') rows are hand-written operator aliases -- they let
    you run an ingest by typing a friendly name and are not derivable from
    the YAML. A naive sync would overwrite them."""
    from priced_sets import sync_priced_sets

    _seed(["ps_alias"])
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as s:
        with s.begin():
            s.execute(text(
                "INSERT INTO set_identifiers (set_id, source, identifier, identifier_type) "
                "VALUES ('ps_alias', 'tcgdex', 'Friendly Name', 'name')"
            ))

    sync_priced_sets([{"set_id": "ps_alias", "ppt_name": "A", "tcgdex_id": "ps_alias"}])

    with Session(engine) as s:
        row = s.execute(text(
            "SELECT identifier FROM set_identifiers WHERE set_id = 'ps_alias' "
            "AND source = 'tcgdex' AND identifier_type = 'name'"
        )).fetchone()
    assert row.identifier == "Friendly Name"
