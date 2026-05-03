"""
Delete expired collection_sessions rows.

Run from the nightly ingestion workflow after the multiplier refresh.
The /collection/* endpoints filter expired sessions out at read time,
so a missed cleanup is not a correctness issue -- but the table still
grows over time without it. Idempotent: re-running on the same day is
a no-op.
"""

from __future__ import annotations

import logging
import os

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine, text


def main() -> None:
    load_dotenv(find_dotenv())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )
    log = logging.getLogger("cleanup_sessions")

    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM collection_sessions WHERE expires_at < NOW()")
        )
    log.info(
        "Deleted %d expired collection_sessions rows.",
        result.rowcount or 0,
    )


if __name__ == "__main__":
    main()
