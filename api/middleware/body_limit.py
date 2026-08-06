"""
Reject an oversized request before its body is read.

``services.upload_guard.read_capped`` is the authoritative size check,
but it cannot run early enough to help here. FastAPI awaits
``request.form()`` before it resolves dependencies or enters the route
handler, so by the time any application code sees the request, Starlette
has already consumed the entire body and spooled it to a temporary file.
For a genuinely large upload that spool is the slow part, and a client
can time out waiting for a 413 that the server would happily have sent
immediately.

Middleware is the only layer that runs before that happens. This one
looks at ``Content-Length`` alone -- a header, no body read at all -- and
refuses anything obviously too big.

**This is a courtesy, not a boundary.** ``Content-Length`` is supplied by
the client, may be absent, and is meaningless under chunked transfer
encoding. A caller who wants to lie about it will still reach
``read_capped``, which counts real bytes and is what actually enforces
the limit. The value here is that the honest case -- a browser posting a
FormData, which always sets Content-Length -- gets an instant, readable
answer instead of a timeout.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from services.upload_guard import max_upload_bytes

# Only the endpoints that accept a file. Matched exactly rather than by
# prefix so a future cheap endpoint under /collection cannot be rejected
# for carrying a large body it legitimately needs.
GUARDED_PATHS = frozenset(
    {
        "/collection/upload",
        "/collection/upload/annotated",
    }
)


def declared_length(scope: Scope) -> int | None:
    """Content-Length as an int, or None when absent or unparseable."""
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class ContentLengthLimitMiddleware:
    """Refuse an over-sized upload on its headers alone."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in GUARDED_PATHS:
            await self.app(scope, receive, send)
            return

        limit = max_upload_bytes()
        length = declared_length(scope)
        if length is None or length <= limit:
            await self.app(scope, receive, send)
            return

        megabytes = limit // (1024 * 1024)
        response = JSONResponse(
            status_code=413,
            content={"detail": f"File is larger than the {megabytes} MB limit."},
        )
        await response(scope, receive, send)


__all__ = ["ContentLengthLimitMiddleware", "GUARDED_PATHS", "declared_length"]
