"""
Endpoints for the user-collection upload flow.

The flow is:

1. ``GET /collection/template`` -- download the .xlsx template populated
   with the current set list as a dropdown.
2. ``POST /collection/upload`` -- submit a filled-out workbook. On
   success a session row is created, a session cookie is set, and the
   summary (card count, set count) is returned. On row-level failure
   the response is 422 with the per-row errors so the frontend can
   render them and offer the annotated workbook.
3. ``POST /collection/upload/annotated`` -- accepts the same workbook
   and returns it with an ``Error`` column added. We re-validate
   server-side rather than trusting any prior validation result the
   client might pass back.
4. ``POST /collection/mock`` -- read ``api/assets/mock_collection.xlsx``
   from disk and run it through the same pipeline as a normal upload.
5. ``GET /collection/session`` -- read the session cookie and return
   the parsed rows for the dashboard view (built in M04_S03).
6. ``DELETE /collection/session`` -- clear the cookie and remove the
   session row.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from schemas.collection import (
    CollectionCardsWithPricesResponse,
    CollectionMoversResponse,
    CollectionTimeseriesResponse,
    ParsedCollectionRow,
    SessionResponse,
    UploadSuccess,
    UploadValidationFailure,
)
from services.collection_annotator import annotate_workbook
from services.collection_excel import (
    EXCEL_MEDIA_TYPE,
    excel_filename,
    populate_template,
)
from services.collection_pricing import (
    cards_with_prices,
    daily_timeseries,
    movers,
    parse_window,
)
from services.collection_session import (
    COOKIE_MAX_AGE_SECONDS,
    COOKIE_NAME,
    create_session,
    delete_session,
    get_session,
)
from services.collection_template import build_template_workbook, template_filename
from services.collection_validator import validate_workbook

from decimal import Decimal


XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
MOCK_FILE_PATH = (
    Path(__file__).resolve().parent.parent / "assets" / "mock_collection.xlsx"
)


router = APIRouter(prefix="/collection", tags=["collection"])


def _cookie_secure() -> bool:
    """Whether the session cookie should carry the ``Secure`` flag.

    Defaults to True in production. Local dev (``http://localhost``)
    can opt out by setting ``SESSION_COOKIE_SECURE=false`` in .env so
    the browser will actually accept the cookie over plain HTTP.
    """
    raw = os.environ.get("SESSION_COOKIE_SECURE", "true").strip().lower()
    return raw not in {"0", "false", "no"}


def _cookie_samesite() -> str:
    """SameSite attribute paired with ``_cookie_secure()``.

    The deployed frontend and API live on different ``*.onrender.com``
    subdomains. ``onrender.com`` is on the Public Suffix List, so the
    browser treats those subdomains as separate sites and refuses to
    send a ``SameSite=Strict`` (or even ``Lax``) cookie on the
    cross-site XHR. ``SameSite=None`` is required for cross-site
    credentialed requests -- and per spec that flavor requires
    ``Secure``, which we already set in production.

    Local dev runs both sides on ``http://localhost``, which is
    same-site, so ``Lax`` is enough and avoids browsers rejecting a
    ``SameSite=None`` cookie that lacks ``Secure``.
    """
    return "none" if _cookie_secure() else "lax"


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path="/",
    )


def _summarize(rows: list[ParsedCollectionRow]) -> tuple[int, int]:
    """Return (card_count, set_count) for a parsed collection.

    ``card_count`` is the total quantity across all rows -- the
    intuitive "how many cards in the binder" number. ``set_count`` is
    the number of distinct sets touched, derived from the card_id
    prefix (TCGdex card IDs are ``<set_id>-<number>`` so a left-split
    on the dash is sufficient and keeps this helper free of an extra
    DB round-trip).
    """
    card_count = sum(r.quantity for r in rows)
    set_ids: set[str] = set()
    for r in rows:
        if "-" in r.card_id:
            set_ids.add(r.card_id.split("-", 1)[0])
        else:
            set_ids.add(r.card_id)
    return card_count, len(set_ids)


@router.get("/template")
def download_template(db: Session = Depends(get_db)) -> StreamingResponse:
    """Generate and return the upload template workbook."""
    from io import BytesIO

    blob = build_template_workbook(db)
    headers = {
        "Content-Disposition": f'attachment; filename="{template_filename()}"'
    }
    return StreamingResponse(BytesIO(blob), media_type=XLSX_MEDIA_TYPE, headers=headers)


def _process_upload(
    file_bytes: bytes,
    db: Session,
    response: Response,
) -> UploadSuccess:
    """Validate the bytes, persist, set the cookie. Raise 422 on errors."""
    result = validate_workbook(file_bytes, db)
    if result.has_errors:
        failure = UploadValidationFailure(
            structural_error=result.structural_error,
            total_rows=result.total_rows,
            error_rows=result.row_errors,
            distinct_error_messages=result.distinct_error_messages,
        )
        raise HTTPException(status_code=422, detail=failure.model_dump())

    session_id = create_session(db, result.parsed_rows)
    _set_session_cookie(response, session_id)
    card_count, set_count = _summarize(result.parsed_rows)
    return UploadSuccess(
        session_id=session_id,
        card_count=card_count,
        set_count=set_count,
    )


@router.post("/upload", response_model=UploadSuccess)
async def upload_collection(
    response: Response,
    file: UploadFile,
    db: Session = Depends(get_db),
) -> UploadSuccess:
    """Validate an uploaded workbook and create a session on success."""
    file_bytes = await file.read()
    return _process_upload(file_bytes, db, response)


@router.post("/upload/annotated")
async def download_annotated_workbook(
    file: UploadFile,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Re-validate a workbook and return it with an Error column added."""
    from io import BytesIO

    file_bytes = await file.read()
    annotated = annotate_workbook(file_bytes, db)
    headers = {
        "Content-Disposition": 'attachment; filename="collection-errors.xlsx"'
    }
    return StreamingResponse(
        BytesIO(annotated), media_type=XLSX_MEDIA_TYPE, headers=headers
    )


@router.post("/mock", response_model=UploadSuccess)
def upload_mock_collection(
    response: Response,
    db: Session = Depends(get_db),
) -> UploadSuccess:
    """Run the bundled mock collection through the upload pipeline."""
    if not MOCK_FILE_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "Mock collection file is not available on this deployment."
            ),
        )
    file_bytes = MOCK_FILE_PATH.read_bytes()
    return _process_upload(file_bytes, db, response)


