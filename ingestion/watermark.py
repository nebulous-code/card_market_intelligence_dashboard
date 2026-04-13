"""
Watermark read and write logic for the ingestion pipeline.

A watermark is a database row that records the last time a set was
successfully priced by a given source. The ingestion script reads watermarks
at the start of each run to decide which sets need pricing, and writes them
at the end of each successful set ingestion.

The watermark table also tracks whether the one-time historical backfill has
been completed for a set, which is only relevant on the API tier.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Source identifier used in all watermark rows written by this pipeline.
SOURCE = "pokemonpricetracker"


def get_watermark(session: Session, set_id: str) -> Optional[dict]:
    """
    Return the current watermark for a set, or None if it does not exist yet.

    Args:
        session: Active database session.
        set_id: The set ID to look up.

    Returns:
        dict with keys 'last_ingested_at', 'backfilled', and 'updated_at',
        or None if no watermark row exists for this set.
    """
    row = session.execute(
        text("""
            SELECT last_ingested_at, backfilled, last_offset, updated_at
            FROM ingestion_watermarks
            WHERE source = :source AND set_id = :set_id
        """),
        {"source": SOURCE, "set_id": set_id},
    ).fetchone()

    if row is None:
        return None

    return {
        "last_ingested_at": row.last_ingested_at,
        "backfilled": row.backfilled,
        "last_offset": row.last_offset,
        "updated_at": row.updated_at,
    }


def set_watermark(
    session: Session,
    set_id: str,
    backfilled: bool = False,
    last_offset: int = 0,
) -> None:
    """
    Upsert the watermark for a set, recording ingestion progress.

    Sets last_ingested_at to the current UTC time and stores the pagination
    offset reached. When a run completes the full set, pass last_offset=0
    so the next day's run starts from card 1. When a run is interrupted by
    a credit limit, pass the offset where pagination stopped so the next
    run resumes from there rather than re-fetching cards already ingested.

    Args:
        session: Active database session. The caller is responsible for
            committing the transaction.
        set_id: The set ID that was just processed.
        backfilled: Whether the historical backfill is now complete for this
            set. Once set to True, this value is never reset to False.
        last_offset: Pagination offset to resume from on the next run.
            0 means start from the beginning (full set completed, or first run).

    Returns:
        None
    """
    now = datetime.now(timezone.utc)
    log.debug(
        "set_watermark set_id=%s backfilled=%s last_offset=%d at=%s",
        set_id, backfilled, last_offset, now,
    )

    session.execute(
        text("""
            INSERT INTO ingestion_watermarks
                (source, set_id, last_ingested_at, backfilled, last_offset, updated_at)
            VALUES (:source, :set_id, :now, :backfilled, :last_offset, :now)
            ON CONFLICT (source, set_id) DO UPDATE SET
                last_ingested_at = EXCLUDED.last_ingested_at,
                -- Only advance backfilled from False to True, never reverse it.
                backfilled = ingestion_watermarks.backfilled OR EXCLUDED.backfilled,
                last_offset = EXCLUDED.last_offset,
                updated_at = EXCLUDED.updated_at
        """),
        {"source": SOURCE, "set_id": set_id, "now": now, "backfilled": backfilled, "last_offset": last_offset},
    )


def get_all_sets(session: Session) -> list[dict]:
    """
    Return all sets currently in the database, ordered oldest-first.

    Returns both the TCGdex ID (used as the watermark key and database FK)
    and the display name (passed to PokemonPriceTracker, which does not
    know TCGdex IDs and expects the set's display name e.g. "Base Set").

    Sets are ordered by release_date ascending so older sets are processed
    first. Sets with no release date sort last.

    Args:
        session: Active database session.

    Returns:
        list[dict]: Each dict has keys "id" (TCGdex ID) and "name" (display name).
    """
    rows = session.execute(
        text("SELECT id, name FROM sets ORDER BY release_date ASC NULLS LAST")
    ).fetchall()
    return [{"id": row.id, "name": row.name} for row in rows]
