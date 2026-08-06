"""
Per-client rate limiting for the write endpoints.

Only three endpoints accept work from the caller: the two collection
uploads and the mock loader. Each one parses a workbook, runs a query
per row, and writes a session. Left unbounded on a free tier that is
both a cost problem and an availability problem. The reads are cheap
and cached and are deliberately left alone.

Hand-rolled rather than pulled from a library. Render's free tier runs
a single instance, so in-process state is the correct scope, and the
behaviour needed here is small enough that a dependency would cost more
than it saves -- the same reasoning that produced
``services.xlsx_patcher``.

**This is abuse control, not authentication.** Client identity comes
from a header the client can set, and the counters reset when the
process restarts. Both are acceptable: the worst outcome is that a
determined attacker evades their own limit, which leaves us no worse
off than having no limiter. Anything that actually needs to be
unforgeable would need a different mechanism entirely.
"""

from __future__ import annotations

import os
import time
from collections import deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# Ten writes per ten minutes. Uploading a collection is a once-then-fix
# activity: a user might upload, hit validation errors, correct the
# sheet and retry a few times. Ten inside ten minutes is comfortably
# above that and far below what a script would do.
_DEFAULT_MAX_REQUESTS = 10
_DEFAULT_WINDOW_SECONDS = 600

# Ceiling on tracked clients. Without this the store is an unbounded
# dict keyed by a caller-supplied header -- a slow memory leak that an
# attacker could drive deliberately by rotating the header.
_MAX_TRACKED_CLIENTS = 10_000

# Paths that cost real work. Matched exactly rather than by prefix so
# that adding a cheap endpoint under /collection later cannot be
# throttled by accident.
LIMITED_PATHS = frozenset(
    {
        "/collection/upload",
        "/collection/upload/annotated",
        "/collection/mock",
    }
)


def _int_env(name: str, default: int) -> int:
    """Read a positive integer setting, ignoring anything malformed.

    A bad value must not disable the limiter or crash a request, so it
    falls back to the default rather than raising.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def max_requests() -> int:
    return _int_env("RATE_LIMIT_MAX_REQUESTS", _DEFAULT_MAX_REQUESTS)


def window_seconds() -> int:
    return _int_env("RATE_LIMIT_WINDOW_SECONDS", _DEFAULT_WINDOW_SECONDS)


def client_key(scope: Scope) -> str:
    """Identify the caller, preferring the proxy's forwarded address.

    On Render the app sits behind a proxy, so the socket peer is always
    the proxy's address -- keying on it would lump every user in the
    world into one bucket and throttle the whole site the moment one
    person uploaded too often. ``X-Forwarded-For`` carries the original
    client as the first entry in a comma-separated chain.

    Falls back to the socket peer when the header is absent, which is
    the local-development case.
    """
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name == b"x-forwarded-for":
            first = raw_value.decode("latin-1").split(",")[0].strip()
            if first:
                return first
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimiter:
    """Sliding-window counter over request timestamps.

    A sliding window rather than a fixed one because a fixed window lets
    a caller send two full allowances back to back either side of the
    boundary -- twice the intended burst at exactly the wrong moment.

    The clock is injected so tests can advance time explicitly instead
    of sleeping, which keeps the suite fast and the assertions exact.
    """

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def _evict_stale(self, now: float, window: float) -> None:
        """Drop clients whose entire history has aged out.

        Called on each check, so the store stays proportional to active
        callers rather than to everyone who has ever called.
        """
        cutoff = now - window
        empty = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in empty:
            del self._hits[key]

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit. Returns ``(allowed, retry_after_seconds)``."""
        now = self._clock()
        window = window_seconds()
        limit = max_requests()

        self._evict_stale(now, window)

        hits = self._hits.setdefault(key, deque())
        cutoff = now - window
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= limit:
            # Retry when the oldest hit in the window expires.
            retry_after = max(1, int(hits[0] + window - now) + 1)
            return False, retry_after

        # Only enforce the client ceiling on a genuinely new key, so an
        # established caller is never dropped in favour of a new one.
        if len(self._hits) > _MAX_TRACKED_CLIENTS:
            self._hits.pop(next(iter(self._hits)), None)

        hits.append(now)
        return True, 0

    def reset(self) -> None:
        """Clear all state. Used by tests for isolation."""
        self._hits.clear()


# One limiter shared by the whole process. Held at module scope rather
# than inside the middleware instance so it can be reached without
# digging through Starlette's middleware stack -- the test suite resets
# it between cases, and without that the counters would carry over and
# throttle the suite itself.
_DEFAULT_LIMITER = RateLimiter()


def default_limiter() -> RateLimiter:
    return _DEFAULT_LIMITER


class RateLimitMiddleware:
    """Pure-ASGI middleware applying :class:`RateLimiter` to writes.

    Written against the raw ASGI interface rather than
    ``BaseHTTPMiddleware`` because the latter wraps every response in an
    anyio task group, which interferes with streaming responses -- and
    two of the endpoints in this app stream workbooks back.
    """

    def __init__(self, app: ASGIApp, limiter: RateLimiter | None = None):
        self.app = app
        self.limiter = limiter or _DEFAULT_LIMITER

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in LIMITED_PATHS:
            await self.app(scope, receive, send)
            return

        allowed, retry_after = self.limiter.check(client_key(scope))
        if allowed:
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            status_code=429,
            content={
                "detail": (
                    "Too many uploads from this address. "
                    f"Try again in {retry_after} seconds."
                )
            },
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)


__all__ = [
    "LIMITED_PATHS",
    "RateLimitMiddleware",
    "RateLimiter",
    "client_key",
    "default_limiter",
    "max_requests",
    "window_seconds",
]