@router.get("/session", response_model=SessionResponse)
def read_session(
    db: Session = Depends(get_db),
    collection_session_id: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> SessionResponse:
    """Return the parsed collection tied to the caller's session cookie."""
    if not collection_session_id:
        raise HTTPException(status_code=404, detail="No active collection session")
    stored = get_session(db, collection_session_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="No active collection session")
    card_count, set_count = _summarize(stored.rows)
    return SessionResponse(
        session_id=stored.session_id,
        rows=stored.rows,
        card_count=card_count,
        set_count=set_count,
    )


def _require_session_rows(
    db: Session,
    collection_session_id: str | None,
) -> list[ParsedCollectionRow]:
    """Look up the active session or raise 404.

    Centralised so all dashboard endpoints share a single 404 message
    and the cookie/session decoupling lives in one place.
    """
    if not collection_session_id:
        raise HTTPException(status_code=404, detail="No active collection session")
    stored = get_session(db, collection_session_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="No active collection session")
    return stored.rows


@router.get("/cards-with-prices", response_model=CollectionCardsWithPricesResponse)
def get_cards_with_prices(
    db: Session = Depends(get_db),
    collection_session_id: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> CollectionCardsWithPricesResponse:
    """Session rows joined to current market prices + card metadata."""
    rows = _require_session_rows(db, collection_session_id)
    cards = cards_with_prices(db, rows)
    return CollectionCardsWithPricesResponse(cards=cards)


@router.get("/timeseries", response_model=CollectionTimeseriesResponse)
def get_timeseries(
    window: str | None = None,
    db: Session = Depends(get_db),
    collection_session_id: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> CollectionTimeseriesResponse:
    """Daily total ``quantity * price`` for the chosen window."""
    rows = _require_session_rows(db, collection_session_id)
    try:
        normalized_window = parse_window(window)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    points, earliest = daily_timeseries(db, rows, normalized_window)
    return CollectionTimeseriesResponse(
        points=points,
        earliest_snapshot=earliest.isoformat() if earliest else None,
    )


@router.get("/movers", response_model=CollectionMoversResponse)
def get_movers(
    window: str | None = None,
    count: int = 5,
    min_pct: Decimal = Decimal("0.05"),
    db: Session = Depends(get_db),
    collection_session_id: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> CollectionMoversResponse:
    """Top ``count`` gainers and losers above ``min_pct`` movement."""
    rows = _require_session_rows(db, collection_session_id)
    try:
        normalized_window = parse_window(window)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if count < 1:
        raise HTTPException(status_code=422, detail="count must be >= 1")
    if min_pct < 0:
        raise HTTPException(status_code=422, detail="min_pct must be >= 0")
    gainers, losers = movers(db, rows, normalized_window, count, min_pct)
    return CollectionMoversResponse(gainers=gainers, losers=losers)


@router.get("/excel")
def download_collection_excel(
    db: Session = Depends(get_db),
    collection_session_id: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> StreamingResponse:
    """Populate the collection template with the user's data and stream it.

    Always returns the user's full collection -- dashboard slicer
    state is intentionally ignored so the export is a portable copy
    rather than a snapshot of the current view.
    """
    from io import BytesIO

    rows = _require_session_rows(db, collection_session_id)
    try:
        blob = populate_template(db, rows)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Excel template is not available on this deployment. "
                "Please regenerate api/assets/collection_template.xlsx."
            ),
        ) from exc
    headers = {
        "Content-Disposition": f'attachment; filename="{excel_filename()}"',
    }
    return StreamingResponse(BytesIO(blob), media_type=EXCEL_MEDIA_TYPE, headers=headers)


@router.delete("/session", status_code=204)
def clear_session(
    response: Response,
    db: Session = Depends(get_db),
    collection_session_id: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> Response:
    """Drop the session row (if any) and clear the cookie."""
    if collection_session_id:
        delete_session(db, collection_session_id)
    # Match Secure/SameSite to the original Set-Cookie so browsers
    # accept the deletion. Chrome silently ignores a delete that
    # doesn't match the original cookie's flags.
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        httponly=True,
    )
    return Response(status_code=204)
