"""
CRUD helpers for the collection_sessions table.

Sessions are anonymous, keyed by a UUID written to a cookie on the
client. They store the parsed collection as JSONB and expire 24 hours
after creation. Anything that touches the table goes through these
helpers so the cookie name, expiry, and JSON shape stay consistent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from schemas.collection import ParsedCollectionRow

SESSION_TTL = timedelta(hours=24)
COOKIE_NAME = "collection_session_id"
COOKIE_MAX_AGE_SECONDS = int(SESSION_TTL.total_seconds())


@dataclass(frozen=True)
class StoredSession:
    """In-memory representation of a row read back from the database."""

    session_id: str
    rows: list[ParsedCollectionRow]
    created_at: datetime
    expires_at: datetime


def create_session(db: Session, rows: list[ParsedCollectionRow]) -> str:
    """Insert a new session row and return its id.

    Caller is responsible for committing the surrounding transaction
    (the get_db dependency yields a non-autocommit session) and for
    setting the cookie on the response.
    """
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + SESSION_TTL
    db.execute(
        text(
            """
            INSERT INTO collection_sessions (id, collection, created_at, expires_at)
            VALUES (:id, CAST(:collection AS JSONB), :created_at, :expires_at)
            """
        ),
        {
            "id": session_id,
            "collection": _serialize_rows(rows),
            "created_at": now,
            "expires_at": expires_at,
        },
    )
    db.commit()
    return session_id


def get_session(db: Session, session_id: str) -> StoredSession | None:
    """Look up an unexpired session. Returns None if missing or expired."""
    row = db.execute(
        text(
            """
            SELECT id, collection, created_at, expires_at
            FROM collection_sessions
            WHERE id = :id AND expires_at > NOW()
            """
        ),
        {"id": session_id},
    ).fetchone()
    if row is None:
        return None
    return StoredSession(
        session_id=row.id,
        rows=_deserialize_rows(row.collection),
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


def delete_session(db: Session, session_id: str) -> None:
    db.execute(
        text("DELETE FROM collection_sessions WHERE id = :id"),
        {"id": session_id},
    )
    db.commit()


def _serialize_rows(rows: list[ParsedCollectionRow]) -> str:
    """JSON-encode rows for the JSONB column.

    Pydantic's ``model_dump_json`` handles ``Decimal`` correctly (string
    serialisation), which is what we want -- JSONB will store the value
    as text inside the document and we re-parse to ``Decimal`` on read
    so downstream math doesn't accidentally use floats.
    """
    import json

    payload = [_row_to_dict(r) for r in rows]
    return json.dumps(payload)


def _row_to_dict(row: ParsedCollectionRow) -> dict[str, Any]:
    return {
        "card_id": row.card_id,
        "condition": row.condition,
        "variant": list(row.variant),
        "is_first_edition": row.is_first_edition,
        "quantity": row.quantity,
        "purchase_price": str(row.purchase_price) if row.purchase_price is not None else None,
    }


def _deserialize_rows(payload: Any) -> list[ParsedCollectionRow]:
    """Inverse of ``_serialize_rows``. JSONB comes back as native Python."""
    out: list[ParsedCollectionRow] = []
    for entry in payload or []:
        purchase_price = entry.get("purchase_price")
        out.append(
            ParsedCollectionRow(
                card_id=entry["card_id"],
                condition=entry["condition"],
                variant=list(entry.get("variant") or []),
                is_first_edition=bool(entry.get("is_first_edition")),
                quantity=int(entry["quantity"]),
                purchase_price=Decimal(purchase_price) if purchase_price is not None else None,
            )
        )
    return out
