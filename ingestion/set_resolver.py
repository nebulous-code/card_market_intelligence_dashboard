"""
Set identifier resolver for the ingestion pipeline.

Provides a single lookup function that converts any recognizable form of a
set name or ID into the exact identifier that a given external source expects.
All ingestion scripts must call resolve_identifier() before making any API
call that takes a set name or ID — never pass strings to APIs directly.

Identifier mappings live in the set_identifiers table. To add a new set or
correct a wrong name, insert a row there rather than changing code.
"""

import logging
import os
from typing import Literal

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv(find_dotenv())

log = logging.getLogger(__name__)

# Source constants — use these instead of bare strings to avoid typos.
SOURCE_TCGDEX = "tcgdex"
SOURCE_PPT = "ppt"
SOURCE_TCGPLAYER = "tcgplayer"

# Which identifier_type to return for each source.
# TCGdex is queried by slug ID; PPT and TCGPlayer are queried by display name.
_SOURCE_RETURN_TYPE: dict[str, str] = {
    SOURCE_TCGDEX: "id",
    SOURCE_PPT: "name",
    SOURCE_TCGPLAYER: "name",
}

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    return _engine


class SetIdentifierNotFoundError(Exception):
    """
    Raised when no identifier mapping exists for a given search term and source.

    The error message includes the search term, the source, and exact SQL to
    add the missing mapping so the operator knows exactly how to fix the problem.
    """


# Which identifier_type to return per source.
_RETURN_TYPE: dict[str, str] = {
    SOURCE_TCGDEX: "id",
    SOURCE_PPT: "name",
    SOURCE_TCGPLAYER: "name",
}


def resolve_identifier(search_term: str, source: str) -> str:
    """
    Return the identifier that ``source`` uses for the set matching ``search_term``.

    The lookup matches ``search_term`` case-insensitively against both the
    ``identifier`` column and the ``set_id`` column in ``set_identifiers``.
    The first matching row's identifier for the requested source is returned.

    For TCGdex, returns the ``identifier_type='id'`` value (e.g. ``"base1"``).
    For PPT and TCGPlayer, returns the ``identifier_type='name'`` value
    (e.g. ``"Base Set"``).

    Args:
        search_term: Any recognizable form of the set — the canonical set ID
            (e.g. ``"base1"``), a display name (e.g. ``"Base Set"``), or a
            case-insensitive variant of either.
        source: The data source to resolve for. Use the SOURCE_* constants
            defined in this module (``"tcgdex"``, ``"ppt"``, ``"tcgplayer"``).

    Returns:
        str: The exact identifier the source uses for this set.

    Raises:
        SetIdentifierNotFoundError: If no mapping exists for this search term
            and source combination. The error message includes the SQL needed
            to add the mapping.
    """
    return_type = _RETURN_TYPE.get(source, "name")

    with Session(_get_engine()) as session:
        # Find any set_identifiers row for this source whose identifier or
        # set_id matches search_term (case-insensitive). If found, return the
        # identifier for the requested type (id or name) in the same set.
        row = session.execute(
            text("""
                SELECT si_target.identifier
                FROM set_identifiers si_match
                JOIN set_identifiers si_target
                  ON si_target.set_id = si_match.set_id
                 AND si_target.source = :source
                 AND si_target.identifier_type = :return_type
                WHERE si_match.source = :source
                  AND (
                      LOWER(si_match.identifier) = LOWER(:search_term)
                   OR LOWER(si_match.set_id)     = LOWER(:search_term)
                  )
                LIMIT 1
            """),
            {"source": source, "return_type": return_type, "search_term": search_term},
        ).fetchone()

    if row is not None:
        log.debug("Resolved '%s' for source='%s' → '%s'", search_term, source, row[0])
        return row[0]

    # Build the set_id for the helpful error message. Try to find it via any
    # source so the operator gets a pre-filled INSERT statement.
    with Session(_get_engine()) as session:
        set_id_row = session.execute(
            text("""
                SELECT set_id FROM set_identifiers
                WHERE LOWER(identifier) = LOWER(:search_term)
                   OR LOWER(set_id) = LOWER(:search_term)
                LIMIT 1
            """),
            {"search_term": search_term},
        ).fetchone()

    set_id_hint = set_id_row[0] if set_id_row else "<set_id>"

    raise SetIdentifierNotFoundError(
        f"No identifier found for search_term={search_term!r} source={source!r}.\n\n"
        f"To fix this:\n"
        f"1. Look up the exact name/ID that {source!r} uses for this set.\n"
        f"   For 'ppt': visit https://www.pokemonpricetracker.com and search for the set.\n"
        f"   For 'tcgdex': visit https://tcgdex.dev and find the set ID.\n"
        f"2. Once you have the correct value, add it to the set_identifiers table:\n\n"
        f"   INSERT INTO set_identifiers (set_id, source, identifier, identifier_type)\n"
        f"   VALUES ('{set_id_hint}', '{source}', '<correct value here>', 'name');\n\n"
        f"3. Re-run the ingestion script."
    )


def register_identifier(set_id: str, source: str, identifier: str, identifier_type: str) -> None:
    """
    Insert a new row into set_identifiers.

    Used when an operator has verified a new name and wants to register it
    before running ingestion. Validates that the set exists and that the
    (set_id, source, identifier_type) combination is not already taken.

    Args:
        set_id: The canonical set ID (must exist in the sets table).
        source: The data source (e.g. ``"ppt"``).
        identifier: The name or ID the source uses for this set.
        identifier_type: ``"id"`` or ``"name"``.

    Raises:
        ValueError: If ``set_id`` does not exist in sets, or if the
            (set_id, source, identifier_type) combination already exists.
    """
    with Session(_get_engine()) as session:
        with session.begin():
            set_exists = session.execute(
                text("SELECT 1 FROM sets WHERE id = :set_id"),
                {"set_id": set_id},
            ).fetchone()
            if not set_exists:
                raise ValueError(
                    f"set_id={set_id!r} does not exist in the sets table. "
                    f"Run the TCGdex ingestion for this set first."
                )

            already_exists = session.execute(
                text("""
                    SELECT 1 FROM set_identifiers
                    WHERE set_id = :set_id AND source = :source AND identifier_type = :identifier_type
                """),
                {"set_id": set_id, "source": source, "identifier_type": identifier_type},
            ).fetchone()
            if already_exists:
                raise ValueError(
                    f"A {identifier_type!r} identifier for set_id={set_id!r} source={source!r} "
                    f"already exists. Use UPDATE to change it."
                )

            session.execute(
                text("""
                    INSERT INTO set_identifiers (set_id, source, identifier, identifier_type)
                    VALUES (:set_id, :source, :identifier, :identifier_type)
                """),
                {"set_id": set_id, "source": source, "identifier": identifier, "identifier_type": identifier_type},
            )
            log.info(
                "Registered identifier: set_id=%s source=%s type=%s value=%s",
                set_id, source, identifier_type, identifier,
            )
