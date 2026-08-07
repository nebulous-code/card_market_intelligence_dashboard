"""
Reconcile priced_sets.yml into the set_identifiers table.

set_identifiers is what actually gates spend: run.py resolves a set's
PokemonPriceTracker name before making any HTTP call and skips the set at
zero credit cost when no mapping exists. That works well but is invisible --
the list of sets we pay for lives in a database table nobody reads.

This module makes the YAML file the readable source and generates those rows
from it, so adding a set is a one-line commit rather than a hand-written
INSERT against production.
"""

import logging
from pathlib import Path
from typing import Any

import yaml
from set_resolver import (
    SOURCE_PPT,
    SOURCE_TCGDEX,
    SetNotFoundError,
    _get_engine,
    upsert_identifier,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

DEFAULT_YAML_PATH = Path(__file__).resolve().parent / "priced_sets.yml"

# Exactly the keys an entry may carry. Anything else is a typo -- "ppt-name"
# and "pptname" would otherwise be silently ignored, and the first sign of
# trouble would be a set quietly not being priced.
_ALLOWED_KEYS = {"set_id", "ppt_name", "tcgdex_id"}
_REQUIRED_KEYS = {"set_id", "ppt_name"}


class PricedSetsError(Exception):
    """Raised when priced_sets.yml is missing, unreadable, or malformed."""


def load_priced_sets(path: Path | None = None) -> list[dict[str, str]]:
    """
    Read and validate priced_sets.yml.

    Validation is deliberately strict. The file is small, hand-edited, and
    every entry represents money; a typo that silently drops a set is worse
    than a loud failure that stops the sync.

    Args:
        path: Override for the YAML location. Defaults to the file next to
            this module.

    Returns:
        list[dict]: One dict per entry with keys set_id, ppt_name, tcgdex_id.
            tcgdex_id is filled in from set_id when not given.

    Raises:
        PricedSetsError: On any structural or content problem.
    """
    path = path or DEFAULT_YAML_PATH

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise PricedSetsError(f"Could not read {path}: {e}") from e

    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise PricedSetsError(f"{path} is not valid YAML: {e}") from e

    if not isinstance(document, dict):
        raise PricedSetsError(f"{path} must contain a mapping at the top level.")

    entries = document.get("sets")
    if not isinstance(entries, list) or not entries:
        raise PricedSetsError(f"{path} must have a non-empty 'sets' list.")

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise PricedSetsError(f"{path} entry {i} is not a mapping.")

        unknown = set(entry) - _ALLOWED_KEYS
        if unknown:
            raise PricedSetsError(
                f"{path} entry {i} has unrecognized key(s) {sorted(unknown)}. "
                f"Allowed keys are {sorted(_ALLOWED_KEYS)}."
            )

        missing = [k for k in sorted(_REQUIRED_KEYS) if not str(entry.get(k) or "").strip()]
        if missing:
            raise PricedSetsError(f"{path} entry {i} is missing or has blank {missing}.")

        set_id = str(entry["set_id"]).strip()
        if set_id in seen:
            raise PricedSetsError(f"{path} lists set_id {set_id!r} more than once.")
        seen.add(set_id)

        out.append({
            "set_id": set_id,
            "ppt_name": str(entry["ppt_name"]).strip(),
            "tcgdex_id": str(entry.get("tcgdex_id") or set_id).strip(),
        })

    return out


def sync_priced_sets(entries: list[dict[str, str]]) -> dict[str, Any]:
    """
    Write the YAML entries into set_identifiers, in one transaction.

    A set that is not yet in the catalogue is recorded and skipped rather
    than raising. That state is legitimately transient -- a set added to the
    YAML on a night TCGdex was unreachable will exist tomorrow, and the
    catalogue step runs immediately before this one, so the normal case
    heals itself within a single run. Aborting the whole sync over one such
    line would also block every other new set from being priced.

    Args:
        entries: Output of load_priced_sets().

    Returns:
        dict with keys:
            inserted     -- list of (set_id, identifier_type, identifier)
            updated      -- list of (set_id, identifier_type, identifier)
            unchanged    -- count of rows that already matched
            missing_sets -- set_ids absent from the sets table
    """
    inserted: list[tuple[str, str, str]] = []
    updated: list[tuple[str, str, str]] = []
    unchanged = 0
    missing_sets: list[str] = []

    with Session(_get_engine()) as session:
        with session.begin():
            # One query for the whole file rather than one per entry.
            known = {
                r.id for r in session.execute(
                    text("SELECT id FROM sets WHERE id = ANY(:ids)"),
                    {"ids": [e["set_id"] for e in entries]},
                ).fetchall()
            }

            for entry in entries:
                set_id = entry["set_id"]
                if set_id not in known:
                    missing_sets.append(set_id)
                    continue

                # ('tcgdex', 'name') rows are deliberately not synced -- see
                # the note in priced_sets.yml.
                for source, identifier, identifier_type in (
                    (SOURCE_PPT, entry["ppt_name"], "name"),
                    (SOURCE_TCGDEX, entry["tcgdex_id"], "id"),
                ):
                    try:
                        result = upsert_identifier(
                            set_id, source, identifier, identifier_type,
                            session=session,
                        )
                    except SetNotFoundError:  # pragma: no cover -- pre-filtered above
                        missing_sets.append(set_id)
                        break

                    if result == "inserted":
                        inserted.append((set_id, f"{source}/{identifier_type}", identifier))
                    elif result == "updated":
                        updated.append((set_id, f"{source}/{identifier_type}", identifier))
                    else:
                        unchanged += 1

    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "missing_sets": missing_sets,
    }
