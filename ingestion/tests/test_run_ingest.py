"""
Tests for ingestion/run_ingest.py.

main() is called with sys.argv patched, and external dependencies
(resolve_identifier, get_set, get_cards, load_set) are mocked so we
exercise the orchestration without hitting TCGdex or writing to the DB.
"""

import sys

import pytest


def _run_main(monkeypatch, argv):
    """Invoke run_ingest.main with a custom argv list."""
    import run_ingest

    monkeypatch.setattr(sys, "argv", ["run_ingest.py", *argv])
    run_ingest.main()


def test_main_resolves_and_loads_set(monkeypatch, mocker):
    import run_ingest

    resolve = mocker.patch.object(run_ingest, "resolve_identifier", return_value="base1")
    mocker.patch.object(run_ingest, "get_set", return_value={
        "id": "base1", "name": "Base Set", "cards": [{"id": "base1-1"}],
    })
    mocker.patch.object(run_ingest, "get_cards", return_value=[{"id": "base1-1"}])
    load_set = mocker.patch.object(run_ingest, "load_set", return_value={"cards_upserted": 1, "unknowns": {}})

    _run_main(monkeypatch, ["--set-id", "Base Set"])

    resolve.assert_called_once_with("Base Set", run_ingest.SOURCE_TCGDEX)
    load_set.assert_called_once()


def test_main_new_set_bypasses_resolver(monkeypatch, mocker):
    import run_ingest

    resolve = mocker.patch.object(run_ingest, "resolve_identifier")
    mocker.patch.object(run_ingest, "get_set", return_value={"id": "newset", "name": "N", "cards": []})
    mocker.patch.object(run_ingest, "get_cards", return_value=[])
    mocker.patch.object(run_ingest, "load_set", return_value={"cards_upserted": 0, "unknowns": {}})

    _run_main(monkeypatch, ["--set-id", "newset", "--new-set"])

    resolve.assert_not_called()


def test_main_unresolvable_set_id_exits(monkeypatch, mocker):
    import run_ingest

    mocker.patch.object(
        run_ingest, "resolve_identifier",
        side_effect=run_ingest.SetIdentifierNotFoundError("no mapping"),
    )

    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, ["--set-id", "ghost"])
    assert exc.value.code == 1


def test_main_get_set_failure_exits(monkeypatch, mocker):
    import run_ingest

    mocker.patch.object(run_ingest, "resolve_identifier", return_value="base1")
    mocker.patch.object(run_ingest, "get_set", side_effect=RuntimeError("boom"))

    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, ["--set-id", "base1"])
    assert exc.value.code == 1


def test_main_logs_unknown_rarities(monkeypatch, mocker, caplog):
    """Unknown rarities returned by load_set get logged with INSERT snippets."""
    import logging

    import run_ingest

    mocker.patch.object(run_ingest, "resolve_identifier", return_value="base1")
    mocker.patch.object(run_ingest, "get_set", return_value={"id": "base1", "name": "Base", "cards": []})
    mocker.patch.object(run_ingest, "get_cards", return_value=[])
    mocker.patch.object(
        run_ingest, "load_set",
        return_value={"cards_upserted": 0, "unknowns": {("rarity", "Mythic"): 3, ("rarity", "Singleton"): 1}},
    )

    with caplog.at_level(logging.WARNING):
        _run_main(monkeypatch, ["--set-id", "base1"])

    log_text = caplog.text
    assert "Mythic" in log_text
    assert "Singleton" in log_text
    assert "INSERT INTO rarity_aliases" in log_text


def test_main_no_unknowns_no_warning_block(monkeypatch, mocker, caplog):
    import logging

    import run_ingest

    mocker.patch.object(run_ingest, "resolve_identifier", return_value="base1")
    mocker.patch.object(run_ingest, "get_set", return_value={"id": "base1", "name": "Base", "cards": []})
    mocker.patch.object(run_ingest, "get_cards", return_value=[])
    mocker.patch.object(run_ingest, "load_set", return_value={"cards_upserted": 0, "unknowns": {}})

    with caplog.at_level(logging.WARNING):
        _run_main(monkeypatch, ["--set-id", "base1"])

    assert "Unrecognized rarity values" not in caplog.text
